# 部署到 Vercel

這個資料夾就是部署現成版：只有一個 `index.html`（整合版，內含真實 PCA/KM 引擎）。純靜態、不需 build。

## ⚠️ 部署前務必知道
`index.html` 內嵌了 12,250 筆去識別合成病患資料。**公開網址 = 任何人都能下載這份資料。**
這份是合成版可以展示；但**絕對不要**用同樣方式部署含真實病患資料的版本。

---

## 方法 A：Vercel CLI（最快，約 2 分鐘）
在這個 `deploy/` 資料夾裡開終端機，依序執行：

```bash
npm i -g vercel        # 安裝一次即可
vercel login           # 用 GitHub / Email 登入（會開瀏覽器）
vercel                 # 第一次部署，一路按 Enter 用預設值
vercel --prod          # 產生正式網址
```

跑完會給你一個網址，例如 `https://gut-instinct-xxxx.vercel.app`，把它傳給組員即可。

## 方法 B：從 GitHub 匯入（適合之後持續更新）
1. 把這個 `deploy/` 資料夾推上一個 GitHub repo（見下方「Git 已初始化」）。
2. 到 https://vercel.com → **Add New… → Project** → 選 **Import Git Repository**。
3. 選你的 repo → Framework Preset 選 **Other** → 直接 **Deploy**（不用改任何設定，Vercel 會自動把 `index.html` 放在網站根目錄）。
4. 完成後給你 `xxx.vercel.app` 網址。之後 push 到 GitHub 會自動重新部署。

### Git 已初始化
我已在此資料夾 `git init` 並 commit 好。接上 GitHub：
```bash
git remote add origin https://github.com/<你的帳號>/<repo名>.git
git branch -M main
git push -u origin main
```

---

## 想加存取限制（建議）
Vercel 免費版的 **Deployment Protection → Vercel Authentication** 可限制只有你 Vercel 帳號/團隊成員登入才看得到（適合只給組員）。
專案 → Settings → Deployment Protection 開啟。完整密碼保護（給任意人一組密碼）需 Pro。

## 想改回不公開
最安全還是直接把 `index.html` 傳檔案給組員，不放任何公開網址。
