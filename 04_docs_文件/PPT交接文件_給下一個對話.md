# CRC-ORACLE（腸命天機）簡報交接文件

給另一個 Claude 對話用，讓它能接手/延伸製作 Steven 負責的簡報部分，不需要重新問我一次所有背景。

## 1. 專案背景

- 專案：Project CRC-ORACLE（腸命天機），大腸直腸癌術後存活分析與相似病患查詢系統，StanCode 201 期末專題。
- 團隊：陳繹中（隊長／指導醫師）、鄭文森 Kevin（統計/FAMD模型）、Sean（驗證方法）、Steven 陳奕閔（我／UI-UX 前端負責人）。指導老師：李柏南 Po-Nan Li。
- Steven 負責前端網站（單一 HTML 檔）+ 簡報中「介面介紹、介面操作、介面顯示結果」三個部分。
- 簡報順序：**陳繹中的 3 頁 deck → Steven 的 deck（本文件對象）→ Sean 的「驗證方法」deck**。三份最後要合併，所以 Steven 的 deck 要獨立看得懂，也要跟陳繹中的視覺風格一致。
- 網站已部署：`crc-oracle.vercel.app`（GitHub ↔ Vercel Git 整合已修好，push 會自動部署）。

## 2. 目前已完成的簡報（v3）

檔案：`CRC-ORACLE_進度報告_Steven介面_v3.pptx`（在專案資料夾根目錄），4 頁：

1. **介面操作：三步驟查詢流程** — Step1輸入／Step2解析確認／Step3相似族群結果，三個瀏覽器窗格並排，用真實網站畫面內容重建（不是截圖，是照真實數字手工重繪的）。
2. **STEP 2 詳解：FAMD v3 完整 23 變數透明度** — 兩欄表格，左邊 11 個連續變數、右邊 12 個類別變數，每一列標示「使用者輸入」或「母體中位數/眾數代入」。
3. **STEP 3 詳解：FAMD v3 主成分的臨床意義** — PC1/PC2/PC3 三張卡片（真實 eigenvalue/貢獻度，不是舊版線性 PCA 的假數字）+ 模型版本說明 + 6 個 KPI。
4. **STEP 3 詳解：目標病患 vs 相似族群完整對照** — 23 變數逐一比對表（連續變數中位數/IQR、類別變數相符%）。

舊版 v2（只有 1 頁，三步驟並排但沒有 23 變數細節）也還留著，沒刪除。

## 3. 視覺風格（品牌規範，必須沿用）

從陳繹中原本的 3 頁 deck 用 PIL 取樣得到，v3 deck 也是用這組色：

| 用途 | Hex |
|---|---|
| 主色（標題、按鈕、header bar） | `2C5F8D` |
| 深色文字（NAVY） | `12213A` |
| 淺藍底（卡片背景） | `EAF3FC` |
| 灰色說明文字（MUT） | `5B6472` |
| 白 | `FFFFFF` |
| 綠色（正向數據，如存活率） | `1E824C` |
| 邊框灰 | `D8E0E8` |

- 版面：`pptxgenjs`，`pres.layout = "LAYOUT_WIDE"`（13.33"×7.5"）。
- 標題字型 Cambria 24-28pt bold（NAVY），內文 Calibri。
- Eyebrow 小標：`UI/UX · INTERFACE WALKTHROUGH`（Calibri 11pt bold BLUE，全大寫）。
- Footer 固定：`PROJECT CRC-ORACLE · UI/UX INTERFACE · STEVEN CHEN`（右下角，8pt MUT）。
- **不要用底線強調標題**、不要用色條/側邊條裝飾（AI 感）。用留白、卡片底色、陰影做區隔。
- 建置腳本在 `/sessions/hopeful-brave-einstein/mnt/outputs/steven_slides/build_final.js`（VM 內路徑，新對話的沙盒路徑可能不同，但邏輯可以整段複製參考）——用 `pptxgenjs` 手刻每張卡片/table，沒有用範本檔。

## 4. 系統技術背景（避免新對話瞎猜或幻覽）

