"""
腸命天機 Gut Instinct · 相似病患查詢 API (FAMD版)
====================================================
【v3.1 更新】年齡改用5分層類別變數(<50/50-60/60-70/70-80/80+)取代連續年齡，
理由：實測存活風險跟年齡非線性——50-60/60-70歲風險最低、<50歲居中(早發型
大腸癌本身風險較高)、70-80較高、80+最高。5-fold CV C-index從0.7978提升到0.7995。

用法：
    from similarity_api_famd import build_response
    payload = build_response({
        "AGE": 68,                      # 可直接傳實際年齡數字，自動轉成年齡分層
        "SEX": "male", "TNM_stage": "II", "T_stage": "T2",
        "N_stage": "N0", "M_stage": "M0", "site_group": "right",
        "HT_adenoca": "yes", "HG_grade": "moderate",
        "IR_curative": "yes", "OT_emergency": "no",
        "LAB_CEA_log": 2.60269,
    }, k=100)

也可以直接傳年齡分層字串，兩種都支援：{"age_group": "70-80", ...}

注意：其餘類別欄位要傳「類別字串」（如 "male"、"II"、"T2"），
不是像PCA版那樣傳數值代碼——這是FAMD版跟PCA版介面上最大的差異，
前端的NLP解析層需要對應調整輸出格式。
"""
import numpy as np
import pandas as pd
import pickle
import sys
from pathlib import Path
from lifelines import KaplanMeierFitter

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from train_famd_v3 import age_to_group

ARTIFACT_PATH = BASE_DIR / "artifacts_famd.pkl"

with open(ARTIFACT_PATH, "rb") as f:
    _A = pickle.load(f)

CONT, CAT = _A["CONT"], _A["CAT"]
_cont_medians, _cat_modes = _A["cont_medians"], _A["cat_modes"]
_famd = _A["famd"]
_train = _A["train"]
_train_coord = _A["train_coord"]
_cph = _A["cph"]
_cont_mu, _cont_sigma, _dummy_cols = _A["cont_mu"], _A["cont_sigma"], _A["dummy_cols"]

YEAR_DAYS = 365.25
_CATEGORY_LEVELS = {c: sorted(_train[c].dropna().unique().tolist()) for c in CAT}


def _normalize_raw(raw: dict) -> dict:
    """把 raw 裡的 AGE(數字) 自動轉成 age_group(類別)，其餘欄位原樣傳遞。
    若同時給了 AGE 跟 age_group，以明確給定的 age_group 為準。"""
    out = dict(raw)
    if "age_group" not in out and "AGE" in out and out["AGE"] is not None:
        out["age_group"] = age_to_group(out["AGE"])
    out.pop("AGE", None)
    return out


def encode_query(raw: dict) -> np.ndarray:
    """raw: {feature_name: value}；連續變數傳數值，類別變數傳字串類別，
    年齡可直接傳 AGE=數字（自動轉分層）或 age_group=字串。
    未提及欄位自動帶入訓練集中位數/眾數。回傳前5個FAMD座標。"""
    raw = _normalize_raw(raw)
    row = {}
    for c in CONT:
        row[c] = float(raw.get(c, _cont_medians[c]))
    for c in CAT:
        v = raw.get(c, _cat_modes[c])
        if v not in _CATEGORY_LEVELS[c]:
            v = _cat_modes[c]
        row[c] = v
    row_df = pd.DataFrame([row])
    for c in CAT:
        row_df[c] = pd.Categorical(row_df[c], categories=_CATEGORY_LEVELS[c])
    return _famd.row_coordinates(row_df).values[0]


def find_similar_patients(raw: dict, k: int = 100):
    """[固定K版，保留給需要跟舊結果比較時使用]"""
    q = encode_query(raw)
    d = np.linalg.norm(_train_coord - q, axis=1)
    idx = np.argsort(d)[:k]
    return _train.iloc[idx].reset_index(drop=True), d[idx], q


# ---------------------------------------------------------------------------
# 自適應搜尋：SD半徑起點 + 事件數門檻自動擴張（跟PCA版邏輯一致）
# ---------------------------------------------------------------------------
_pc_sd = _train_coord.std(axis=0)
_u_train = _train_coord / _pc_sd


