"""腸命天機 Gut Instinct · PCA v3 訓練管線.

=======================================
輸入：三份 v2 去識別擬真資料 part1/part2/part3.xlsx（合併後 12,250 筆、197 欄）
輸出：artifacts.pkl（給 similarity_api.py 載入）＋ artifacts/ 下的 JSON（給前端）

流程：
  1. 動態搜尋並合併同目錄（或指定目錄）下的 Excel 檔案，還原 ROC(民國)日期，計算 OS（總體存活）time/event
  2. 排除 12 例 held-out 病例（不參與訓練，只用於驗證）
  3. 從 197 欄挑出 23 個臨床特徵並工程化（BMI、LN ratio、CEA log 等）
  4. 中位數插補缺失值 → z-score 標準化（統計量只從訓練集計算，避免 leakage）
  5. SVD 做 PCA，取前 5 個主成分
  6. 用標準化後的 23 特徵做 CoxPH 模型，算 C-index（train / 5-fold CV / held-out 12）

注意：held-out 只有 12 例，其 C-index 僅供參考，信賴區間非常寬，
不能單獨拿來當作模型正式驗證的唯一依據；正式報告請以 5-fold CV 的
c-index 為主，held-out 數字作為額外的獨立抽樣檢查。
"""

import glob
import json
import os
import pickle
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

# 定義 12 例 Held-out 病例 ID (統一轉為字串避免型態不一致)
HOLDOUT_IDS = [
    str(i)
    for i in [
        604666,
        606660,
        602666,
        606663,
        604443,
        604447,
        608444,
        607444,
        611333,
        602333,
        604333,
        609333,
    ]
]

FEATURES = [
    "AGE",
    "SEX",
    "BMI",
    "TNM_stage",
    "T_stage",
    "N_stage",
    "M_stage",
    "ELN",
    "PLN",
    "LN_ratio",
    "site_group",
    "HT_adenoca",
    "HG_grade",
    "WID",
    "LEN",
    "GA_infiltrative",
    "CI",
    "RM",
    "IR_curative",
    "OT_emergency",
    "LAB_CEA_log",
    "LAB_ALB",
    "LAB_HB",
]

FEATURE_LABELS_ZH = {
    "AGE": "診斷年齡",
    "SEX": "性別(1=男)",
    "BMI": "BMI",
    "TNM_stage": "TNM總分期",
    "T_stage": "T分期",
    "N_stage": "N分期",
    "M_stage": "M分期",
    "ELN": "摘除淋巴結數",
    "PLN": "陽性淋巴結數",
    "LN_ratio": "淋巴結陽性比率",
    "site_group": "腫瘤側別(0右側/1左側/2直腸)",
    "HT_adenoca": "腺癌型組織學",
    "HG_grade": "分化程度(1好/2中/3差)",
    "WID": "腫瘤寬度(cm)",
    "LEN": "腫瘤長度(cm)",
    "GA_infiltrative": "浸潤型外觀",
    "CI": "環周侵犯",
    "RM": "切除margin(cm)",
    "IR_curative": "根治性切除",
    "OT_emergency": "急診手術",
    "LAB_CEA_log": "術前CEA(log)",
    "LAB_ALB": "術前白蛋白",
    "LAB_HB": "術前血色素",
}


def roc_to_dt(series: pd.Series) -> pd.Series:
    """民國年-月-日 字串 -> 西元 Timestamp，錯誤或缺值回傳 NaT。"""

    def conv(x):
        x = str(x)
        if x in ("nan", "None", ""):
            return pd.NaT
        try:
            y, m, d = x.split("-")
            return pd.Timestamp(year=int(y) + 1911, month=int(m), day=int(d))
        except Exception:
            return pd.NaT

    return series.apply(conv)