- 核心引擎：**FAMD v3**（Factor Analysis of Mixed Data，`prince` 套件），23 個特徵：11 個連續（AGE, BMI, ELN摘除淋巴結數, PLN陽性淋巴結數, LN_ratio淋巴結陽性比率, WID腫瘤寬度, LEN腫瘤長度, RM切除margin, LAB_CEA_log, LAB_ALB術前白蛋白, LAB_HB術前血色素）+ 12 個類別（SEX, TNM_stage, T_stage, N_stage, M_stage, site_group腫瘤側別, HT_adenoca腺癌型組織學, HG_grade分化程度, GA_infiltrative浸潤型外觀, CI環周侵犯, IR_curative根治性切除, OT_emergency急診手術）。
- 網站的自然語言輸入只會主動收集 9 個欄位（年齡/性別/期別/部位/病理/分化/手術術式/目的/時機/CEA），其餘 14 個永遠用全體 12,196 位病患的中位數/眾數代入——**這是刻意的設計，簡報要誠實呈現，不要假裝醫師輸入了全部 23 個**。
- 相似病患搜尋：標準化距離（每個PC座標除以其標準差）由近到遠排序，累積死亡事件數達門檻（min_events=20）才停止擴張，人數夾在 [30, 100] 之間；醫師也可以手動拉桿指定距離半徑。
- 模型驗證數字（真實，可直接引用）：5-fold CV C-index **0.7978**（簡報寫「約0.798」），12例 held-out C-index **0.7568**（簡報寫「約0.757」），訓練樣本 **12,196** 位。
- FAMD 真實主成分資料（`famd_coefficients_v3.json`，勿用舊版16特徵PCA的26.7%/13.9%/8.0%）：
  - PC1 · 11.99%：主要載荷 TNM_stage(0.1227), M_stage(0.1007), IR_curative(0.084), N_stage(0.0745), LN_ratio(0.0606), T_stage(0.0592) → 「腫瘤分期／根治性軸」
  - PC2 · 6.36%：TNM_stage(0.1732), T_stage(0.1097), CI(0.0733), LAB_HB(0.0479), site_group(0.0416), LAB_ALB(0.0394) → 「腫瘤侵犯深度／體能狀態軸」
  - PC3 · 5.81%：TNM_stage(0.1667), N_stage(0.1134), site_group(0.087), RM(0.0778), T_stage(0.0455), LN_ratio(0.0427) → 「淋巴結侵犯／切除margin軸」
  - 前三軸累積解釋變異 24.15%（FAMD 的變異算法跟線性PCA不同，分母含類別指標矩陣總慣性，不能直接比較舊版PCA的explained_variance_ratio）。
- 手術死亡率＝`MT`欄位（出院前死亡=2），不是「30天死亡率」代理指標。

## 5. 範例病患（v3 deck 用的示範案例，可直接沿用）

輸入句：「68歲男性，第二期升結腸腺癌，中分化，前位切除，CEA 12.5」

- 使用者輸入 9 個：AGE=68, SEX=男性, TNM_stage=第II期, site_group=升結腸, HT_adenoca=是, HG_grade=中分化, IR_curative=是, OT_emergency=否, LAB_CEA_log=2.60(CEA≈12.5)
- 其餘14個母體代入：BMI=23.89, ELN=27.0, PLN=0.0, LN_ratio=0.0, WID=3.6, LEN=3.5, RM=99.0, LAB_ALB=4.2, LAB_HB=12.4, T_stage=T3, N_stage=N0, M_stage=M0, GA_infiltrative=否, CI=否
- 相似族群結果：66人，標準化距離半徑0.22，5年存活率81.6%(71–92)，手術死亡率0.0%(0/66)，中位住院8天(IQR 6–10)
- 完整23變數 vs 66人族群對照（連續中位數/IQR、類別相符%）——見 v3 deck 第4頁，或問我要完整表格資料可以再貼一次。

## 6. 給下一個對話的具體任務指示（依你實際需求填空）

如果是要「延伸/修改」現有4頁 deck：直接讀取 `CRC-ORACLE_進度報告_Steven介面_v3.pptx`，用 pptx skill 的「編輯既有檔案」流程（unzip → 改 slideN.xml → zip），沿用上面第3節的色票與字體規範。

如果是要「從頭做新的一份」：先確認你要涵蓋的內容範圍（是否還是三步驟介面+23變數透明度，還是要換主題），再用上面第4-5節的真實數字，不要編造新數字。任何新數字都應該來自 `/FAMD_V3_20260823/` 資料夾裡的 `artifacts_famd.pkl`／`famd_coefficients_v3.json`，用 Python 讀取後驗證，不要憑印象寫。

## 7. 重要原則（來自我的明確要求，務必遵守）

- **禁止 hallucination**：任何數字/百分比/變數名稱都必須來自真實檔案或程式計算結果，不能編。若不確定，重新跑一次 Python/Node 驗證。
- 「全部都顯示，ppt可以更多頁沒關係如果塞不下」——不要為了塞進單頁而閹割資訊完整度，寧可拆成更多頁。
- 完成後務必用 pptx skill 的 `validate.py` + 轉圖檢查（overflow/重疊/對齊）再交付，不要略過視覺QA。