def find_similar_patients_adaptive(raw: dict, min_events: int = 20,
                                    k_min: int = 30, k_max: int = 300,
                                    sd_start: float = 0.5):
    """同 similarity_api.py 的 find_similar_patients_adaptive，僅座標來源改為FAMD。
    回傳: (cohort_dataframe, distances_in_sd, meta_dict)"""
    q = encode_query(raw)
    u_query = q / _pc_sd
    d_sd = np.linalg.norm(_u_train - u_query, axis=1)
    order = np.argsort(d_sd)

    sorted_events = _train["os_event"].values[order]
    cum_events = np.cumsum(sorted_events)
    k_for_events = int(np.searchsorted(cum_events, min_events) + 1)
    k_used = int(np.clip(k_for_events, k_min, k_max))

    idx = order[:k_used]
    cohort = _train.iloc[idx].reset_index(drop=True)
    dist_sd = d_sd[idx]
    n_events = int(cohort["os_event"].sum())
    low_confidence = n_events < min_events

    meta = {
        "k_used": k_used, "sd_radius_used": round(float(dist_sd.max()), 3),
        "n_events": n_events, "min_events_target": min_events,
        "low_confidence": low_confidence, "sd_start": sd_start,
        "k_min": k_min, "k_max": k_max,
    }
    return cohort, dist_sd, meta


def km_curve(cohort: pd.DataFrame, time_points_years=(1, 3, 5, 10)):
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
    raw = _normalize_raw(raw)
    cont_row = {c: float(raw.get(c, _cont_medians[c])) for c in CONT}
    z = (pd.Series(cont_row) - _cont_mu) / _cont_sigma
    cat_row = {c: raw.get(c, _cat_modes[c]) for c in CAT}
    for c in CAT:
        if cat_row[c] not in _CATEGORY_LEVELS[c]:
            cat_row[c] = _cat_modes[c]
    cat_df = pd.DataFrame([cat_row])
    for c in CAT:
        cat_df[c] = pd.Categorical(cat_df[c], categories=_CATEGORY_LEVELS[c])
    dummies = pd.get_dummies(cat_df).reindex(columns=_dummy_cols, fill_value=0).astype(float)
    X = pd.concat([pd.DataFrame([z]), dummies], axis=1)
    return float(_cph.predict_partial_hazard(X).values[0])


def build_response(raw: dict, k: int = None, min_events: int = 20,
                    k_min: int = 30, k_max: int = 300, sd_start: float = 0.5) -> dict:
    raw = _normalize_raw(raw)
    if k is not None:
        cohort, dist, q_coord = find_similar_patients(raw, k=k)
        search_meta = {"method": "fixed_k", "k_used": k}
    else:
        cohort, dist, meta = find_similar_patients_adaptive(
            raw, min_events=min_events, k_min=k_min, k_max=k_max, sd_start=sd_start)
        q_coord = encode_query(raw)
        search_meta = {"method": "adaptive_sd_event", **meta}

    cohort_summary, cohort_curve = km_curve(cohort)
    all_summary, all_curve = km_curve(_train)
    return {
        "query": {"input_features": raw, "famd_coords": q_coord.round(3).tolist()},
        "cohort": {
            "n": int(len(cohort)),
            "search": search_meta,
            "median_distance": float(np.median(dist)),
            "profile": {
                "age_mean_years": float(cohort["AGE_years"].mean()),
                "age_group_mode": cohort["age_group"].mode().iloc[0] if not cohort["age_group"].mode().empty else None,
                "male_pct": float((cohort["SEX"] == "male").mean()),
                "stage_mode": cohort["TNM_stage"].mode().iloc[0] if not cohort["TNM_stage"].mode().empty else None,
            },
        },
        "km": {
            "summary": {"cohort": cohort_summary, "all": all_summary},
            "curve_cohort": cohort_curve,
            "curve_all": all_curve,
        },
        "risk_score": risk_score(raw),
        "model_meta": {
            "version": "v3-famd", "n_features": len(CONT) + len(CAT),
            "cv_cindex": _A["cv_cindex"], "holdout12_cindex": _A["hold_cindex"],
        },
    }


if __name__ == "__main__":
    demo = dict(AGE=68, SEX="male", TNM_stage="II", T_stage="T2", N_stage="N0", M_stage="M0",
                site_group="right", HT_adenoca="yes", HG_grade="moderate",
                IR_curative="yes", OT_emergency="no", LAB_CEA_log=np.log1p(12.5))

    print("=== 自適應搜尋（預設，AGE=68自動轉成年齡分層）===")
    out = build_response(demo)
    print("cohort n:", out["cohort"]["n"], " search meta:", out["cohort"]["search"])
    print("cohort profile:", out["cohort"]["profile"])
    print("KM summary:", out["km"]["summary"])
    print("risk score:", out["risk_score"])

    print("\n=== 固定K=100（舊版比較）===")
    out_fixed = build_response(demo, k=100)
    print("cohort n:", out_fixed["cohort"]["n"])
    print("KM summary:", out_fixed["km"]["summary"])

    print("\n=== 直接傳 age_group 字串（等效寫法）===")
    demo2 = dict(demo); demo2.pop("AGE"); demo2["age_group"] = "60-70"
    out2 = build_response(demo2)
    print("cohort n:", out2["cohort"]["n"], " search meta:", out2["cohort"]["search"])
