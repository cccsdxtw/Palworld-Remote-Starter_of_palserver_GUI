import os
import sys
import time
import glob
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox
import json
import winsound  
import requests  
from requests.auth import HTTPBasicAuth
from flask import Flask, request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image, ImageDraw
import pystray

# ==========================================
# ⚙️ 設定檔與全域變數區
# ==========================================
CONFIG_FILE = "config.json"
SERVER_NAME = ""
SERVER_IP_PORT = ""
ADMIN_PASSWORD = ""
REST_API_URL = ""
GUI_URL = ""

is_blocking = False
block_message = "台主正在打積分，暫時不開放！"
window = None
log_box = None

app = Flask(__name__)

# ==========================================
# 🌟 設定與讀取系統
# ==========================================
def run_setup_wizard(config_path):
    setup_win = tk.Tk()
    setup_win.title("帕魯 API - 初次設定精靈")
    setup_win.geometry("400x520")
    setup_win.configure(bg="#f0f0f0")

    try:
        if os.path.exists(r"C:\Users\DontHow\Desktop\鐵.ico"):
            setup_win.iconbitmap(r"C:\Users\DontHow\Desktop\鐵.ico")
    except Exception:
        pass

    tk.Label(setup_win, text="🚀 歡迎使用伺服器前台系統", font=("微軟正黑體", 14, "bold"), bg="#f0f0f0", fg="#03A9F4").pack(pady=20)
    tk.Label(setup_win, text="偵測到您是第一次執行，請填寫基本設定：", font=("微軟正黑體", 10), bg="#f0f0f0").pack(pady=5)

    fields = [
        ("伺服器名稱 (顯示於網頁)", "例如：我的帕魯世界"),
        ("遊戲連線 IP 與 Port", "例如：127.0.0.1:8211"),
        ("管理員密碼 (AdminPassword)", ""),
        ("伺服器面板網址", "http://localhost:8250"),
        ("REST API 網址", "http://127.0.0.1:8213")
    ]

    entries = []
    for text, default_val in fields:
        frame = tk.Frame(setup_win, bg="#f0f0f0")
        frame.pack(fill=tk.X, padx=40, pady=5)
        tk.Label(frame, text=text, font=("微軟正黑體", 9, "bold"), bg="#f0f0f0").pack(anchor="w")
        entry = tk.Entry(frame, font=("微軟正黑體", 10))
        entry.insert(0, default_val)
        entry.pack(fill=tk.X)
        entries.append(entry)

    def save_and_start():
        new_config = {
            "SERVER_NAME": entries[0].get(),
            "SERVER_IP_PORT": entries[1].get(),
            "ADMIN_PASSWORD": entries[2].get(),
            "GUI_URL": entries[3].get(),
            "REST_API_URL": entries[4].get()
        }
        
        if not new_config["ADMIN_PASSWORD"]:
            messagebox.showwarning("警告", "強烈建議輸入管理員密碼，否則無法使用線上人數與安全關機功能！", parent=setup_win)
            
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            setup_win.destroy()  
        except Exception as e:
            messagebox.showerror("錯誤", f"無法建立設定檔：{e}", parent=setup_win)

    tk.Button(setup_win, text="💾 儲存設定並啟動", bg="#4CAF50", fg="white", font=("微軟正黑體", 11, "bold"), command=save_and_start, relief="flat", padx=10, pady=5).pack(pady=20)

    def on_closing():
        os._exit(0)  

    setup_win.protocol("WM_DELETE_WINDOW", on_closing)
    setup_win.mainloop()

def load_config_and_init():
    global SERVER_NAME, SERVER_IP_PORT, ADMIN_PASSWORD, REST_API_URL, GUI_URL
    
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    config_path = os.path.join(base_path, CONFIG_FILE)
    
    if not os.path.exists(config_path):
        run_setup_wizard(config_path)
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            
        SERVER_NAME = cfg.get("SERVER_NAME", "預設伺服器")
        SERVER_IP_PORT = cfg.get("SERVER_IP_PORT", "127.0.0.1:8211")
        ADMIN_PASSWORD = cfg.get("ADMIN_PASSWORD", "")
        REST_API_URL = cfg.get("REST_API_URL", "http://127.0.0.1:8213")
        GUI_URL = cfg.get("GUI_URL", "http://localhost:8250")
    except Exception as e:
        print(f"讀取設定檔失敗: {e}")
        os._exit(1)

