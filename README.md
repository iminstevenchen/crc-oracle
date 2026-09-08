# 腸命天機 · Project CRC-ORACLE

> **Real-World Intelligence for Personalized Colorectal Cancer Outcomes**
> 大腸直腸癌相似病患智慧查詢 — 用一句自然語言描述病患，找出資料庫中最相似的一群病患，並給出存活曲線與術後結果。

線上 Demo：https://crc-oracle.vercel.app ｜ StanCode SC201 專題

## 團隊分工
| 成員 | 角色 |
|---|---|
| 陳繹中（組長） | 林口長庚大腸直腸外科主治醫師 — 專案協調、臨床驗證、資料來源、UI 方向 |
| 陳奕閔 Steven | UI/UX 與前端整合 |
| 鄭文森 Kevin、Sean | FAMD 降維與存活分析 |

---

## 資料夾導覽

```
CRC-ORACLE 腸命天機/
├── README.md                       ← 你在這裡 · you are here
├── 01_data_資料/                   原始資料與 codebook · raw data & codebook
├── 02_model_模型/                  FAMD 訓練管線與模型產物 · training pipeline & artifacts
│   ├── current_famd_age-layered_年齡分層版/   現行模型 · current model
│   └── archive_famd_20260823_舊版/            封存模型 · archived model
├── 03_website_網站/                單檔網站 + Vercel 部署 · single-file site & deployment
│   └── deploy/                     ← GitHub repo 根目錄 · the GitHub repo root
├── 04_docs_文件/                   報告與交接文件 · reports & handover docs
│   └── archive_封存/
├── 05_slides_簡報/                 簡報檔 · slide decks
│   └── archive_封存/
└── 99_assets_素材/                 截圖素材 · screenshots
```

> ℹ️ **GitHub 上只有 `03_website_網站/deploy/` 這一層**（`index.html`、`README.md`、`DEPLOY.md`、`.gitignore`、`.nojekyll`）。
> 其餘資料夾只存在於本機。

### 01_data_資料
| 檔案 | 說明 |
|---|---|
| `癌症資料20072023_AI去識別擬真版_v2.csv` | 原始資料，12,250 列 × 197 欄（AI 去識別擬真版） |
| `癌症資料_欄位定義20260612.xlsx` | 欄位定義 |
| `癌症資料_資料字典與codebook.xlsx` | 官方 codebook（自然語言解析的對照依據） |

> ⚠️ 兩份資料來源要分清楚：
> - **訓練管線**讀的是 `02_model_模型/current_famd_age-layered_年齡分層版/` 底下的 **xlsx part1~3**（`train_v3.py` 的 `load_raw()`）
> - **`export_frontend_famd_blob.py`** 讀的是 **CSV**（取 LOS / MT 兩個欄位）
>
> 三個位置的 CSV 與 xlsx md5 都相同，內容一致（12,250 列 × 197 欄）。清理建議見 `04_docs_文件/資料夾清理清單-20260903.md`。

### 02_model_模型
| 資料夾 | 狀態 | 說明 |
|---|---|---|
| `current_famd_age-layered_年齡分層版/` | **現行** | Kevin 的 age-layer FAMD（原名 `5 age layer`）。10 連續 + 13 類別變項，cv5 C-index **0.7995** |
| `archive_famd_20260823_舊版/` | 封存 | 8/22 舊版 FAMD（原名 `FAMD_V3_20260823`）。11 連續 + 12 類別，cv5 0.7978。**線上網站目前仍跑這一版** |

**`current_famd_age-layered_年齡分層版/` 裡的檔案分兩套管線 —— 網站只用 FAMD 那套：**

| 檔案 | 網站有用到 | 說明 |
|---|---|---|
| `train_famd_v3.py` | ✅ | FAMD 訓練主程式 |
| `artifacts_famd.pkl` | ✅ | 訓練產物（FAMD 編碼器 + 全體座標 + Cox） |
| `famd_coefficients_v3.json` | ✅ | PC1–PC5 解釋變異與欄位貢獻度 |
| `export_frontend_famd_blob.py` | ✅ | **從 pkl 匯出網站的 `F` blob**（見下方「換模型流程」） |
| `export_frontend_data_famd.py` | — | Kevin 原本的展示用匯出（散佈圖 / 係數 / holdout） |
| `similarity_api_famd.py` | — | Flask 版查詢 API（網站是純前端，不呼叫它） |
| `validate_holdout.py` | — | 12 人 holdout 驗證（簡報數字的佐證） |
| `train_v3.py` | ⚠️ | PCA 版訓練程式，但 `train_famd_v3.py` 會 `from train_v3 import load_raw, clean999, HOLDOUT_IDS` —— **必要相依，不可刪** |
| `癌症資料…_v2_part1~3.xlsx` | ⚠️ | `load_raw()` 實際讀的訓練資料來源（不是 CSV）—— **不可刪** |
| `artifacts.pkl` / `export_frontend_data.py` / `similarity_api.py` | ❌ | 更早的 **PCA** 管線，已被 FAMD 取代 |

