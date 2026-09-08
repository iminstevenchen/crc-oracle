"""
腸命天機 Gut Instinct · FAMD v3 訓練管線
=========================================
跟 train_v3.py 用同一份資料、同樣 23 個臨床特徵，但改用 FAMD
（Factor Analysis of Mixed Data，prince套件）取代線性 PCA：
  - 11 個連續變數：z-score 標準化後當作PCA部分處理
  - 12 個類別變數：保留真正類別標籤（不強制轉序數），用類似MCA的方式編碼

輸出：artifacts_famd.pkl（給 similarity_api_famd.py 使用）
"""
import os
import sys
import pickle
import numpy as np
import pandas as pd
import prince
from sklearn.model_selection import KFold
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index

# --- 路徑處理與模組導入 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
sys.path.insert(0, "/mnt/user-data/outputs/gut_instinct_pca_v3")

try:
    from PCA_V3 import load_raw, clean999, HOLDOUT_IDS
except ImportError:
    from train_v3 import load_raw, clean999, HOLDOUT_IDS

# 設定輸出目錄
OUT_DIR = "/mnt/user-data/outputs/gut_instinct_pca_v3/"
if not os.path.exists(OUT_DIR):
    OUT_DIR = os.path.join(CURRENT_DIR, "outputs")
    os.makedirs(OUT_DIR, exist_ok=True)

T_map = {0: "T0", 1: "T1", 2: "T2", 22: "T2", 3: "T3", 33: "T3", 32: "T3", 41: "T4a", 42: "T4b", 4: "T4"}
N_map = {0: "N0", 1: "N1", 11: "N1a", 12: "N1b", 13: "N1c", 2: "N2", 21: "N2a", 22: "N2b", 3: "N3"}
M_map = {0: "M0", 1: "M1", 11: "M1a", 12: "M1b", 13: "M1c"}
STAGE_map = {0: "0", 1: "I", 2: "II", 3: "III", 4: "IV"}
SITE_map = {0: "right", 1: "left", 2: "rectum"}
HG_map = {1: "well", 2: "moderate", 3: "poor"}

CONT = ["AGE", "BMI", "ELN", "PLN", "LN_ratio", "WID", "LEN", "RM",
        "LAB_CEA_log", "LAB_ALB", "LAB_HB"]
CAT = ["SEX", "TNM_stage", "T_stage", "N_stage", "M_stage", "site_group",
       "HT_adenoca", "HG_grade", "GA_infiltrative", "CI", "IR_curative", "OT_emergency"]

FEATURE_LABELS_ZH = {
    "AGE": "診斷年齡", "BMI": "BMI", "ELN": "摘除淋巴結數", "PLN": "陽性淋巴結數",
    "LN_ratio": "淋巴結陽性比率", "WID": "腫瘤寬度(cm)", "LEN": "腫瘤長度(cm)",
    "RM": "切除margin(cm)", "LAB_CEA_log": "術前CEA(log)", "LAB_ALB": "術前白蛋白",
    "LAB_HB": "術前血色素", "SEX": "性別", "TNM_stage": "TNM總分期", "T_stage": "T分期",
    "N_stage": "N分期", "M_stage": "M分期", "site_group": "腫瘤側別",
    "HT_adenoca": "腺癌型組織學", "HG_grade": "分化程度", "GA_infiltrative": "浸潤型外觀",
    "CI": "環周侵犯", "IR_curative": "根治性切除", "OT_emergency": "急診手術",
}


def site_group_raw(v):
    if v in (1, 2, 3, 4):
        return 0
    if v in (5, 6, 7):
        return 1
    if v == 8:
        return 2
    return np.nan


