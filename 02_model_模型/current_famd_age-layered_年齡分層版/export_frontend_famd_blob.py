# -*- coding: utf-8 -*-
"""
export_frontend_famd_blob.py
────────────────────────────────────────────────────────────────────────────
把 train_famd_v3.py 產生的 artifacts_famd.pkl，匯出成前端網站
(index_整合版.html) 直接可用的 `F` blob。

背景
────
export_frontend_data_famd.py 只匯出 3 個「展示用」JSON：
    famd_coefficients_v3.json      → PC 解釋變異、欄位貢獻度
    population_scatter_famd_v3.json→ PC1-3 座標（畫散佈圖用）
    holdout12_validation_famd_v3.json
這 3 個檔缺少網站「查詢」功能必須的兩塊資料：
    (1) FAMD 編碼器矩陣  → 新病患才能被投影到 PC 空間
    (2) 每位病患的臨床 / 存活欄位 → 才能算相似族群的 KM 曲線與術後結果
本腳本補上這兩塊，一次輸出成單一 JSON。

用法
────
    cd "5 age layer"
    python export_frontend_famd_blob.py                    # → famd_frontend_blob.json
    python export_frontend_famd_blob.py --html index_整合版.html   # 順便就地換掉網站裡的 F

需求：prince、numpy、pandas（＝跑 train_famd_v3.py 的同一個環境）。
**不需要** lifelines：pickle 裡的 Cox 物件我們用不到，會用 stub 接住。

輸出結構
────────
{
  "meta": {version, n_train, train_cindex, cv5_cindex, holdout12_cindex,
           n_continuous, n_categorical},
  "enc" : {cont[], cat_vars[], cat_categories{}, one_hot[], prop[],
           outer_mean[], outer_scale[], V[5][p], pc_sd[5], cat_modes{}},
  "d"   : {每個欄位都是長度 = n_train 的陣列，順序與 train 相同}
}
────────────────────────────────────────────────────────────────────────────
"""
import argparse, io, json, os, pickle, sys, types, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── 1. 讓 pickle 在沒有 lifelines 的環境也能載入 ────────────────────────────
class _Any:
    """萬用替身：unpickle 遇到 lifelines / autograd 的任何類別都用它接住。"""
    def __init__(self, *a, **k): pass
    def __setstate__(self, s):
        if isinstance(s, dict): self.__dict__.update(s)
    def __call__(self, *a, **k): return self
    def __getattr__(self, n): return _Any()

class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        setattr(self, name, _Any); return _Any

def _install_stubs():
    for name in ["lifelines", "lifelines.fitters", "lifelines.fitters.coxph_fitter",
                 "lifelines.utils", "lifelines.utils.concordance",
                 "autograd", "autograd.numpy", "autograd_gamma",
                 "formulaic", "formulaic.parser", "formulaic.parser.types"]:
        if name not in sys.modules:
            sys.modules[name] = _StubModule(name)

def load_artifacts(path):
    try:
        import prince  # noqa: F401
    except ImportError:
        raise SystemExit(
            "缺少 prince 套件。artifacts_famd.pkl 內含 prince 的 FAMD 物件，\n"
            "必須在跑過 train_famd_v3.py 的同一個 Python 環境執行本腳本，\n"
            "或先安裝：pip install prince pandas numpy")
    try:
        import lifelines  # noqa: F401  真的裝了就用真的
    except Exception:
        _install_stubs()   # 沒裝 lifelines 也能載入（Cox 物件我們用不到）
    with open(path, "rb") as fh:
        return pickle.load(fh)

# ── 2. 網站沿用的固定編碼表（與舊版 index_整合版.html 完全一致，勿改） ──────
TNM_CODE   = {"0": 0, "I": 1, "II": 2, "III": 3, "IV": 4}
GRADE_CODE = {"well": 1, "moderate": 2, "poor": 3}
T_CODE     = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}          # T0 / T4a / T4b → null
N_CODE     = {"N0": 1, "N1": 2, "N2": 3}                   # 帶 a/b/c 後綴 → null
M_CODE     = {"M0": 1, "M1": 2}                            # M1a/b/c      → null
YESNO      = {"yes": 1, "no": 0}

def _roc_to_date(s):
    """民國日期字串 '110-10-28' → Timestamp。無法解析回 NaT。"""
    s = s.astype(str).str.strip()
    y = pd.to_numeric(s.str[:3], errors="coerce") + 1911
    iso = y.astype("Int64").astype(str) + "-" + s.str[4:6] + "-" + s.str[7:9]
    return pd.to_datetime(iso, errors="coerce")

MONTH_DAYS = 30.4368          # 網站沿用的「月」換算基準，勿改

def _num(v, nd):
    """四捨五入到 nd 位；NaN → None。"""
    if v is None: return None
    v = float(v)
    if v != v: return None
    return round(v, nd)

def _str(v):
    if v is None: return None
    if isinstance(v, float) and v != v: return None
    s = str(v)
    return None if s in ("nan", "NaT", "None") else s

