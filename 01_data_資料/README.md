# 01_data_資料 (data)

**This folder contains no patient data on GitHub.** The data files live only on the team's local machines and are excluded by `.gitignore`; they have never been committed to this repository.

| Local file (not in this repo) | What it is |
|---|---|
| `癌症資料20072023_AI去識別擬真版_v2.csv` | *Cancer data 2007–2023, AI de-identified synthetic version, v2.* 12,250 rows × 197 columns |
| `癌症資料_欄位定義20260612.xlsx` | *Column definitions* |
| `癌症資料_資料字典與codebook.xlsx` | *Data dictionary / codebook* |

The dataset is an **AI de-identified synthetic version** prepared by the clinical lead. It contains no real patient records, names or contact details, and is for methodology demonstration only.

One thing to know: the published site (`03_website/deploy/index.html`) embeds a row-level matrix of this synthetic dataset (a serial number, survival time and event, and the model's 23 clinical variables per record) so that it can run without a backend. See the "Limitations" section of the root [README](../README.md).

---

**此資料夾在 GitHub 上不含任何病患資料。** 資料檔只存在團隊的本機，已被 `.gitignore` 排除，從未提交到這個 repo。資料是臨床負責人提供的「AI 去識別化擬真版」，不含真實病患紀錄、姓名或聯絡資料，僅供方法示範。網站（`index.html`）為了在沒有後端的情況下運作，內嵌了這份擬真資料的逐筆矩陣（流水號、存活時間與事件、23 項臨床變數）。