# ==========================================
# 🛠️ 核心功能區
# ==========================================
def log_to_gui(msg, play_sound=False):
    if window and log_box:
        current_time = time.strftime("%H:%M:%S")
        window.after(0, lambda: log_box.insert(tk.END, f"[{current_time}] {msg}"))
        window.after(0, lambda: log_box.yview(tk.END))
        if play_sound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except:
                pass

def get_server_uptime():
    if not ADMIN_PASSWORD:
        return "未設定密碼"
    try:
        resp = requests.get(f"{REST_API_URL}/v1/api/metrics", auth=HTTPBasicAuth("admin", ADMIN_PASSWORD), timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            uptime_sec = int(data.get("uptime", 0))
            if uptime_sec == 0:
                return "剛剛啟動"
            mins = uptime_sec // 60
            if mins >= 60:
                return f"{mins // 60} 小時 {mins % 60} 分鐘"
            elif mins == 0:
                return "不到 1 分鐘"
            else:
                return f"{mins} 分鐘"
    except Exception:
        pass
    return "未知 (抓取失敗)"

def get_player_count():
    if not ADMIN_PASSWORD:
        return "未設定密碼"
    try:
        resp = requests.get(f"{REST_API_URL}/v1/api/metrics", auth=HTTPBasicAuth("admin", ADMIN_PASSWORD), timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return str(data.get("currentplayernum", 0))
    except Exception:
        pass
    return "抓取失敗"

def safe_shutdown_task():
    if not ADMIN_PASSWORD:
        log_to_gui("❌ 關機失敗：未設定管理員密碼", play_sound=True)
        return
    try:
        log_to_gui("💾 正在強制儲存世界存檔...")
        requests.post(f"{REST_API_URL}/v1/api/save", auth=HTTPBasicAuth("admin", ADMIN_PASSWORD), timeout=5)
        time.sleep(2)
        
        log_to_gui("🛑 正在發送關機指令...")
        data = {"waittime": 5, "message": "Server is shutting down by Admin."}
        requests.post(f"{REST_API_URL}/v1/api/stop", json=data, auth=HTTPBasicAuth("admin", ADMIN_PASSWORD), timeout=5)
        
        log_to_gui("✅ 伺服器已安全關機！", play_sound=True)
    except Exception:
        log_to_gui(f"❌ 關機指令失敗: 伺服器可能已關閉", play_sound=True)

def check_streaming():
    tasks = os.popen('tasklist').read().lower()
    if 'obs64.exe' not in tasks and 'obs.exe' not in tasks:
        return "<span style='color: #4CAF50;'>🟢 目前沒有開實況，網路資源充足！</span>"
    try:
        log_dir = os.path.join(os.getenv('APPDATA'), 'obs-studio', 'logs')
        if not os.path.exists(log_dir):
            return "<span style='color: #4CAF50;'>🟢 OBS 準備中 (未開始實況)</span>"
        list_of_files = glob.glob(os.path.join(log_dir, '*.txt'))
        if not list_of_files:
            return "<span style='color: #4CAF50;'>🟢 OBS 準備中 (未開始實況)</span>"
        latest_file = max(list_of_files, key=os.path.getmtime)
        is_active = False
        with open(latest_file, 'r', encoding='utf-8') as f:
            for line in f:
                if "Output 'adv_stream': started" in line or "Output 'simple_stream': started" in line:
                    is_active = True
                elif "Output 'adv_stream': stopped" in line or "Output 'simple_stream': stopped" in line:
                    is_active = False
        if is_active:
            return "<span style='color: #FF5252;'>🔴 實況運作中！可能會微 LAG 喔！</span>"
        else:
            return "<span style='color: #4CAF50;'>🟢 OBS 開啟中，未實況，資源充足！</span>"
    except:
        return "<span style='color: #4CAF50;'>🟢 目前網路資源充足！</span>"

def run_web_automation(visitor_name, visitor_ip):
    global is_blocking, block_message, SERVER_NAME, SERVER_IP_PORT, GUI_URL
    
    log_to_gui(f"🔔 訪客 {visitor_name} (IP: {visitor_ip}) 造訪了網頁！", play_sound=True)
    
    if is_blocking:
        log_to_gui(f"🛡️ 已攔截 {visitor_name} 的啟動請求")
        html_response = f"""
        <!DOCTYPE html>
        <html>
        <head><title>伺服器鎖定中</title><meta charset="utf-8"></head>
        <body style="background-color: #121212; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
            <div style="background-color: #1e1e1e; color: white; padding: 40px; border-radius: 20px; width: 350px; text-align: center; border: 1px solid #FF5252; box-shadow: 0 0 25px rgba(255, 82, 82, 0.4);">
                <h2 style="margin-top: 0; color: #FF5252;">⛔ 伺服器暫時鎖定</h2>
                <hr style="border: 1px solid #333; margin-bottom: 20px;">
                <p style="font-size: 1.1em;"><strong>嗨，{visitor_name}，台主留言：</strong></p>
                <p style="background: #2a2a2a; padding: 15px; border-radius: 10px; line-height: 1.6; color: #FFC107; font-weight: bold;">{block_message}</p>
                <p style="font-size: 0.9em; color: #777; margin-top: 30px;">請稍後再試，或聯絡台主。</p>
            </div>
        </body>
        </html>
        """
        return html_response, 200

    driver = None 
    try:
        options = Options()
        options.headless = True 
        
        # === 🚀 神級防呆進階版：優先找旁邊，找不到就用系統的 ===
        if getattr(sys, 'frozen', False):
            current_dir = os.path.dirname(sys.executable)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
        driver_path = os.path.join(current_dir, "chromedriver.exe")
        
        # 判斷：如果旁邊有放，就強制用旁邊的
        if os.path.exists(driver_path):
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=options)
        else:
            # 如果旁邊沒放，就放手讓 Selenium 去抓你原本安裝過的環境！
            driver = webdriver.Chrome(options=options)
        # ====================================================
        
        driver.get(GUI_URL)
        wait_short = WebDriverWait(driver, 3) 
        
        log_to_gui(f"🔍 正在為 {visitor_name} 尋找『{SERVER_NAME}』...")
        try:
            xpath_server_card = f"//*[contains(text(), '{SERVER_NAME}')]"
            server_card = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_server_card)))
            driver.execute_script("arguments[0].click();", server_card)
        except Exception as e:
            log_to_gui(f"❌ 錯誤：畫面上找不到『{SERVER_NAME}』")
            raise e
            
        time.sleep(1.5)
        
        try:
            xpath_start_btn = "//button[contains(., '啟動') and not(contains(., '未'))]"
            start_btn = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_start_btn)))
            is_running = False
        except:
            is_running = True

        if is_running:
            uptime = get_server_uptime()
            players = get_player_count() 
            
            if players.isdigit():
                player_display = f"<br><span style='font-size: 0.9em; color: #00E676;'>👥 目前線上人數：{players} 人</span>"
            else:
                player_display = f"<br><span style='font-size: 0.9em; color: #777;'>👥 線上人數：{players}</span>"

            status_msg = f"<span style='color: #4CAF50;'>✅ 伺服器已在運作中！<br><span style='font-size: 0.9em; color: #B0BEC5;'>⏱️ 本次已開機：{uptime}</span>{player_display}<br>不要猶豫，直接連線吧！</span>"
            log_to_gui(f"✅ 回報 {visitor_name}：伺服器運作中 (人數: {players})")
        else:
            log_to_gui("🚀 正在執行自動啟動程序...")
            driver.execute_script("arguments[0].click();", start_btn)
            time.sleep(3)
            status_msg = "<span style='color: #FFC107;'>🚀 伺服器剛剛已為你成功喚醒！<br><span style='font-size: 0.9em; color: #B0BEC5;'>⏱️ 系統正在載入世界...</span><br>請等個幾十秒再進入遊戲喔！</span>"
            log_to_gui(f"✅ 已為 {visitor_name} 發送啟動訊號")
            
        stream_status = check_streaming()
        
        html_response = f"""
        <!DOCTYPE html>
        <html>
        <head><title>帕魯伺服器狀態</title><meta charset="utf-8"></head>
        <body style="background-color: #121212; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
            <div style="background-color: #1e1e1e; color: white; padding: 40px; border-radius: 20px; width: 350px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); text-align: center; border: 1px solid #333;">
                <h2 style="margin-top: 0; color: #03A9F4;">🌐 {SERVER_NAME} 專屬伺服器</h2>
                <hr style="border: 1px solid #333; margin-bottom: 20px;">
                <p style="font-size: 1.1em;"><strong>歡迎，{visitor_name}！</strong></p>
                <p style="background: #2a2a2a; padding: 15px; border-radius: 10px; line-height: 1.6;">{status_msg}</p>
                <p style="font-size: 1.1em; margin-top: 25px;"><strong>🎮 遊戲連線 IP</strong></p>
                <p style="background: #2a2a2a; padding: 10px; border-radius: 10px; color: #00E676; font-size: 1.3em; font-weight: bold; letter-spacing: 1px;">{SERVER_IP_PORT}</p>
                <p style="font-size: 1.1em; margin-top: 25px;"><strong>🎥 網路狀況預警</strong></p>
                <p style="background: #2a2a2a; padding: 10px; border-radius: 10px; line-height: 1.4;">{stream_status}</p>
                <p style="font-size: 0.9em; color: #777; margin-top: 30px;">VPN 虛擬區網通道：開啟</p>
            </div>
        </body>
        </html>
        """
        return html_response, 200
        
    except Exception as e:
        log_to_gui("❌ 錯誤：自動化失敗")
        error_msg = str(e)
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>系統錯誤</title><meta charset="utf-8"></head>
        <body style="background-color: #121212; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: sans-serif;">
            <div style="background-color: #1e1e1e; color: white; padding: 40px; border-radius: 20px; text-align: center; border: 1px solid #FF5252; box-shadow: 0 0 25px rgba(255, 82, 82, 0.4);">
                <h2 style="color: #FF5252; margin-top: 0;">⚠️ 系統發生錯誤</h2>
                <hr style="border: 1px solid #333; margin-bottom: 20px;">
                <p style="color: #B0BEC5; word-break: break-all; max-width: 400px; text-align: left; background: #2a2a2a; padding: 15px; border-radius: 10px;">{error_msg}</p>
                <p style="font-size: 0.9em; color: #777; margin-top: 20px;">請將此截圖傳給台主進行除錯。</p>
            </div>
        </body>
        </html>
        """, 500
    finally:
        if driver is not None:
            driver.quit()

@app.route('/start', methods=['GET', 'POST'])
def start_server():
    global SERVER_NAME
    if request.method == 'GET':
        login_html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>訪客登記 - {SERVER_NAME}</title><meta charset="utf-8"></head>
        <body style="background-color: #121212; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
            <div style="background-color: #1e1e1e; color: white; padding: 40px; border-radius: 20px; width: 320px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); text-align: center; border: 1px solid #333;">
                <h2 style="margin-top: 0; color: #03A9F4;">🔐 {SERVER_NAME} 前台系統</h2>
                <p style="color: #B0BEC5; margin-bottom: 25px;">請輸入你的遊戲暱稱以進行身分驗證</p>
                <form id="loginForm" method="POST" action="/start" onsubmit="showLoading()">
                    <input type="text" name="visitor_name" required placeholder="例如：玩家123" style="width: 90%; padding: 12px; margin-bottom: 25px; border-radius: 8px; border: none; background: #2a2a2a; color: white; font-size: 16px; text-align: center; outline: none;">
                    <br>
                    <button id="submitBtn" type="submit" style="background-color: #4CAF50; color: white; border: none; padding: 12px 20px; font-size: 16px; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; transition: 0.3s;">🚀 進入控制台</button>
                </form>
                <div id="loadingStatus" style="display: none; margin-top: 20px;">
                    <p style="color: #FFC107; font-weight: bold; font-size: 1.1em; margin: 0;">⏳ 正在呼叫後台系統...</p>
                    <p style="color: #777; font-size: 0.9em; margin-top: 5px;">啟動程序約需 5~10 秒，請勿關閉網頁</p>
                </div>
            </div>
            <script>
            function showLoading() {{
                var btn = document.getElementById('submitBtn');
                var status = document.getElementById('loadingStatus');
                btn.style.backgroundColor = '#555555';
                btn.style.cursor = 'not-allowed';
                btn.innerHTML = '⚙️ 處理中，請稍候...';
                btn.disabled = true; 
                status.style.display = 'block';
                document.getElementById('loginForm').submit();
            }}
            </script>
        </body>
        </html>
        """
        return login_html, 200
    else:
        visitor_name = request.form.get('visitor_name', '匿名玩家')
        visitor_ip = request.remote_addr  
        return run_web_automation(visitor_name, visitor_ip)

