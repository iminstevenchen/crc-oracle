"""
腸命天機 Gut Instinct · 相似病患查詢 API (v3)
================================================
給前端／後端串接使用。載入 train_v3.py 產生的 artifacts.pkl，
提供：
  - encode_query(raw_dict)        自然語言解析後的結構化條件 -> PC 座標
  - find_similar_patients(...)    PCA 空間 KNN 找相似病患群
  - km_curve(cohort_df, ...)      算 KM 存活曲線（給定時間點的存活機率）
  - risk_score(raw_dict)          用 CoxPH 模型算病患風險分數(相對風險)
  - build_response(raw_dict, k)   直接組出前端要的完整 JSON 結構

使用方式（範例）：
    from similarity_api import build_response
    payload = build_response({
        "AGE": 68, "SEX": 1, "TNM_stage": 2, "T_stage": 2,
        "N_stage": 0, "M_stage": 0, "site_group": 0,
        "HT_adenoca": 1, "HG_grade": 2, "IR_curative": 1,
        "OT_emergency": 0, "LAB_CEA_log": 2.60269,
    }, k=100)
    print(payload["km"]["summary"])

未在 raw_dict 中出現的欄位，會自動帶入訓練集的中位數（等同於「未提及、採用預設」）。
"""
import numpy as np
import pandas as pd
import pickle
from pathlib import Path
from lifelines import KaplanMeierFitter

BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_PATH = BASE_DIR / "artifacts.pkl"

with open(ARTIFACT_PATH, "rb") as f:
    _A = pickle.load(f)

FEATURES = _A["FEATURES"]
_medians, _mu, _sigma, _x_mean = _A["medians"], _A["mu"], _A["sigma"], _A["x_mean"]
_Vt, _n_pc = _A["Vt"], _A["n_pc"]
_train = _A["train"]
_train_pc = _A["train_pc"]
_cph = _A["cph"]

YEAR_DAYS = 365.25


def encode_query(raw: dict) -> np.ndarray:
    """raw: {feature_name: value, ...}（可只給部分欄位）-> 前 n_pc 個主成分座標"""
    vec = _medians.copy()
    for k, v in raw.items():
        if k in vec.index and v is not None:
            vec[k] = v
    z = (vec[FEATURES] - _mu) / _sigma
    pc = (z.values - _x_mean).dot(_Vt[:_n_pc].T)
    return pc


def find_similar_patients(raw: dict, k: int = 100):
    """[固定K版，保留給需要跟舊結果比較時使用] 回傳 (cohort_dataframe, distances, query_pc_coords)。"""
    q_pc = encode_query(raw)
    d = np.linalg.norm(_train_pc - q_pc, axis=1)
    idx = np.argsort(d)[:k]
    return _train.iloc[idx].reset_index(drop=True), d[idx], q_pc


# ---------------------------------------------------------------------------
# 自適應搜尋：SD半徑起點 + 事件數門檻自動擴張
# ---------------------------------------------------------------------------
# 每個PC軸自己的標準差（全體訓練病患），用來把PC空間換成「SD單位」的距離，
# 這樣「0.5 SD」才有一致的統計意義，不會被PC1天生變異數較大而扭曲。
_pc_sd = _train_pc.std(axis=0)
_u_train = _train_pc / _pc_sd


def find_similar_patients_adaptive(raw: dict, min_events: int = 20,
                                    k_min: int = 30, k_max: int = 300,
                                    sd_start: float = 0.5):
    """
    自適應相似病患搜尋：
      1. 先以 sd_start（預設0.5 SD，5維合併距離）為起始半徑收案
      2. 若累積死亡事件數 < min_events，自動擴大半徑（等同擴大K）直到達標
      3. 不管半徑多寬，收案人數永遠介於 [k_min, k_max] 之間
      4. 若擴到 k_max 都還不夠 min_events 個事件，回傳 low_confidence=True，
         代表這是資料庫裡的罕見病患組合，結果只能參考、不建議直接呈現給醫師當定論

    回傳: (cohort_dataframe, distances_in_sd, meta_dict)
      meta_dict 包含: k_used, sd_radius_used, n_events, low_confidence, sd_start
    """
    q_pc = encode_query(raw)
    u_query = q_pc / _pc_sd
    d_sd = np.linalg.norm(_u_train - u_query, axis=1)
    order = np.argsort(d_sd)

    sorted_events = _train["os_event"].values[order]
    cum_events = np.cumsum(sorted_events)

    # 找出達到 min_events 所需的最小K，並套用 k_min / k_max 邊界
    k_for_events = int(np.searchsorted(cum_events, min_events) + 1)
    k_used = int(np.clip(k_for_events, k_min, k_max))

    idx = order[:k_used]
    cohort = _train.iloc[idx].reset_index(drop=True)
    dist_sd = d_sd[idx]
    n_events = int(cohort["os_event"].sum())
    low_confidence = n_events < min_events  # 代表即使開到k_max也湊不到足夠事件數

    meta = {
        "k_used": k_used,
        "sd_radius_used": round(float(dist_sd.max()), 3),
        "n_events": n_events,
        "min_events_target": min_events,
        "low_confidence": low_confidence,
        "sd_start": sd_start,
        "k_min": k_min,
        "k_max": k_max,
    }
    return cohort, dist_sd, meta


