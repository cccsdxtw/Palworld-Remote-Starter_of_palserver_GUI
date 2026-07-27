# 🌐 Palworld Remote Starter (for palserver GUI)

這是一款專為《幻獸帕魯 (Palworld)》專屬伺服器 ([palserver GUI](https://github.com/io-software-ai/palserver-gui)) 設計的「遠端啟動與前台控制系統」。  
讓你的朋友可以透過網頁自助啟動伺服器，同時賦予台主最高權限的安全防護與狀態監控！

> 目前版本：**V1.5.1**

## ✨ 核心特色

* 🚀 **自助遠端喚醒**：朋友造訪專屬網頁即可一鍵喚醒伺服器，不求人！
* 🛡️ **防干擾鎖定模式**：台主不想被打擾？一鍵鎖定連線，並自訂專屬阻擋留言。
* 💾 **面板官方 API 關機／備份**：自動讀取 `~/.palserver-agent/token`，呼叫與面板按鈕相同的 API（含 `worldGuid`），不再誤打 400。
* 🔢 **REST API 只填埠號**：對照面板「REST API：啟用 (8213)」直接填 `8213` 即可；舊版完整網址會在啟動時自動遷移成埠號。
* 🌙 **自動／手動深度休眠**：閒置達標後依序存檔 → 備份 → 停止；**確認遊戲行程真正停妥後**才關閉 `palserver-agent`。
* ⏱️ **自動休眠防循環**：進入休眠後暫停計時，需訪客喚醒後才重新開始，避免無限關機迴圈。
* ⚙️ **初次設定精靈**：超友善 GUI 介面，免改程式碼！第一次啟動自動引導填寫 IP 與密碼。
* 🔗 **無縫連動**：支援自動偵測並喚醒本機端背景的 `palserver-agent`。

## 🛠️ 如何安裝與使用 (給伺服器主)

### 1. 初次設定
* 將打包好的 EXE（或 `server_web_api_open.py`）放到你喜歡的資料夾並執行。
* 畫面會彈出「初次設定精靈」，請依序填寫你的：
  * 伺服器名稱
  * 對外連線 IP 與 Port
  * 管理員密碼 (AdminPassword)
  * palserver GUI 網址（預設 `http://localhost:8250`）
  * REST API 網址（預設 `http://127.0.0.1:8213`）
* 點擊儲存後，系統會自動生成 `config.json`，並將控制台常駐於系統右下角工具列。

### 2. 開放連線
* 將你的前台網址 (預設為 `http://你的IP:5000/start`) 分享給社群或朋友。
* 朋友輸入暱稱後，系統就會自動在背景幫他們點擊啟動伺服器！

## ⚠️ 注意事項與系統需求

* 伺服器必須開啟 **REST API** 功能，才能正確抓取線上人數與執行安全關機。
* 本專案底層依賴 Chrome 瀏覽器進行自動化背景喚醒操作，請確保主機端已安裝 Google Chrome。
* **千萬不要**將你填好密碼的 `config.json` 檔案上傳到網路上！
* 自動休眠建議設 **15～30 分鐘**（設 `0` 可停用）；測試時勿設成 `1` 分鐘以免頻繁觸發。

### ⚠️ 必備前置作業：安裝 ChromeDriver (網頁驅動器)
理論上他說會自動下載 但我用的時候他是沒有自動 所以  
本程式底層依賴自動化技術來操控面板，因此需要配合 **ChromeDriver** 才能正常運作！如果你沒有放置這個檔案，程式啟動時會報錯。

1. 請先打開你的 Google Chrome 瀏覽器，點擊右上角三個點 ➡️ **說明** ➡️ **關於 Google Chrome**，確認你的 Chrome 版本數字 (例如 127.0.x.x)。
2. 前往 [Chrome for Testing 官方下載頁](https://googlechromelabs.github.io/chrome-for-testing/)，找到對應版本的 `chromedriver-win64.zip` 並下載。
3. 下載後解壓縮，將裡面的 **`chromedriver.exe`** 檔案，**直接跟本程式的 EXE 檔放在同一個資料夾裡面** 即可！

## 📦 倉庫
https://github.com/cccsdxtw/Palworld-Remote-Starter_of_palserver_GUI