def _int(v):
    if v is None: return None
    v = float(v)
    return None if v != v else int(v)

def _clean(x):
    """把 numpy / NaN 轉成 JSON 可序列化的值。"""
    if x is None: return None
    if isinstance(x, (np.floating, float)):
        return None if (x != x) else round(float(x), 6)
    if isinstance(x, (np.integer, int)): return int(x)
    if isinstance(x, (np.bool_, bool)):  return int(x)
    if x is pd.NaT: return None
    return str(x)

def _arr(series, cast=None):
    out = []
    for v in series:
        if v is None or (isinstance(v, float) and v != v): out.append(None)
        elif cast is int:
            out.append(None if (isinstance(v, float) and v != v) else int(v))
        else: out.append(_clean(v))
    return out

# ── 3. 主流程 ──────────────────────────────────────────────────────────────
def build_blob(pkl_path, csv_path, version):
    A  = load_artifacts(pkl_path)
    f  = A["famd"]
    tr = A["train"].reset_index(drop=True)
    n  = len(tr)

    # ---- 3a. 編碼器 -------------------------------------------------------
    cont_names = list(f.num_cols_)                       # 連續變項（保持訓練順序）
    cat_vars   = list(f.cat_cols_)                       # 類別變項（prince 已排序）
    ns         = f.num_scaler_                           # 連續變項 z-score
    medians    = A["cont_medians"]

    cont = [{"name": c,
             "mean":   float(ns.mean_[i]),
             "std":    float(np.sqrt(ns.var_[i])),
             "median": float(medians[c])}
            for i, c in enumerate(cont_names)]

    one_hot = list(f.one_hot_columns_)                   # 49 個 one-hot 欄位
    cat_categories = {v: sorted(str(x) for x in f.categories_[v]) for v in cat_vars}

    # prop：每個 one-hot 欄位在訓練集的比例 p，編碼時用 (ind − p)/√p
    # 缺值先用 cat_modes 補（與 train_famd_v3.py 的前處理一致），否則比例會低估
    filled = tr[cat_vars].copy()
    for c in cat_vars:
        filled[c] = filled[c].fillna(A["cat_modes"][c])
    dummies = pd.get_dummies(filled, prefix_sep="_").reindex(columns=one_hot, fill_value=0)
    prop = dummies.mean(axis=0)

    outer = f.scaler_                                    # 外層 StandardScaler
    V     = np.asarray(f.svd_.V, dtype=float)            # (5, p)
    pc_sd = np.sqrt(np.asarray(A["eigen"], dtype=float)) # 各主成分標準差

    enc = {
        "cont": cont,
        "cat_vars": cat_vars,
        "cat_categories": cat_categories,
        "one_hot": one_hot,
        "prop": {c: float(prop[c]) for c in one_hot},
        "outer_mean":  [float(x) for x in outer.mean_],
        "outer_scale": [float(x) for x in outer.scale_],
        "V":     [[float(x) for x in row] for row in V],
        "pc_sd": [float(x) for x in pc_sd],
        "cat_modes": {k: str(v) for k, v in A["cat_modes"].items()},
    }

    meta = {
        "version": version,
        "n_train": int(n),
        "train_cindex":      round(float(A["train_cindex"]), 4),
        "cv5_cindex":        round(float(A["cv_cindex"]),    4),
        "holdout12_cindex":  round(float(A["hold_cindex"]),  4),
        "n_continuous":  len(cont_names),
        "n_categorical": len(cat_vars),
    }

    # ---- 3b. 每位病患的欄位 ----------------------------------------------
    coord = np.asarray(A["train_coord"], dtype=float)     # (n, 5)

    # LOS（術後住院天數）與 MT（出院前死亡）只存在於原始 CSV，需以 SER_NO 併回
    raw = pd.read_csv(csv_path, low_memory=False)
    raw.columns = [c.strip().lstrip("﻿") for c in raw.columns]
    raw = raw.drop_duplicates("SER_NO").set_index("SER_NO")
    sub = raw.reindex(tr["SER_NO"].values)

    los = (_roc_to_date(sub["DD"]) - _roc_to_date(sub["OD"])).dt.days   # 出院 − 手術
    mt  = (sub["MT"].values == 2).astype(int)                           # CSV: 1=否 2=是

    d = {
        "id":  [int(x) for x in tr["SER_NO"]],
        "t":   [int(x) for x in tr["os_time_days"]],
        "e":   [int(x) for x in tr["os_event"]],
        "los": [_int(v) for v in los.values],
        "mt":  [int(x) for x in mt],
        "age": [_int(v) for v in tr["AGE_years"]],
        "ageg": [_str(x) for x in tr["age_group"]],
        "sexM": [1 if x == "male" else 0 for x in tr["SEX"]],
        "stageCode": [TNM_CODE.get(_str(x)) for x in tr["TNM_stage"]],
        "gradeCode": [GRADE_CODE.get(_str(x)) for x in tr["HG_grade"]],
        "site":  [_str(x) for x in tr["site_group"]],
        "grade": [_str(x) for x in tr["HG_grade"]],
        "cea":   [_num(np.expm1(v), 4) for v in tr["LAB_CEA_log"]],
        "tM":    [_num(float(v) / MONTH_DAYS, 2) for v in tr["os_time_days"]],
        "c1": [round(v, 4) for v in coord[:, 0]],
        "c2": [round(v, 4) for v in coord[:, 1]],
        "c3": [round(v, 4) for v in coord[:, 2]],
        "c4": [round(v, 4) for v in coord[:, 3]],
        "c5": [round(v, 4) for v in coord[:, 4]],
        "bmi":  [_num(v, 2) for v in tr["BMI"]],
        "eln":  [_int(v) for v in tr["ELN"]],
        "pln":  [_int(v) for v in tr["PLN"]],
        "lnr":  [_num(v, 3) for v in tr["LN_ratio"]],
        "wid":  [_num(v, 2) for v in tr["WID"]],
        "len2": [_num(v, 2) for v in tr["LEN"]],
        "rm":   [_num(v, 2) for v in tr["RM"]],
        "alb":  [_num(v, 2) for v in tr["LAB_ALB"]],
        "hb":   [_num(v, 2) for v in tr["LAB_HB"]],
        "tS": [T_CODE.get(_str(x)) for x in tr["T_stage"]],
        "nS": [N_CODE.get(_str(x)) for x in tr["N_stage"]],
        "mS": [M_CODE.get(_str(x)) for x in tr["M_stage"]],
        "gaI": [YESNO.get(_str(x)) for x in tr["GA_infiltrative"]],
        "ci":  [YESNO.get(_str(x)) for x in tr["CI"]],
        "irc": [YESNO.get(_str(x)) for x in tr["IR_curative"]],
        "ote": [YESNO.get(_str(x)) for x in tr["OT_emergency"]],
        "hta": [YESNO.get(_str(x)) for x in tr["HT_adenoca"]],
    }

    # ---- 3c. 自我檢查 ------------------------------------------------------
    for k, v in d.items():
        assert len(v) == n, "欄位 %s 長度 %d ≠ %d" % (k, len(v), n)
    assert V.shape[0] == 5 and V.shape[1] == len(cont_names) + len(one_hot), \
        "V 形狀 %s 與 %d 連續 + %d one-hot 不符" % (V.shape, len(cont_names), len(one_hot))
    assert abs(f.total_inertia_ - (len(cont_names) + len(one_hot))) < 1e-6, \
        "total_inertia 與欄位數不符，編碼流程可能已改變"
    n_los = sum(1 for x in d["los"] if x is None)
    print("[檢查] n=%d  連續 %d  類別 %d  one-hot %d  V=%s" %
          (n, len(cont_names), len(cat_vars), len(one_hot), V.shape))
    print("[檢查] PC 解釋變異 %% = %s" %
          [round(float(e) / f.total_inertia_ * 100, 2) for e in A["eigen"]])
    print("[檢查] LOS 無法計算（缺 OD/DD）：%d 位，已存成 null" % n_los)
    print("[檢查] 術中/出院前死亡 MT=1：%d 位" % int(mt.sum()))

    return {"meta": meta, "enc": enc, "d": d}

