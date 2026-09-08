"""
Held-out 12例驗證：兩種角度
  1. Cox風險分數的排序能力 (C-index) + bootstrap 95% CI，看這個數字有多可信
  2. PCA/FAMD相似病例cohort的KM曲線，對每位held-out病患個別做校準檢查
     （這才是直接驗證「PCA找相似病例」這個功能本身，而不只是Cox模型）
"""
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from lifelines import KaplanMeierFitter
from lifelines.utils import concordance_index

BASE_DIR = Path(__file__).resolve().parent
np.random.seed(42)

# ---------------- 1. Bootstrap CI for held-out C-index ----------------
def bootstrap_cindex(times, events, risk, n_boot=3000):
    n = len(times)
    times, events, risk = np.array(times), np.array(events), np.array(risk)
    boots = []
    for _ in range(n_boot):
        idx = np.random.choice(n, n, replace=True)
        t, e, r = times[idx], events[idx], risk[idx]
        if e.sum() == 0 or e.sum() == n:
            continue
        try:
            c = concordance_index(t, -r, e)
            boots.append(c)
        except ZeroDivisionError:
            continue
    return np.array(boots)


for name, path in [("PCA線性版", "artifacts.pkl"), ("FAMD版", "artifacts_famd.pkl")]:
    with open(BASE_DIR / path, "rb") as f:
        A = pickle.load(f)
    holdout = A["holdout"]
    hold_risk = A["hold_risk"]
    point_c = A["hold_cindex"]
    boots = bootstrap_cindex(holdout["os_time_days"], holdout["os_event"], hold_risk)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"\n=== {name} ===")
    print(f"held-out(n=12, events=6) C-index = {point_c:.4f}")
    print(f"bootstrap 95% CI = [{lo:.3f}, {hi:.3f}]  (n_boot有效樣本={len(boots)})")
    print(f"5-fold CV C-index (n=12,196, 較可信) = {A['cv_cindex']:.4f}")

# ---------------- 2. 個別病患的cohort校準檢查（以PCA版為例）----------------
print("\n\n=== 個別held-out病患：cohort KM 校準檢查 (PCA版) ===")
with open(BASE_DIR / "artifacts.pkl", "rb") as f:
    A = pickle.load(f)

FEATURES = A["FEATURES"]
mu, sigma, x_mean, Vt, n_pc = A["mu"], A["sigma"], A["x_mean"], A["Vt"], A["n_pc"]
train = A["train"]
train_pc = A["train_pc"]
holdout = A["holdout"]
holdout_pc = A["holdout_pc"]

rows = []
for i in range(len(holdout)):
    q_pc = holdout_pc[i]
    d = np.linalg.norm(train_pc - q_pc, axis=1)
    idx = np.argsort(d)[:100]
    cohort = train.iloc[idx]
    kmf = KaplanMeierFitter().fit(cohort["os_time_days"], cohort["os_event"])
    t_obs = holdout["os_time_days"].iloc[i]
    e_obs = holdout["os_event"].iloc[i]
    # cohort 預測「活到病患實際追蹤時間」的機率
    try:
        pred_surv_at_tobs = float(kmf.survival_function_at_times(min(t_obs, cohort["os_time_days"].max())).values[0])
    except Exception:
        pred_surv_at_tobs = np.nan
    rows.append({
        "SER_NO": int(holdout["SER_NO"].iloc[i]),
        "obs_time_days": int(t_obs),
        "obs_event": int(e_obs),
        "cohort_pred_survival_at_obs_time": round(pred_surv_at_tobs, 3),
    })

cal = pd.DataFrame(rows)
print(cal.to_string(index=False))
print("""
判讀方式：
- obs_event=0（存活/被審查）的病患，cohort_pred_survival_at_obs_time 應該偏高
  （代表模型也認為「活到這個時間點」的機率不低，跟實際觀察一致）
- obs_event=1（死亡）的病患，cohort_pred_survival_at_obs_time 應該偏低
  （代表模型也認為「活到死亡發生的時間點」的機率不高，一致代表校準合理）
- 如果obs_event=1但預測存活機率仍很高，或obs_event=0但預測存活機率很低，
  代表這個相似病例cohort沒有抓對這位病患的風險層級，屬於「miscalibrated」的個案
""")