def build_gui():
    global window, log_box
    window = tk.Tk()
    window.title(f"{SERVER_NAME} 主控台")
    window.geometry("450x480") 
    window.configure(bg="#f0f0f0")

    try:
        if os.path.exists(r"C:\Users\DontHow\Desktop\鐵.ico"):
            window.iconbitmap(r"C:\Users\DontHow\Desktop\鐵.ico")
    except Exception:
        pass 

    # 頂部控制列 (放入狀態與設定按鈕)
    top_frame = tk.Frame(window, bg="#f0f0f0")
    top_frame.pack(fill=tk.X, padx=15, pady=10)
    
    lbl_status = tk.Label(top_frame, text="🟢 狀態：API 正常開放", fg="#4CAF50", bg="#f0f0f0", font=("微軟正黑體", 12, "bold"))
    lbl_status.pack(side=tk.LEFT)

    # === 動態修改設定的視窗 ===
    def open_settings():
        settings_win = tk.Toplevel(window)
        settings_win.title("修改伺服器設定")
        settings_win.geometry("400x520")
        settings_win.configure(bg="#f0f0f0")
        settings_win.grab_set()  # 鎖定主視窗

        tk.Label(settings_win, text="⚙️ 修改伺服器參數", font=("微軟正黑體", 12, "bold"), bg="#f0f0f0").pack(pady=15)

        fields = [
            ("伺服器名稱 (顯示於網頁)", SERVER_NAME),
            ("遊戲連線 IP 與 Port", SERVER_IP_PORT),
            ("管理員密碼 (AdminPassword)", ADMIN_PASSWORD),
            ("伺服器面板網址", GUI_URL),
            ("REST API 網址", REST_API_URL)
        ]
        
        entries = []
        for text, current_val in fields:
            frame = tk.Frame(settings_win, bg="#f0f0f0")
            frame.pack(fill=tk.X, padx=40, pady=5)
            tk.Label(frame, text=text, font=("微軟正黑體", 9, "bold"), bg="#f0f0f0").pack(anchor="w")
            entry = tk.Entry(frame, font=("微軟正黑體", 10))
            entry.insert(0, current_val)
            entry.pack(fill=tk.X)
            entries.append(entry)

        def save_settings():
            global SERVER_NAME, SERVER_IP_PORT, ADMIN_PASSWORD, GUI_URL, REST_API_URL
            SERVER_NAME = entries[0].get()
            SERVER_IP_PORT = entries[1].get()
            ADMIN_PASSWORD = entries[2].get()
            GUI_URL = entries[3].get()
            REST_API_URL = entries[4].get()
            
            new_config = {
                "SERVER_NAME": SERVER_NAME,
                "SERVER_IP_PORT": SERVER_IP_PORT,
                "ADMIN_PASSWORD": ADMIN_PASSWORD,
                "GUI_URL": GUI_URL,
                "REST_API_URL": REST_API_URL
            }
            
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_path, CONFIG_FILE)
            
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(new_config, f, indent=4, ensure_ascii=False)
                messagebox.showinfo("成功", "設定已儲存！下次觸發將自動套用新設定。", parent=settings_win)
                window.title(f"{SERVER_NAME} 主控台")  # 更新主視窗標題
                settings_win.destroy()
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存失敗：{e}", parent=settings_win)

        tk.Button(settings_win, text="💾 儲存並套用", bg="#2196F3", fg="white", font=("微軟正黑體", 10, "bold"), command=save_settings, relief="flat", padx=10).pack(pady=20)

    btn_settings = tk.Button(top_frame, text="⚙️ 修改設定", bg="#607D8B", fg="white", font=("微軟正黑體", 9, "bold"), command=open_settings, relief="flat")
    btn_settings.pack(side=tk.RIGHT)

    frame_block = tk.LabelFrame(window, text="防干擾設定", bg="#f0f0f0", font=("微軟正黑體", 9))
    frame_block.pack(fill=tk.X, padx=15, pady=5)

    entry_msg = tk.Entry(frame_block, font=("微軟正黑體", 10))
    entry_msg.insert(0, "台主正在打積分，暫時不開放伺服器！")
    entry_msg.pack(fill=tk.X, pady=10, padx=10)

    def toggle_block():
        global is_blocking, block_message
        is_blocking = not is_blocking
        if is_blocking:
            block_message = entry_msg.get()
            lbl_status.config(text="🔴 狀態：已鎖定連線", fg="#FF5252")
            btn_toggle.config(text="解除鎖定", bg="#4CAF50", fg="white")
            entry_msg.config(state="disabled")
            log_to_gui("🛡️ 台主啟動了阻擋模式")
        else:
            lbl_status.config(text="🟢 狀態：API 正常開放", fg="#4CAF50")
            btn_toggle.config(text="啟動鎖定 (阻擋朋友開啟)", bg="#FF5252", fg="white")
            entry_msg.config(state="normal")
            log_to_gui("🛡️ 台主解除了阻擋模式")

    btn_toggle = tk.Button(frame_block, text="啟動鎖定 (阻擋朋友開啟)", bg="#FF5252", fg="white", font=("微軟正黑體", 10, "bold"), command=toggle_block, relief="flat", padx=10, pady=5)
    btn_toggle.pack(pady=5)

    def trigger_shutdown():
        threading.Thread(target=safe_shutdown_task, daemon=True).start()

    btn_shutdown = tk.Button(window, text="🛑 一鍵安全關機 (自動存檔)", bg="#37474F", fg="white", font=("微軟正黑體", 10, "bold"), command=trigger_shutdown, relief="flat", padx=10, pady=5)
    btn_shutdown.pack(pady=10)

    lbl_log = tk.Label(window, text="近期訪客與事件日誌：", bg="#f0f0f0", font=("微軟正黑體", 9))
    lbl_log.pack(anchor="w", padx=15)
    
    log_box = tk.Listbox(window, height=8, font=("微軟正黑體", 9), bg="#ffffff")
    log_box.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
    log_to_gui(f"✅ 系統啟動完畢，已載入 {SERVER_NAME} 設定檔")

    def create_tray_image():
        try:
            if os.path.exists(r"C:\Users\DontHow\Desktop\鐵.png"):
                return Image.open(r"C:\Users\DontHow\Desktop\鐵.png")
            raise FileNotFoundError
        except Exception:
            image = Image.new('RGB', (64, 64), color=(3, 169, 244))
            dc = ImageDraw.Draw(image)
            dc.rectangle((16, 16, 48, 48), fill=(30, 30, 30))
            return image

    def show_window(icon, item):
        window.after(0, lambda: [window.deiconify(), window.lift(), window.focus_force()])

    def quit_app(icon, item):
        icon.stop()
        os._exit(0) 

    menu = pystray.Menu(
        pystray.MenuItem('顯示控制台', show_window, default=True), 
        pystray.MenuItem('完全退出程式', quit_app)
    )
    
    tray_icon = pystray.Icon("PalAPI", create_tray_image(), "帕魯伺服器 API", menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()

    def hide_window():
        window.withdraw() 

    window.protocol("WM_DELETE_WINDOW", hide_window)
    window.mainloop()

if __name__ == '__main__':
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    load_config_and_init()

    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    build_gui()