def patch_html(html_path, blob_json):
    """就地把 HTML 裡的 `const F={...};` 換成新的 blob（F 定義佔完整一行）。"""
    s = io.open(html_path, encoding="utf-8").read()
    i = s.index("const F=")
    eol = s.index("\n", i)
    line = s[i:eol]
    if not line.rstrip().endswith("};"):
        raise SystemExit("找不到單行的 `const F={...};`，請手動替換。")
    s = s[:i] + "const F=" + blob_json + ";" + s[eol:]
    io.open(html_path, "w", encoding="utf-8").write(s)
    print("[HTML] 已替換 F：舊 %d bytes → 新 %d bytes" % (len(line), len(blob_json) + 9))

def main():
    ap = argparse.ArgumentParser(description="匯出前端網站用的 FAMD blob")
    ap.add_argument("--pkl", default="artifacts_famd.pkl")
    ap.add_argument("--csv", default="癌症資料20072023_AI去識別擬真版_v2.csv")
    ap.add_argument("--out", default="famd_frontend_blob.json")
    ap.add_argument("--html", default=None, help="若指定，順便就地更新該 HTML 的 F")
    ap.add_argument("--version", default="v3-famd-age5")
    a = ap.parse_args()

    for p in (a.pkl, a.csv):
        if not os.path.exists(p):
            raise SystemExit("找不到檔案：%s" % p)

    blob = build_blob(a.pkl, a.csv, a.version)
    txt = json.dumps(blob, ensure_ascii=False, separators=(",", ":"))
    io.open(a.out, "w", encoding="utf-8").write(txt)
    print("[輸出] %s  (%.2f MB)" % (a.out, len(txt.encode("utf-8")) / 1048576))
    if a.html:
        patch_html(a.html, txt)

if __name__ == "__main__":
    main()