def load_raw(data_dir=None, file_pattern="*part*.xlsx") -> pd.DataFrame:
    """自動搜尋並讀取 Excel 檔案，支援相對路徑與跨平台執行。"""
    # 若未指定資料夾，預設抓取程式碼所在目錄
    if data_dir is None:
        data_dir = os.path.dirname(os.path.abspath(__file__))

    search_path = os.path.join(data_dir, file_pattern)
    files = sorted(glob.glob(search_path))

    if not files:
        print("\n" + "=" * 50)
        print(f"❌ [錯誤] 找不到符合條件的 Excel 檔案！")
        print(f"   搜尋路徑: {search_path}")
        print("   請確認 Excel 檔案是否已放置於程式資料夾中。")
        print("=" * 50 + "\n")
        raise FileNotFoundError(f"在 '{data_dir}' 中未找到符合 '{file_pattern}' 的檔案")

    print("\n" + "=" * 50)
    print(f"📁 找到 {len(files)} 個資料檔，準備讀取：")
    for f in files:
        file_name = os.path.basename(f)
        file_size_mb = os.path.getsize(f) / (1024 * 1024)
        print(f"  └─ {file_name} ({file_size_mb:.2f} MB)")
    print("=" * 50)

    df = pd.concat(
        [pd.read_excel(f, engine="openpyxl") for f in files], ignore_index=True
    )

    for col in ["OD", "DEATH_D", "LATESTUPD"]:
        df[col + "_dt"] = roc_to_dt(df[col])
    event_time = df["DEATH_D_dt"].where(
        df["DEATH_D_dt"].notna(), df["LATESTUPD_dt"]
    )
    df["os_time_days"] = (event_time - df["OD_dt"]).dt.days
    df["os_event"] = df["FOLLOW_ST"].isin([3, 4, 5, 6]).astype(int)

    # 剔除追蹤時間 <=0（同日進出、無真實追蹤資訊）的極少數病例
    df = df[df["os_time_days"] > 0].copy()
    print(f"✅ 資料載入完成！有效筆數：{len(df)} 筆\n")
    return df


def clean999(s: pd.Series) -> pd.Series:
    return s.where(~s.isin([999, 9999, 99999]), np.nan)


def map_T(v):
    return {
        0: 0,
        1: 1,
        2: 2,
        22: 2.5,
        3: 3,
        33: 3.5,
        32: 3.5,
        41: 4,
        42: 4.5,
        4: 4,
    }.get(v, np.nan)


def map_N(v):
    return {
        0: 0,
        1: 1,
        11: 1,
        12: 1.5,
        13: 1.7,
        2: 2,
        21: 2,
        22: 2.5,
        3: 3,
    }.get(v, np.nan)


def map_M(v):
    return {0: 0, 1: 1, 11: 1, 12: 1.3, 13: 1.6}.get(v, np.nan)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    feat = pd.DataFrame(index=df.index)

    # 轉為字串並去空白，確保比對精準
    feat["SER_NO"] = df["SER_NO"].astype(str).str.strip()

    feat["AGE"] = df["AGE"]
    feat["SEX"] = df["SEX"]
    h = clean999(df["HEIGHT"]) / 100.0
    w = clean999(df["WEIGHT"])
    feat["BMI"] = w / (h**2)
    feat["TNM_stage"] = df["TNM"].where(df["TNM"].isin([0, 1, 2, 3, 4]), np.nan)
    feat["T_stage"] = df["TMN_T"].apply(map_T)
    feat["N_stage"] = df["TMN_N"].apply(map_N)
    feat["M_stage"] = df["TMN_M"].apply(map_M)
    feat["ELN"] = df["ELN"].where(df["ELN"] <= 90, np.nan)
    feat["PLN"] = df["PLN"].where(df["PLN"] <= 90, np.nan)
    feat["LN_ratio"] = (feat["PLN"] / feat["ELN"].replace(0, np.nan)).clip(0, 1)

    def site_group(v):
        if v in (1, 2, 3, 4):
            return 0
        if v in (5, 6, 7):
            return 1
        if v == 8:
            return 2
        return np.nan

    feat["site_group"] = df["TL_1"].apply(site_group)
    feat["HT_adenoca"] = df["HT_1"].isin([1, 2, 3]).astype(float)
    feat["HG_grade"] = df["HG_1"].where(df["HG_1"].isin([1, 2, 3]), np.nan)
    feat["WID"] = clean999(df["WID_1"])
    feat["LEN"] = clean999(df["LEN_1"])
    feat["GA_infiltrative"] = df["GA_1"].isin([4, 7]).astype(float)
    feat["CI"] = df["CI"].where(df["CI"].isin([1, 2]), np.nan) - 1
    feat["RM"] = clean999(df["RM"])
    feat["IR_curative"] = (df["IR"] == 3).astype(float)
    feat["OT_emergency"] = (df["OT"] == 2).astype(float)
    feat["LAB_CEA_log"] = np.log1p(clean999(df["LAB_CEA"]).clip(upper=1000))
    feat["LAB_ALB"] = df["LAB_ALB"].where(df["LAB_ALB"].between(1, 6), np.nan)
    feat["LAB_HB"] = df["LAB_HB"].where(df["LAB_HB"].between(3, 20), np.nan)

    feat["os_time_days"] = df["os_time_days"]
    feat["os_event"] = df["os_event"]

    # 比對 HOLDOUT_IDS
    feat["is_holdout"] = feat["SER_NO"].isin(HOLDOUT_IDS)
    return feat


