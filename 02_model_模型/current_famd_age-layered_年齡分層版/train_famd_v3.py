"""
腸命天機 Gut Instinct · FAMD v3 訓練管線
=========================================
跟 train_v3.py 用同一份資料、同樣 23 個臨床特徵，但改用 FAMD
（Factor Analysis of Mixed Data，prince套件）取代線性 PCA：
  - 10 個連續變數：z-score 標準化後當作PCA部分處理
  - 13 個類別變數（含年齡5分層）：保留真正類別標籤（不強制轉序數），
    用類似MCA的方式編碼，避免線性PCA把類別距離錯誤地假設成固定的數值差距

【年齡改版說明】原本年齡是連續變數，但實測發現存活風險跟年齡不是線性關係：
50-60/60-70歲風險反而最低、<50歲居中（早發型大腸癌本身風險較高，不完全是
年輕帶來的優勢）、70-80較高、80+最高。改成5分層類別變數後，
5-fold CV C-index從0.7978提升到0.7995。詳見 age_to_group()。

跟 train_v3.py 的差異：
  - PCA版把 T/N/M分期、分化程度等類別變數，人工映射成有序數值（如 T4a=4, T4b=4.5）
    再丟進標準PCA。這個做法簡單，但隱含假設「類別之間的數值距離有意義」，
    對於本來就是無序或非等距的分期代碼不完全合理。
  - FAMD版讓類別變數用自己的編碼方式（類似指標矩陣/卡方距離）進入降維空間，
    數學上更適合這種連續+類別混合的臨床資料。

輸出：artifacts_famd.pkl（給 similarity_api_famd.py 使用）+ artifacts/ 下的 JSON
"""
import pandas as pd
import numpy as np
import pickle
import prince
from pathlib import Path
from sklearn.model_selection import KFold
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
import sys

# 自動抓這支腳本所在的資料夾，並把它加進import路徑，這樣才能找到同資料夾的train_v3.py
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from train_v3 import load_raw, clean999, HOLDOUT_IDS

OUT_DIR = BASE_DIR

T_map = {0: "T0", 1: "T1", 2: "T2", 22: "T2", 3: "T3", 33: "T3", 32: "T3", 41: "T4a", 42: "T4b", 4: "T4"}
N_map = {0: "N0", 1: "N1", 11: "N1a", 12: "N1b", 13: "N1c", 2: "N2", 21: "N2a", 22: "N2b", 3: "N3"}
M_map = {0: "M0", 1: "M1", 11: "M1a", 12: "M1b", 13: "M1c"}
STAGE_map = {0: "0", 1: "I", 2: "II", 3: "III", 4: "IV"}
SITE_map = {0: "right", 1: "left", 2: "rectum"}
HG_map = {1: "well", 2: "moderate", 3: "poor"}

AGE_BINS = [0, 50, 60, 70, 80, 200]
AGE_LABELS = ["<50", "50-60", "60-70", "70-80", "80+"]  # 依實測風險：50-60/60-70最低風險、<50居中、80+最高風險

CONT = ["BMI", "ELN", "PLN", "LN_ratio", "WID", "LEN", "RM",
        "LAB_CEA_log", "LAB_ALB", "LAB_HB"]
CAT = ["SEX", "age_group", "TNM_stage", "T_stage", "N_stage", "M_stage", "site_group",
       "HT_adenoca", "HG_grade", "GA_infiltrative", "CI", "IR_curative", "OT_emergency"]

FEATURE_LABELS_ZH = {
    "BMI": "BMI", "ELN": "摘除淋巴結數", "PLN": "陽性淋巴結數",
    "LN_ratio": "淋巴結陽性比率", "WID": "腫瘤寬度(cm)", "LEN": "腫瘤長度(cm)",
    "RM": "切除margin(cm)", "LAB_CEA_log": "術前CEA(log)", "LAB_ALB": "術前白蛋白",
    "LAB_HB": "術前血色素", "SEX": "性別", "age_group": "年齡分層(5組)",
    "TNM_stage": "TNM總分期", "T_stage": "T分期",
    "N_stage": "N分期", "M_stage": "M分期", "site_group": "腫瘤側別",
    "HT_adenoca": "腺癌型組織學", "HG_grade": "分化程度", "GA_infiltrative": "浸潤型外觀",
    "CI": "環周侵犯", "IR_curative": "根治性切除", "OT_emergency": "急診手術",
}


def age_to_group(age) -> str:
    """把連續年齡轉成5個分層，跟資料實測的風險結構對齊（不是線性假設）。
    依 held-out無關的完整資料驗證：50-60/60-70歲風險最低、<50歲居中(早發型大腸癌
    獨立風險略高)、70-80較高、80+最高。"""
    if pd.isna(age):
        return np.nan
    for lo, hi, label in zip(AGE_BINS[:-1], AGE_BINS[1:], AGE_LABELS):
        if lo <= age < hi:
            return label
    return np.nan


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
    feat["age_group"] = df["AGE"].apply(age_to_group)
    feat["AGE_years"] = df["AGE"].astype(float)  # 僅供報表/前端顯示用，不是模型特徵
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
    feat["is_holdout"] = feat["SER_NO"].isin(HOLDOUT_IDS)
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


def train_all_famd():
    df = load_raw()
    feat = build_famd_features(df)

    train = feat[~feat["is_holdout"]].reset_index(drop=True)
    holdout = feat[feat["is_holdout"]].reset_index(drop=True)
    assert len(holdout) == 12

    cont_medians = train[CONT].median()
    cat_modes = train[CAT].mode().iloc[0]

    def impute(d):
        out = d.copy()
        out[CONT] = out[CONT].fillna(cont_medians)
        out[CAT] = out[CAT].fillna(cat_modes)
        return out

    train_imp = impute(train[CONT + CAT])
    holdout_imp = impute(holdout[CONT + CAT])
    for c in CAT:
        train_imp[c] = train_imp[c].astype("category")
        holdout_imp[c] = pd.Categorical(holdout_imp[c], categories=train_imp[c].cat.categories)
        holdout_imp[c] = holdout_imp[c].fillna(cat_modes[c])

    n_comp = 5
    famd = prince.FAMD(n_components=n_comp, rescale_with_mean=True, rescale_with_std=True,
                        random_state=42, engine="sklearn").fit(train_imp)

    train_coord = famd.row_coordinates(train_imp).values
    holdout_coord = famd.row_coordinates(holdout_imp).values
    eigen = famd.eigenvalues_
    pct_var = famd.percentage_of_variance_
    cum_var = famd.cumulative_percentage_of_variance_
    col_contrib = famd.column_contributions_

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
    with open(OUT_DIR / "artifacts_famd.pkl", "wb") as f:
        pickle.dump(artifacts, f)

    print(f"train n={len(train)}  holdout n={len(holdout)}")
    print(f"eigenvalues (top5): {np.round(eigen[:5], 4).tolist()}")
    print(f"cumulative %var (top3): {round(float(cum_var[2]), 2)}")
    print(f"train C-index: {round(train_cindex,4)}  CV C-index: {round(cv_cindex,4)}  "
          f"held-out(12): {hold_cindex}")
    return artifacts


if __name__ == "__main__":
    train_all_famd()