def build_famd_features(df: pd.DataFrame) -> pd.DataFrame:
    feat = pd.DataFrame(index=df.index)
    feat["SER_NO"] = df["SER_NO"]
    feat["AGE"] = df["AGE"].astype(float)
    h = clean999(df["HEIGHT"]) / 100.0
    w = clean999(df["WEIGHT"])
    feat["BMI"] = w / (h ** 2)
    feat["ELN"] = df["ELN"].where(df["ELN"] <= 90, np.nan).astype(float)
    feat["PLN"] = df["PLN"].where(df["PLN"] <= 90, np.nan).astype(float)
    feat["LN_ratio"] = (feat["PLN"] / feat["ELN"].replace(0, np.nan)).clip(0, 1)
    feat["WID"] = clean999(df["WID_1"]).astype(float)
    feat["LEN"] = clean999(df["LEN_1"]).astype(float)
    feat["RM"] = clean999(df["RM"]).astype(float)
    feat["LAB_CEA_log"] = np.log1p(clean999(df["LAB_CEA"]).clip(upper=1000))
    feat["LAB_ALB"] = df["LAB_ALB"].where(df["LAB_ALB"].between(1, 6), np.nan)
    feat["LAB_HB"] = df["LAB_HB"].where(df["LAB_HB"].between(3, 20), np.nan)

    feat["SEX"] = df["SEX"].map({0: "female", 1: "male"})
    feat["TNM_stage"] = df["TNM"].map(STAGE_map)
    feat["T_stage"] = df["TMN_T"].map(T_map)
    feat["N_stage"] = df["TMN_N"].map(N_map)
    feat["M_stage"] = df["TMN_M"].map(M_map)
    feat["site_group"] = df["TL_1"].apply(site_group_raw).map(SITE_map)
    feat["HT_adenoca"] = df["HT_1"].isin([1, 2, 3]).map({True: "yes", False: "no"})
    feat["HG_grade"] = df["HG_1"].map(HG_map)
    feat["GA_infiltrative"] = df["GA_1"].isin([4, 7]).map({True: "yes", False: "no"})
    feat["CI"] = df["CI"].map({1: "no", 2: "yes"})
    feat["IR_curative"] = (df["IR"] == 3).map({True: "yes", False: "no"})
    feat["OT_emergency"] = (df["OT"] == 2).map({True: "yes", False: "no"})

    feat["os_time_days"] = df["os_time_days"]
    feat["os_event"] = df["os_event"]

    # 統一 SER_NO 為字串型態進行比對
    holdout_ids_str = set(str(x).strip() for x in HOLDOUT_IDS)
    feat["is_holdout"] = feat["SER_NO"].astype(str).str.strip().isin(holdout_ids_str)

    return feat


def build_cox_design(df_imp, cont_mu=None, cont_sigma=None, dummy_cols=None):
    z = df_imp[CONT].copy()
    if cont_mu is None:
        cont_mu = z.mean()
        cont_sigma = z.std().replace(0, 1.0)
    z = (z - cont_mu) / cont_sigma
    dummies = pd.get_dummies(df_imp[CAT], drop_first=True)
    if dummy_cols is not None:
        dummies = dummies.reindex(columns=dummy_cols, fill_value=0)
    X = pd.concat([z, dummies.astype(float)], axis=1)
    return X, cont_mu, cont_sigma, dummies.columns


def transform_famd_safe(famd_model, df_imp, train_imp):
    """
    對齊訓練集的轉碼結果，解決舊版 prince 對小樣本 holdout 計算降維座標時維度不一致的致命問題
    """
    # 建立與 train_imp 一致的 One-Hot 全局編碼矩陣
    train_encoded = pd.get_dummies(train_imp[CAT].astype(str))
    expected_cat_cols = train_encoded.columns

    # 對 holdout 轉碼並以 train 的欄位作為基準補齊缺少的類別 (補 0)
    holdout_encoded = pd.get_dummies(df_imp[CAT].astype(str))
    holdout_encoded = holdout_encoded.reindex(columns=expected_cat_cols, fill_value=0)

    # 組合連續欄位與補齊後的類別欄位
    X_global = pd.concat([df_imp[CONT].astype(float), holdout_encoded], axis=1)

    # 透過內部 MFA 特徵建構邏輯或 SVD 相乘計算投影座標
    if hasattr(famd_model, "_row_coordinates_from_global"):
        # 利用 prince 原生的內部全域座標投影機制
        return famd_model._row_coordinates_from_global(X_global).values
    elif hasattr(famd_model, "V_"):
        # 直接使用全域 SVD 正交基底轉換
        return np.dot(X_global.values, famd_model.V_.T)
    else:
        # 兜底：直接對原始物件做 transform
        return famd_model.transform(df_imp).values


