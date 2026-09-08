"""匯出前端要嵌入的 JSON 檔（PCA係數、族群散佈點、held-out驗證結果）。"""
import json
import pickle
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

with open(BASE_DIR / "artifacts.pkl", "rb") as f:
    A = pickle.load(f)

OUT = BASE_DIR / "artifacts"
OUT.mkdir(exist_ok=True)
FEATURES = A["FEATURES"]

FEATURE_LABELS_ZH = {
    "AGE": "診斷年齡", "SEX": "性別(1=男)", "BMI": "BMI",
    "TNM_stage": "TNM總分期", "T_stage": "T分期", "N_stage": "N分期", "M_stage": "M分期",
    "ELN": "摘除淋巴結數", "PLN": "陽性淋巴結數", "LN_ratio": "淋巴結陽性比率",
    "site_group": "腫瘤側別(0右側/1左側/2直腸)", "HT_adenoca": "腺癌型組織學",
    "HG_grade": "分化程度(1好/2中/3差)", "WID": "腫瘤寬度(cm)", "LEN": "腫瘤長度(cm)",
    "GA_infiltrative": "浸潤型外觀", "CI": "環周侵犯", "RM": "切除margin(cm)",
    "IR_curative": "根治性切除", "OT_emergency": "急診手術",
    "LAB_CEA_log": "術前CEA(log)", "LAB_ALB": "術前白蛋白", "LAB_HB": "術前血色素",
}

# ---------- 1. PCA 係數 ----------
pca_coef = {
    "version": "v3",
    "n_features": len(FEATURES),
    "features": [{"code": f, "label_zh": FEATURE_LABELS_ZH[f]} for f in FEATURES],
    "standardization": {
        "median_impute": A["medians"].round(4).to_dict(),
        "mean": A["mu"].round(4).to_dict(),
        "std": A["sigma"].round(4).to_dict(),
    },
    "pca": {
        "n_components": A["n_pc"],
        "explained_variance_ratio": np.round(A["explained_var"][:A["n_pc"]], 4).tolist(),
        "cumulative_top3": round(float(np.cumsum(A["explained_var"][:3])[-1]), 4),
        "loadings": {
            f"PC{i+1}": {f: round(float(A["Vt"][i][j]), 4) for j, f in enumerate(FEATURES)}
            for i in range(A["n_pc"])
        },
    },
    "cox_model": {
        "coefficients": {k: round(float(v), 4) for k, v in A["cph"].params_.to_dict().items()},
        "train_cindex": round(float(A["train_cindex"]), 4),
        "cv5_cindex": round(float(A["cv_cindex"]), 4),
        "holdout12_cindex": round(float(A["hold_cindex"]), 4) if A["hold_cindex"] is not None else None,
    },
}
with open(OUT / "pca_coefficients_v3.json", "w", encoding="utf-8") as f:
    json.dump(pca_coef, f, ensure_ascii=False, indent=2)

# ---------- 2. 全體病患 PC1-PC3 散佈點（供PCA空間散佈圖）----------
train = A["train"]
train_pc = A["train_pc"]
scatter = [
    {
        "pc1": round(float(train_pc[i, 0]), 3),
        "pc2": round(float(train_pc[i, 1]), 3),
        "pc3": round(float(train_pc[i, 2]), 3),
        "stage": None if pd_isna(train["TNM_stage"].iloc[i]) else int(train["TNM_stage"].iloc[i]),
    }
    for i in range(len(train))
] if False else None

import pandas as pd
def pd_isna(x):
    return pd.isna(x)

scatter = []
for i in range(len(train)):
    stg = train["TNM_stage"].iloc[i]
    scatter.append({
        "pc1": round(float(train_pc[i, 0]), 3),
        "pc2": round(float(train_pc[i, 1]), 3),
        "pc3": round(float(train_pc[i, 2]), 3),
        "stage": None if pd.isna(stg) else int(stg),
    })
with open(OUT / "population_scatter_v3.json", "w", encoding="utf-8") as f:
    json.dump({"n": len(scatter), "points": scatter}, f, ensure_ascii=False)

# ---------- 3. held-out 12 例驗證明細 ----------
holdout = A["holdout"]
hold_risk = A["hold_risk"]
holdout_detail = []
for i in range(len(holdout)):
    holdout_detail.append({
        "SER_NO": int(holdout["SER_NO"].iloc[i]),
        "os_time_days": int(holdout["os_time_days"].iloc[i]),
        "os_event": int(holdout["os_event"].iloc[i]),
        "predicted_risk_score": round(float(hold_risk[i]), 4),
    })
with open(OUT / "holdout12_validation_v3.json", "w", encoding="utf-8") as f:
    json.dump({
        "n": len(holdout_detail),
        "cindex": round(float(A["hold_cindex"]), 4) if A["hold_cindex"] is not None else None,
        "note": "held-out僅12例，C-index信賴區間極寬，僅供交叉檢查，正式驗證請以5-fold CV為主。",
        "patients": holdout_detail,
    }, f, ensure_ascii=False, indent=2)

print("exported:")
print(" -", OUT / "pca_coefficients_v3.json")
print(" -", OUT / "population_scatter_v3.json")
print(" -", OUT / "holdout12_validation_v3.json")
