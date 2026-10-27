# 部署到 Vercel

網站是單一 `index.html`（內嵌 12,196 位去識別合成病患與 FAMD 編碼器），加上 PWA 檔案（`manifest.webmanifest`、`sw.js`、`icons/`）。純靜態、不需 build。

## ⚠️ 部署前務必知道
`index.html` 內嵌了去識別**合成**病患資料。**公開網址 = 任何人都能下載這份資料。**
合成版可以展示；但**絕對不要**用同樣方式部署含真實病患資料的版本。

---

## 目前的部署方式（GitHub ↔ Vercel 自動部署）

- GitHub repo：`iminstevenchen/crc-oracle`，**repo 根目錄就是專案根目錄**。
- Vercel 專案：`gut-instinct`，網址 https://crc-oracle.vercel.app
- 發佈哪一層由根目錄 `vercel.json` 的 `outputDirectory: 03_website/deploy` 決定，**不靠 Vercel 後台的 Root Directory 設定**。
- `vercel.json` 同時替 `sw.js` 與 `manifest.webmanifest` 設定 headers（`sw.js` 不可被長時間快取）。

### 更新流程

```bash
# 在 repo 根目錄
git add 03_website/deploy/index.html          # 以及其他有改的檔案
git commit -m "feat: 更新模型"
git push origin main                          # Vercel 自動重新部署（約 1–2 分鐘）
```

更新模型或網頁後，把 `03_website/deploy/sw.js` 的 `VERSION` 加 1，已安裝的 PWA 才會丟掉舊快取。

> 換模型時的匯出指令見根目錄 `README.md` 的「常用流程 A」。

---

## 部署後檢查 PWA

1. 開 https://crc-oracle.vercel.app（改過後先 Cmd+Shift+R 強制重新整理）。
2. Chrome 開發者工具 → Application → Manifest：名稱「腸命天機」、三個圖示都載入。
3. Application → Service Workers：狀態為 *activated*。
4. 切到飛航模式再開一次，STEP 1→3 應可完整執行。

---

## 想加存取限制（建議）
Vercel 免費版的 **Deployment Protection → Vercel Authentication** 可限制只有你 Vercel 帳號／團隊成員登入才看得到（適合只給組員）。
專案 → Settings → Deployment Protection 開啟。完整密碼保護（給任意人一組密碼）需 Pro。

## 想改回不公開
最安全還是直接把 `index.html` 傳檔案給組員，不放任何公開網址。
