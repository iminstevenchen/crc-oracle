"""匯出 FAMD 版前端要嵌入的 JSON（column contributions、族群散佈點、held-out驗證）。"""
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

with open(BASE_DIR / "artifacts_famd.pkl", "rb") as f:
    A = pickle.load(f)

OUT = BASE_DIR / "artifacts"
OUT.mkdir(exist_ok=True)
CONT, CAT = A["CONT"], A["CAT"]

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

n_pc = 5
col_contrib = A["col_contrib"]  # index: 每個類別的每個level或連續變數名稱；columns: 0..n_pc-1

famd_coef = {
    "version": "v3-famd",
    "method": "FAMD (mixed continuous + categorical), prince 0.20.1",
    "n_continuous": len(CONT),
    "n_categorical": len(CAT),
    "features": {
        "continuous": [{"code": c, "label_zh": FEATURE_LABELS_ZH[c]} for c in CONT],
        "categorical": [{"code": c, "label_zh": FEATURE_LABELS_ZH[c]} for c in CAT],
    },
    "eigen": {
        "eigenvalues": np.round(A["eigen"][:n_pc], 4).tolist(),
        "pct_variance": np.round(A["pct_var"][:n_pc], 2).tolist(),
        "cumulative_pct_top3": round(float(A["cum_var"][2]), 2),
        "note": "FAMD的變異百分比計算方式跟線性PCA不同(分母含類別指標矩陣的總慣性)，"
                "數字不能直接跟PCA版的explained_variance_ratio相比。",
    },
    "column_contributions": {
        f"PC{i+1}": {str(idx): round(float(col_contrib.iloc[j, i]), 4)
                     for j, idx in enumerate(col_contrib.index)}
        for i in range(n_pc)
    },
    "cox_model": {
        "encoding": "連續變數z-score + 類別變數one-hot(drop-first)",
        "train_cindex": round(float(A["train_cindex"]), 4),
        "cv5_cindex": round(float(A["cv_cindex"]), 4),
        "holdout12_cindex": round(float(A["hold_cindex"]), 4) if A["hold_cindex"] is not None else None,
    },
}
with open(OUT / "famd_coefficients_v3.json", "w", encoding="utf-8") as f:
    json.dump(famd_coef, f, ensure_ascii=False, indent=2)

# ---------- population scatter (FAMD座標 PC1-3) ----------
train = A["train"]
coord = A["train_coord"]
scatter = []
for i in range(len(train)):
    stg = train["TNM_stage"].iloc[i]
    ag = train["age_group"].iloc[i]
    scatter.append({
        "pc1": round(float(coord[i, 0]), 3),
        "pc2": round(float(coord[i, 1]), 3),
        "pc3": round(float(coord[i, 2]), 3),
        "stage": None if pd.isna(stg) else str(stg),
        "age_group": None if pd.isna(ag) else str(ag),
    })
with open(OUT / "population_scatter_famd_v3.json", "w", encoding="utf-8") as f:
    json.dump({"n": len(scatter), "points": scatter}, f, ensure_ascii=False)

# ---------- held-out 12 例 ----------
holdout = A["holdout"]
hold_risk = A["hold_risk"]
detail = []
for i in range(len(holdout)):
    detail.append({
        "SER_NO": int(holdout["SER_NO"].iloc[i]),
        "os_time_days": int(holdout["os_time_days"].iloc[i]),
        "os_event": int(holdout["os_event"].iloc[i]),
        "predicted_risk_score": round(float(hold_risk[i]), 4),
    })
with open(OUT / "holdout12_validation_famd_v3.json", "w", encoding="utf-8") as f:
    json.dump({
        "n": len(detail),
        "cindex": round(float(A["hold_cindex"]), 4) if A["hold_cindex"] is not None else None,
        "note": "held-out僅12例，僅供交叉檢查，正式驗證請以5-fold CV為主。",
        "patients": detail,
    }, f, ensure_ascii=False, indent=2)

print("exported:")
print(" -", OUT / "famd_coefficients_v3.json")
print(" -", OUT / "population_scatter_famd_v3.json")
print(" -", OUT / "holdout12_validation_famd_v3.json")