def train_all_famd():
    df = load_raw()
    feat = build_famd_features(df)

    train = feat[~feat["is_holdout"]].reset_index(drop=True)
    holdout = feat[feat["is_holdout"]].reset_index(drop=True)

    print(f"實際找到的 holdout 數量: {len(holdout)}")
    assert len(holdout) == 12, f"預期有 12 例 holdout，但實際抓到 {len(holdout)} 例"

    cont_medians = train[CONT].median()
    cat_modes = train[CAT].mode().iloc[0]

    def impute(d):
        out = d.copy()
        out[CONT] = out[CONT].fillna(cont_medians)
        out[CAT] = out[CAT].fillna(cat_modes)
        return out

    train_imp = impute(train[CONT + CAT])
    holdout_imp = impute(holdout[CONT + CAT])

    # 1. 強制連續變數轉 float
    for c in CONT:
        train_imp[c] = train_imp[c].astype(float)
        holdout_imp[c] = holdout_imp[c].astype(float)

    # 2. 強制類別變數轉純字串 object，確保 prince 型態檢查通過
    for c in CAT:
        train_imp[c] = train_imp[c].astype(str)
        holdout_imp[c] = holdout_imp[c].astype(str)

    # 3. 欄位順序對齊
    ordered_cols = CONT + CAT
    train_imp = train_imp[ordered_cols]
    holdout_imp = holdout_imp[ordered_cols]

    n_comp = 5
    famd = prince.FAMD(n_components=n_comp, engine="sklearn", random_state=42)
    famd = famd.fit(train_imp)

    # 4. 取得 train 降維座標
    if hasattr(famd, "row_coordinates"):
        train_coord = famd.row_coordinates(train_imp).values
    else:
        train_coord = famd.transform(train_imp).values

    # 5. 安全取得 holdout 降維座標（帶有欄位對齊機制）
    try:
        holdout_coord = transform_famd_safe(famd, holdout_imp, train_imp)
    except Exception:
        if hasattr(famd, "row_coordinates"):
            holdout_coord = famd.row_coordinates(holdout_imp).values
        else:
            holdout_coord = famd.transform(holdout_imp).values

    # 相容特徵值與貢獻度提取
    eigen = getattr(famd, "eigenvalues_", None)
    if eigen is None and hasattr(famd, "eigenvalues_summary"):
        eigen = famd.eigenvalues_summary["eigenvalue"].values
    elif isinstance(eigen, (pd.DataFrame, pd.Series)):
        eigen = eigen.values

    pct_var = getattr(famd, "percentage_of_variance_", None)
    if pct_var is None and hasattr(famd, "eigenvalues_summary"):
        pct_var = famd.eigenvalues_summary["% of variance"].values
    elif isinstance(pct_var, (pd.DataFrame, pd.Series)):
        pct_var = pct_var.values

    cum_var = np.cumsum(pct_var) if pct_var is not None else None
    col_contrib = getattr(famd, "column_contributions_", None)

    X_train, cont_mu, cont_sigma, dummy_cols = build_cox_design(train_imp)
    X_holdout, _, _, _ = build_cox_design(holdout_imp, cont_mu, cont_sigma, dummy_cols)

    cox_df = X_train.copy()
    cox_df["os_time_days"] = train["os_time_days"].values
    cox_df["os_event"] = train["os_event"].values
    cph = CoxPHFitter(penalizer=0.1)
    cph.fit(cox_df, duration_col="os_time_days", event_col="os_event")
    train_cindex = cph.concordance_index_

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_risk = np.zeros(len(cox_df))
    for tr_idx, te_idx in kf.split(cox_df):
        m = CoxPHFitter(penalizer=0.1)
        m.fit(cox_df.iloc[tr_idx], duration_col="os_time_days", event_col="os_event")
        oof_risk[te_idx] = m.predict_partial_hazard(cox_df.iloc[te_idx]).values
    cv_cindex = concordance_index(cox_df["os_time_days"], -oof_risk, cox_df["os_event"])

    hold_df = X_holdout.copy()
    hold_df["os_time_days"] = holdout["os_time_days"].values
    hold_df["os_event"] = holdout["os_event"].values
    hold_risk = cph.predict_partial_hazard(hold_df).values
    try:
        hold_cindex = concordance_index(hold_df["os_time_days"], -hold_risk, hold_df["os_event"])
    except ZeroDivisionError:
        hold_cindex = None

    artifacts = dict(
        CONT=CONT, CAT=CAT, cont_medians=cont_medians, cat_modes=cat_modes,
        famd=famd, train_coord=train_coord, holdout_coord=holdout_coord,
        eigen=eigen, pct_var=pct_var, cum_var=cum_var, col_contrib=col_contrib,
        cph=cph, cont_mu=cont_mu, cont_sigma=cont_sigma, dummy_cols=list(dummy_cols),
        train=train, holdout=holdout,
        train_cindex=train_cindex, cv_cindex=cv_cindex, hold_cindex=hold_cindex,
        hold_risk=hold_risk,
    )

    out_file = os.path.join(OUT_DIR, "artifacts_famd.pkl")
    with open(out_file, "wb") as f:
        pickle.dump(artifacts, f)

    print(f"train n={len(train)}  holdout n={len(holdout)}")
    if eigen is not None:
        print(f"eigenvalues (top5): {np.round(eigen[:5], 4).tolist()}")
    if cum_var is not None:
        print(f"cumulative %var (top3): {round(float(cum_var[2]), 2)}")
    print(f"train C-index: {round(train_cindex, 4)}  CV C-index: {round(cv_cindex, 4)}  "
          f"held-out(12): {hold_cindex}")
    return artifacts


if __name__ == "__main__":
    train_all_famd()