def train_all():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    df = load_raw(data_dir=base_dir)
    feat = build_features(df)

    train = feat[~feat["is_holdout"]].reset_index(drop=True)
    holdout = feat[feat["is_holdout"]].reset_index(drop=True)

    # 檢查是否確實匹配到 12 例 holdout
    if len(holdout) != 12:
        print(f"⚠️ [警告] 預期 held-out 應有 12 例，實際僅找到 {len(holdout)} 例！")
        print(f"找到的 ID: {holdout['SER_NO'].tolist()}")

    assert len(holdout) == 12, (
        f"held-out 應有12例，實際找到 {len(holdout)} 例，請確認 SER_NO 與 Excel 資料。"
    )

    medians = train[FEATURES].median()
    train_imp = train[FEATURES].fillna(medians)
    holdout_imp = holdout[FEATURES].fillna(medians)

    mu = train_imp.mean()
    sigma = train_imp.std().replace(0, 1.0)
    train_z = (train_imp - mu) / sigma
    holdout_z = (holdout_imp - mu) / sigma

    X = train_z.values
    x_mean = X.mean(axis=0)
    Xc = X - x_mean
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    explained_var = (S**2) / np.sum(S**2)
    n_pc = 5
    train_pc = Xc.dot(Vt[:n_pc].T)
    holdout_pc = (holdout_z.values - x_mean).dot(Vt[:n_pc].T)

    cox_df = train_z.copy()
    cox_df["os_time_days"] = train["os_time_days"].values
    cox_df["os_event"] = train["os_event"].values
    cph = CoxPHFitter(penalizer=0.05)
    cph.fit(cox_df, duration_col="os_time_days", event_col="os_event")
    train_cindex = cph.concordance_index_

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_risk = np.zeros(len(cox_df))
    for tr_idx, te_idx in kf.split(cox_df):
        m = CoxPHFitter(penalizer=0.05)
        m.fit(
            cox_df.iloc[tr_idx],
            duration_col="os_time_days",
            event_col="os_event",
        )
        oof_risk[te_idx] = m.predict_partial_hazard(cox_df.iloc[te_idx]).values
    cv_cindex = concordance_index(
        cox_df["os_time_days"], -oof_risk, cox_df["os_event"]
    )

    hold_df = holdout_z.copy()
    hold_df["os_time_days"] = holdout["os_time_days"].values
    hold_df["os_event"] = holdout["os_event"].values
    hold_risk = cph.predict_partial_hazard(hold_df).values
    try:
        hold_cindex = concordance_index(
            hold_df["os_time_days"], -hold_risk, hold_df["os_event"]
        )
    except ZeroDivisionError:
        hold_cindex = None

    artifacts = dict(
        FEATURES=FEATURES,
        medians=medians,
        mu=mu,
        sigma=sigma,
        x_mean=x_mean,
        Vt=Vt,
        n_pc=n_pc,
        explained_var=explained_var,
        train_pc=train_pc,
        train=train,
        cph=cph,
        train_cindex=train_cindex,
        cv_cindex=cv_cindex,
        hold_cindex=hold_cindex,
        holdout=holdout,
        holdout_pc=holdout_pc,
        hold_risk=hold_risk,
    )

    # 自動建立輸出目錄 (在當前 py 檔下的 outputs 資料夾)
    out_dir = os.path.join(base_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    save_path = os.path.join(out_dir, "artifacts.pkl")

    with open(save_path, "wb") as f:
        pickle.dump(artifacts, f)

    print("=" * 50)
    print(f"🎉 模型訓練與打包成功！")
    print(f"📦 成果檔案已儲存至: {save_path}")
    print(f"📊 訓練集數量: {len(train)} | Held-out 數量: {len(holdout)}")
    print(
        f"📈 累積解釋變異量 (PC1-3): {round(float(np.cumsum(explained_var[:3])[-1]), 4)}"
    )
    print(
        f"🏆 Train C-index: {round(train_cindex, 4)} | 5-Fold CV C-index: {round(cv_cindex, 4)} | Held-out C-index: {hold_cindex}"
    )
    print("=" * 50)

    return artifacts


if __name__ == "__main__":
    train_all()