### 03_website_網站
| 檔案 | 模型版本 | 說明 |
|---|---|---|
| `index_整合版_v4_age分層.html` | `v3-famd-age5` | **最新**，含 23 項手動輸入、PC1–PC5、300 人上限、半徑修正 |
| `index_整合版.html` | `v3-famd` | 舊版工作副本（＝目前線上版） |
| `deploy/` | `v3-famd` | Vercel 部署資料夾（git repo，remote 指向 `iminstevenchen/crc-oracle`） |

網站是**單一自包含 HTML**：12,196 位病患的資料與 FAMD 編碼器全部內嵌在 `const F={…}` 裡，離線可用、無後端。

### 04_docs_文件
| 檔案 | 說明 |
|---|---|
| `腸命天機_Project_CRC-ORACLE_Milestone_Report.docx` | 里程碑報告 |
| `PPT交接文件_給下一個對話.md` | 簡報製作交接說明 |
| `資料夾清理清單-20260903.md` | 重複／可刪檔案盤點 |
| `archive_封存/` | 8 月的三份進度報告 |

### 05_slides_簡報
| 檔案 | 說明 |
|---|---|
| `CRC-ORACLE_完整進度報告_含Steven介面_統一風格_20260826.pptx` | 全組合併版 |
| `CRC-ORACLE_進度報告_Steven介面_v4.pptx` | Steven 介面段落（19 頁） |
| `CRC-ORACLE_進度報告_完整三頁版.pptx` | 三頁濃縮版 |
| `簡報_驗證方法_Sean_第二版.pptx` | 驗證方法 |
| `archive_封存/` | v2、v3、Sean 第一版 |

---

## 常用流程

### A. 換模型 → 更新網站（Kevin 重訓之後）

```bash
cd "02_model_模型/current_famd_age-layered_年齡分層版"
python train_famd_v3.py                                    # 產生 artifacts_famd.pkl
python export_frontend_famd_blob.py \
       --html "../../03_website_網站/index_整合版_v4_age分層.html"   # 就地換掉網站的 F blob
```

`export_frontend_famd_blob.py` 一次匯出網站需要的全部：FAMD 編碼器（`V` / `prop` / `outer_mean` / `outer_scale` / `pc_sd` / `cat_categories` / `cat_modes`）＋ 每位病患的臨床與存活陣列。
Kevin 原本的 `export_frontend_data_famd.py` 只匯出展示用的三個 JSON，不含編碼器與病患陣列，所以網站無法只靠它運作。

**環境需求**：要在跑過 `train_famd_v3.py` 的同一個 Python 環境執行（pkl 內含 prince 的 FAMD 物件）。不需要 lifelines。

### B. 部署

```bash
cp "03_website_網站/index_整合版_v4_age分層.html" "03_website_網站/deploy/index.html"
cd "03_website_網站/deploy"
git add index.html && git commit -m "feat: 換上 age 分層 FAMD 模型"
git push                                                   # Vercel 自動重新部署
```

> ⚠️ `deploy/index.html` 目前有 **120 行未 commit 的本機修改**（`git diff --stat` 可看）。
> 覆蓋前先確認那些改動要不要保留：`cd 03_website_網站/deploy && git diff`。

---

## 技術重點

- **FAMD（Factor Analysis of Mixed Data）** — 同時處理連續與類別變項的降維。連續變項 z-score、類別變項 one-hot 後做 `(ind − p)/√p`，再經外層 StandardScaler，投影到 SVD 的 `V`。
- **相似族群搜尋** — 以標準化距離為半徑自適應擴張，直到累積死亡事件數 ≥ 20，人數夾在 30–300 之間。半徑可由使用者手動調整；半徑內無人時顯示誠實的空狀態，不會偷偷補最近 30 位。
- **存活分析** — Kaplan–Meier + Greenwood 95% CI；另呈現手術死亡率（MT）與中位術後住院天數。
- **模型品質** — Cox PH 的 5-fold CV C-index：舊版 0.7978 → age 分層版 **0.7995**（存活風險對年齡非線性，50–70 歲最低、80+ 最高）。

### 病患人數怎麼算出 12,196
```
12,250  原始列數（CSV / xlsx）
  − 42  追蹤天數 ≤ 0（同日進出、無真實追蹤資訊）
  − 12  holdout 驗證病例
─────
12,196  訓練樣本，也是網站上的數字
```
資料版本自 2026-08-19 起未變動；新舊模型用的是同一份資料（md5 已比對）。

### 網站 `F` blob 的隱藏編碼規則（反推自舊版，已寫進匯出腳本）
- `LOS`（術後住院天數）＝ CSV 的 `DD − OD`（民國日期），8 位缺日期存 `null`
- `MT` CSV 用 `1=否 / 2=是`，網站存 `0/1`（共 101 位）
- 「月」換算基準是 **30.4368**（不是 30.4375）

---

## 重要限制

目前使用 **v2 去識別擬真資料**（剔除 12 例 holdout，納入 12,196 位）。期別分層已呈合理臨床分離，但仍為去識別擬真資料，**僅供方法學與研究示範，不可作為臨床判讀或投稿依據**。網站頁面上已明確標註。

部署注意：`index.html` 內嵌全部病患資料，**公開網址 = 任何人都能下載這份資料**。合成版可以展示，但絕不可用同樣方式部署含真實病患資料的版本。Vercel 免費版可用 Settings → Deployment Protection 限制存取。