def km_curve(cohort: pd.DataFrame, time_points_years=(1, 3, 5, 10)):
    """回傳指定年份的存活機率，以及完整 KM 階梯曲線的 (day, survival) 點列表。"""
    kmf = KaplanMeierFitter()
    kmf.fit(cohort["os_time_days"], cohort["os_event"])
    summary = {}
    for yr in time_points_years:
        days = yr * YEAR_DAYS
        try:
            s = float(kmf.survival_function_at_times(days).values[0])
        except Exception:
            s = None
        summary[f"{yr}yr"] = s
    sf = kmf.survival_function_
    curve = [{"day": int(t), "survival": float(v)} for t, v in zip(sf.index, sf.iloc[:, 0])]
    return summary, curve


def risk_score(raw: dict) -> float:
    """用 CoxPH 模型算相對風險分數（partial hazard，數字愈大風險愈高）。"""
    vec = _medians.copy()
    for k, v in raw.items():
        if k in vec.index and v is not None:
            vec[k] = v
    z = (vec[FEATURES] - _mu) / _sigma
    return float(_cph.predict_partial_hazard(pd.DataFrame([z])).values[0])


def build_response(raw: dict, k: int = None, min_events: int = 20,
                    k_min: int = 30, k_max: int = 300, sd_start: float = 0.5) -> dict:
    """組出前端頁面需要的完整資料結構：cohort摘要、KM曲線(cohort vs全體)、PC座標。

    預設用「自適應搜尋」（SD半徑起點 + 事件數門檻自動擴張）。
    若明確傳入 k（固定K），則改用舊版固定K搜尋，方便跟舊結果比較。
    """
    if k is not None:
        cohort, dist, q_pc = find_similar_patients(raw, k=k)
        search_meta = {"method": "fixed_k", "k_used": k}
    else:
        cohort, dist, meta = find_similar_patients_adaptive(
            raw, min_events=min_events, k_min=k_min, k_max=k_max, sd_start=sd_start)
        q_pc = encode_query(raw)
        search_meta = {"method": "adaptive_sd_event", **meta}

    cohort_summary, cohort_curve = km_curve(cohort)
    all_summary, all_curve = km_curve(_train)

    return {
        "query": {"input_features": raw, "pc_coords": q_pc.round(3).tolist()},
        "cohort": {
            "n": int(len(cohort)),
            "search": search_meta,
            "median_distance": float(np.median(dist)),
            "profile": {
                "age_mean": float(cohort["AGE"].mean()),
                "male_pct": float(cohort["SEX"].mean()),
                "stage_mode": float(cohort["TNM_stage"].mode().iloc[0]) if not cohort["TNM_stage"].mode().empty else None,
            },
        },
        "km": {
            "summary": {"cohort": cohort_summary, "all": all_summary},
            "curve_cohort": cohort_curve,
            "curve_all": all_curve,
        },
        "risk_score": risk_score(raw),
        "model_meta": {
            "version": "v3", "n_features": len(FEATURES),
            "cv_cindex": _A["cv_cindex"], "holdout12_cindex": _A["hold_cindex"],
        },
    }


if __name__ == "__main__":
    demo = dict(AGE=68, SEX=1, TNM_stage=2, T_stage=2, N_stage=0, M_stage=0,
                site_group=0, HT_adenoca=1, HG_grade=2, IR_curative=1,
                OT_emergency=0, LAB_CEA_log=np.log1p(12.5))

    print("=== 自適應搜尋（預設，min_events=20）===")
    out = build_response(demo)
    print("cohort n:", out["cohort"]["n"], " search meta:", out["cohort"]["search"])
    print("KM summary:", out["km"]["summary"])
    print("risk score:", out["risk_score"])

    print("\n=== 固定K=100（舊版，用來比較）===")
    out_fixed = build_response(demo, k=100)
    print("cohort n:", out_fixed["cohort"]["n"])
    print("KM summary:", out_fixed["km"]["summary"])

    print("\n=== 罕見病患組合測試（極端年齡+M1c遠端轉移，驗證low_confidence機制）===")
    rare = dict(AGE=29, SEX=0, TNM_stage=4, T_stage=4, M_stage=1.6,
                site_group=2, HG_grade=3, GA_infiltrative=1, LAB_CEA_log=np.log1p(800))
    cohort_r, dist_r, meta_r = find_similar_patients_adaptive(rare)
    print("search meta:", meta_r)
