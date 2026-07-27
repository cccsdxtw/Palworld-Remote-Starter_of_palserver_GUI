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
# 🌟 資源導航魔法 (尋找打包後的圖示)
# ==========================================
def get_resource_path(relative_path):
    """取得打包後資源的絕對路徑"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ==========================================
# ⚙️ 設定檔與全域變數區
# ==========================================
CONFIG_FILE = "config.json"
SERVER_NAME = ""
SERVER_IP_PORT = ""
ADMIN_PASSWORD = ""
REST_API_URL = ""
GUI_URL = ""
INSTANCE_ID = ""          
AUTO_SHUTDOWN_MINUTES = 15 

is_blocking = False
block_message = "台主正在打積分，暫時不開放！"
window = None
log_box = None
is_shutting_down = False   # 防止深度休眠重入
is_server_asleep = False   # 已進入休眠後暫停自動關機，避免無限循環
gui_action_lock = threading.Lock()  # 避免多個 Selenium 同時操作面板

app = Flask(__name__)

# ==========================================
# 🌟 設定與讀取系統
# ==========================================
def normalize_rest_api_url(value):
    """
    使用者只需填面板顯示的埠號（例如 8213）。
    也相容舊設定的完整網址 http://127.0.0.1:8213。
    """
    raw = (value or "").strip()
    if not raw:
        return "http://127.0.0.1:8213"
    if raw.isdigit():
        return f"http://127.0.0.1:{raw}"
    # 誤填成 ":8213" 或 "127.0.0.1:8213"
    if raw.startswith(":"):
        port = raw[1:].strip()
        if port.isdigit():
            return f"http://127.0.0.1:{port}"
    if "://" not in raw and raw.count(":") == 1:
        host, port = raw.split(":", 1)
        if port.isdigit():
            host = host.strip() or "127.0.0.1"
            return f"http://{host}:{port}"
    return raw.rstrip("/")

def rest_api_port_for_display(url):
    """設定畫面顯示用：從完整網址抽出埠號，方便對照面板。"""
    url = (url or "").strip()
    if url.isdigit():
        return url
    try:
        # http://127.0.0.1:8213 → 8213
        after_scheme = url.split("://", 1)[-1]
        hostport = after_scheme.split("/", 1)[0]
        if ":" in hostport:
            return hostport.rsplit(":", 1)[-1]
    except Exception:
        pass
    return url

def run_setup_wizard(config_path):
    setup_win = tk.Tk()
    setup_win.title("帕魯 API - 初次設定精靈")
    setup_win.geometry("420x550")
    setup_win.configure(bg="#f0f0f0")

    try:
        icon_path = get_resource_path("app_master_icon.ico")
        if os.path.exists(icon_path):
            setup_win.iconbitmap(icon_path)
    except Exception:
        pass

    tk.Label(setup_win, text="🚀 歡迎使用伺服器前台系統", font=("微軟正黑體", 14, "bold"), bg="#f0f0f0", fg="#03A9F4").pack(pady=20)
    tk.Label(setup_win, text="偵測到您是第一次執行，請填寫基本設定：", font=("微軟正黑體", 10), bg="#f0f0f0").pack(pady=5)

    fields = [
        ("伺服器名稱 (顯示於網頁)", "例如：我的帕魯世界"),
        ("遊戲連線 IP 與 Port", "例如：127.0.0.1:8211"),
        ("管理員密碼 (AdminPassword)", ""),
        ("伺服器面板網址", "http://localhost:8250"),
        ("REST API 埠號（面板顯示的數字，例如 8213）", "8213"),
        ("面板實例 ID (留空則系統自動抓取)", "")
    ]

    entries = []
    for text, default_val in fields:
        frame = tk.Frame(setup_win, bg="#f0f0f0")
        frame.pack(fill=tk.X, padx=40, pady=3)
        tk.Label(frame, text=text, font=("微軟正黑體", 9, "bold"), bg="#f0f0f0").pack(anchor="w")
        entry = tk.Entry(frame, font=("微軟正黑體", 10))
        entry.insert(0, default_val)
        entry.pack(fill=tk.X)
        entries.append(entry)

    def save_and_start():
        rest_full = normalize_rest_api_url(entries[4].get())
        new_config = {
            "SERVER_NAME": entries[0].get(),
            "SERVER_IP_PORT": entries[1].get(),
            "ADMIN_PASSWORD": entries[2].get(),
            "GUI_URL": entries[3].get().strip() or "http://localhost:8250",
            "REST_API_URL": rest_api_port_for_display(rest_full),  # 設定檔只存埠號
            "INSTANCE_ID": entries[5].get(),
            "AUTO_SHUTDOWN_MINUTES": 15
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
    global SERVER_NAME, SERVER_IP_PORT, ADMIN_PASSWORD, REST_API_URL, GUI_URL, INSTANCE_ID, AUTO_SHUTDOWN_MINUTES
    
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
        raw_rest = str(cfg.get("REST_API_URL", "8213")).strip()
        REST_API_URL = normalize_rest_api_url(raw_rest)
        GUI_URL = cfg.get("GUI_URL", "http://localhost:8250")
        INSTANCE_ID = cfg.get("INSTANCE_ID", "")
        try:
            AUTO_SHUTDOWN_MINUTES = int(cfg.get("AUTO_SHUTDOWN_MINUTES", 15))
        except:
            AUTO_SHUTDOWN_MINUTES = 15

        # 舊版若存完整網址，啟動時自動改寫成埠號（例如 8213）
        port_only = rest_api_port_for_display(REST_API_URL)
        if raw_rest != port_only:
            cfg["REST_API_URL"] = port_only
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
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

def auto_fetch_instance_id():
    """依 SERVER_NAME 從面板取得實例 ID（必要時帶 Bearer）。"""
    global INSTANCE_ID
    data = agent_get_json("/api/instances")
    if isinstance(data, list) and data:
        matched = None
        if SERVER_NAME:
            for item in data:
                if item.get("name") == SERVER_NAME:
                    matched = item
                    break
        if matched is None:
            matched = data[0]
        fetched_id = matched.get("uuid") or matched.get("instanceId") or matched.get("id")
        if fetched_id:
            INSTANCE_ID = fetched_id
            log_to_gui(f"✅ 自動獲取面板 ID 成功：{INSTANCE_ID}")
            return INSTANCE_ID
    if INSTANCE_ID:
        return INSTANCE_ID
    log_to_gui("⚠️ 面板未回傳有效的實例 ID")
    return None

# ==========================================
# 🔑 palserver-agent 官方 API（Bearer + 正確參數）
# ==========================================
def get_agent_token():
    """讀取 ~/.palserver-agent/token（絕不寫入日誌）。"""
    token_path = os.path.join(os.path.expanduser("~"), ".palserver-agent", "token")
    try:
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    return token
    except Exception:
        pass
    return None

def agent_headers():
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = get_agent_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def agent_url(path):
    return f"{GUI_URL.rstrip('/')}{path}"

def agent_get_json(path, timeout=8):
    try:
        resp = requests.get(agent_url(path), headers=agent_headers(), timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def agent_post_json(path, body=None, timeout=30):
    try:
        resp = requests.post(
            agent_url(path),
            headers=agent_headers(),
            json=body if body is not None else {},
            timeout=timeout,
        )
        return resp
    except Exception as e:
        log_to_gui(f"❌ 面板 API 連線異常：{e}")
        return None

def get_active_world_guid(instance_id):
    """從 /saves 取得啟用中世界的 GUID（備份 API 必填）。"""
    data = agent_get_json(f"/api/instances/{instance_id}/saves")
    if not data:
        return None
    worlds = data.get("worlds") or []
    for w in worlds:
        if w.get("active"):
            return w.get("guid")
    if worlds:
        return worlds[0].get("guid")
    return None

def read_server_pid(instance_id):
    """讀取 agent 記錄的遊戲行程 PID。"""
    pid_path = os.path.join(
        os.path.expanduser("~"), ".palserver-agent", "instances", str(instance_id), "server.pid"
    )
    try:
        if not os.path.exists(pid_path):
            return None
        with open(pid_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        pid = int(data.get("pid"))
        return pid if pid > 0 else None
    except Exception:
        return None

def is_pid_running(pid):
    if not pid:
        return False
    try:
        out = subprocess.check_output(
            f'tasklist /FI "PID eq {pid}" /NH',
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="ignore",
        )
        return str(pid) in out and "No tasks" not in out and "沒有執行中" not in out
    except Exception:
        return False

def is_rest_api_alive():
    if not ADMIN_PASSWORD or not REST_API_URL:
        return False
    try:
        resp = requests.get(
            f"{REST_API_URL}/v1/api/metrics",
            auth=HTTPBasicAuth("admin", ADMIN_PASSWORD),
            timeout=2,
        )
        return resp.status_code == 200
    except Exception:
        return False

def is_instance_running(instance_id):
    """用面板 live/status 判斷是否仍在運作。"""
    data = agent_get_json(f"/api/instances/{instance_id}")
    if isinstance(data, dict):
        status = (data.get("status") or data.get("state") or "").lower()
        if status in ("running", "restarting", "stopping"):
            return True
        if status in ("stopped", "offline", "idle"):
            return False
        if "running" in data:
            return bool(data.get("running"))
    live = agent_get_json(f"/api/instances/{instance_id}/live")
    if isinstance(live, dict):
        if "running" in live:
            return bool(live.get("running"))
        status = (live.get("status") or "").lower()
        if status:
            return status in ("running", "restarting", "stopping")
    return None  # 未知

def wait_until_server_fully_stopped(instance_id, timeout_sec=120):
    """
    確認伺服器真正停妥後才繼續（對應面板停止約 30 秒倒數 + 關進程時間）。
    條件：server.pid 行程不存在，且 REST API 連不上。
    """
    log_to_gui("⏳ 等待伺服器真正停止（面板停止約有 30 秒倒數，請稍候）...")
    deadline = time.time() + timeout_sec
    last_log = 0
    while time.time() < deadline:
        pid = read_server_pid(instance_id)
        proc_alive = is_pid_running(pid) if pid else False
        # 若沒有 pid 檔，再看 REST；兩者都死才算停妥
        api_alive = is_rest_api_alive()
        panel_running = is_instance_running(instance_id)

        if not proc_alive and not api_alive and panel_running is not True:
            # 再確認一次，避免倒數剛結束的瞬間誤判
            time.sleep(2)
            pid2 = read_server_pid(instance_id)
            if not is_pid_running(pid2) and not is_rest_api_alive():
                log_to_gui("✅ 已確認伺服器真正停止（行程與 REST API 皆已關閉）")
                return True

        now = time.time()
        if now - last_log >= 10:
            remain = int(deadline - now)
            tip = f"PID={pid}" if pid else "無 PID 檔"
            log_to_gui(f"⏳ 仍在等待停服中…（{tip}，剩餘約 {remain} 秒）")
            last_log = now
        time.sleep(2)

    log_to_gui("⚠️ 等待停服逾時，將依目前狀態繼續（請手動確認伺服器是否已關）")
    return False

def agent_save_world(instance_id):
    log_to_gui("💾 正在呼叫面板 API 存檔（等同「立即存檔」）...")
    resp = agent_post_json(f"/api/instances/{instance_id}/save", {}, timeout=20)
    if resp is not None and resp.status_code in (200, 201, 202, 204):
        log_to_gui("✅ 面板存檔成功")
        return True
    code = resp.status_code if resp is not None else "無回應"
    detail = (resp.text or "")[:160] if resp is not None else ""
    log_to_gui(f"⚠️ 面板存檔失敗 ({code}) {detail}")
    return False

def agent_create_backup(instance_id):
    """POST /saves/backup 必須帶 worldGuid，並建議附 Bearer。"""
    world_guid = get_active_world_guid(instance_id)
    if not world_guid:
        log_to_gui("⚠️ 找不到啟用中的世界 GUID，無法用 API 備份")
        return False
    log_to_gui(f"📦 正在呼叫面板 API 備份（worldGuid={world_guid[:8]}…）...")
    resp = agent_post_json(
        f"/api/instances/{instance_id}/saves/backup",
        {"worldGuid": world_guid},
        timeout=120,
    )
    if resp is not None and resp.status_code in (200, 201, 202, 204):
        log_to_gui("✅ 面板備份成功")
        return True
    code = resp.status_code if resp is not None else "無回應"
    detail = (resp.text or "")[:200] if resp is not None else ""
    log_to_gui(f"⚠️ 面板備份失敗 ({code}) {detail}")
    return False

def agent_stop_server(instance_id, use_countdown=True):
    """
    等同面板點「停止」。
    use_countdown=True：走與 GUI 相同的倒數公告（約 announceSeconds，常見 30 秒），
    此 HTTP 會阻塞到倒數結束並真正 stop 後才返回。
    """
    body = {}
    if use_countdown:
        # 有公告樣板才會進入倒數；秒數由面板「伺服器重啟」設定的 announceSeconds 決定
        body = {"announceTemplate": "伺服器將在 {n} 秒後關閉（自動休眠）"}
        log_to_gui("🛑 正在呼叫面板 API 停止（含倒數，等同點「停止」）...")
        timeout = 180
    else:
        body = {"immediate": True}
        log_to_gui("🛑 正在呼叫面板 API 立即停止...")
        timeout = 60

    resp = agent_post_json(f"/api/instances/{instance_id}/stop", body, timeout=timeout)
    if resp is not None and resp.status_code in (200, 201, 202, 204):
        log_to_gui("✅ 面板停止指令已完成")
        return True
    code = resp.status_code if resp is not None else "無回應"
    detail = (resp.text or "")[:200] if resp is not None else ""
    log_to_gui(f"⚠️ 面板停止失敗 ({code}) {detail}")
    return False

# ==========================================
# 🖥️ Selenium 面板操作（開服用；備份/關服作 API 備援）
# ==========================================
def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def ensure_palserver_agent(wait_seconds=6):
    """確保面板 agent 正在執行；必要時自動喚醒。"""
    current_dir = get_app_dir()
    tasks = os.popen('tasklist').read().lower()
    if 'palserver-agent.exe' in tasks:
        return True

    log_to_gui("⚠️ 偵測到控制面板未啟動，正在自動喚醒 palserver-agent.exe...")
    try:
        agent_folder = os.path.join(current_dir, "palserver-agent-windows")
        agent_path = os.path.join(agent_folder, "palserver-agent.exe")
        if not os.path.exists(agent_path):
            log_to_gui("❌ 找不到 palserver-agent.exe，無法自動喚醒")
            return False
        subprocess.Popen(agent_path, shell=True, cwd=agent_folder, creationflags=subprocess.DETACHED_PROCESS)
        log_to_gui("✅ 面板程式喚醒成功！等待服務啟動中...")
        time.sleep(wait_seconds)
        return True
    except Exception as e:
        log_to_gui(f"❌ 喚醒面板發生錯誤：{e}")
        return False

def create_chrome_driver():
    options = Options()
    options.headless = True
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,900")
    current_dir = get_app_dir()
    driver_path = os.path.join(current_dir, "chromedriver.exe")
    if os.path.exists(driver_path):
        service = Service(executable_path=driver_path)
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)

def open_server_on_gui(driver, wait_timeout=8):
    """開啟面板並點進目前設定的伺服器實例頁。"""
    driver.get(GUI_URL)
    wait = WebDriverWait(driver, wait_timeout)
    log_to_gui(f"🔍 正在面板尋找『{SERVER_NAME}』...")
    xpath_server_card = f"//*[contains(text(), '{SERVER_NAME}')]"
    server_card = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_server_card)))
    driver.execute_script("arguments[0].click();", server_card)
    time.sleep(1.5)
    return wait

def gui_click_button(driver, wait, button_text, extra_xpath=""):
    xpath = f"//button[contains(., '{button_text}'){extra_xpath}]"
    btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", btn)
    return True

def gui_confirm_if_any(driver):
    """若出現確認對話框，自動點確認/確定。"""
    time.sleep(0.8)
    for text in ("確認", "確定", "是", "OK", "Yes"):
        try:
            buttons = driver.find_elements(By.XPATH, f"//button[contains(., '{text}')]")
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
                    return True
        except Exception:
            pass
    return False

def run_gui_session(action_fn, fail_prefix="面板操作"):
    """
    取得 GUI lock → 確保 agent → 開啟 Chrome → 進入伺服器頁 → 執行 action_fn(driver, wait)
    """
    if not gui_action_lock.acquire(blocking=False):
        log_to_gui("⏳ 面板正在被其他操作使用中，請稍後再試")
        return False

    driver = None
    try:
        if not ensure_palserver_agent():
            return False
        driver = create_chrome_driver()
        wait = open_server_on_gui(driver)
        return bool(action_fn(driver, wait))
    except Exception as e:
        log_to_gui(f"❌ {fail_prefix}失敗：{e}")
        return False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        gui_action_lock.release()

def trigger_gui_backup():
    """優先用官方 API（Bearer + worldGuid）；失敗才改 Selenium 點「立即備份」。"""
    if not ensure_palserver_agent():
        return False
    instance_id = auto_fetch_instance_id()
    if instance_id and agent_create_backup(instance_id):
        return True

    def action(driver, wait):
        log_to_gui("📦 API 失敗，改於面板點擊「立即備份」...")
        gui_click_button(driver, wait, "立即備份")
        gui_confirm_if_any(driver)
        time.sleep(8)
        log_to_gui("✅ 面板備份按鈕已點擊")
        return True

    return run_gui_session(action, fail_prefix="GUI 備份")

def gui_save_backup_stop(do_backup=True, kill_agent_after=False):
    """
    關服流程：面板 API 存檔 →（備份）→ 停止（含倒數）→ 確認真正停妥 →（可選）關 agent。
    這與手動點面板按鈕走同一組 API。
    """
    if not ensure_palserver_agent():
        return False
    instance_id = auto_fetch_instance_id()
    if not instance_id:
        log_to_gui("❌ 無法取得實例 ID，關服中止")
        return False

    agent_save_world(instance_id)
    time.sleep(3)

    if do_backup:
        if not agent_create_backup(instance_id):
            # API 失敗時嘗試點按鈕
            trigger_gui_backup()
        time.sleep(2)

    stopped = agent_stop_server(instance_id, use_countdown=True)
    if not stopped:
        def action(driver, wait):
            log_to_gui("🛑 API 停止失敗，改於面板點擊「停止」...")
            gui_click_button(driver, wait, "停止")
            gui_confirm_if_any(driver)
            return True
        run_gui_session(action, fail_prefix="GUI 停止")

    # 無論 API 是否宣稱完成，都再確認行程真的沒了
    wait_until_server_fully_stopped(instance_id, timeout_sec=120)

    if kill_agent_after:
        log_to_gui("🔪 伺服器已確認停止，正在關閉 palserver-agent...")
        os.system("taskkill /F /IM palserver-agent.exe >nul 2>&1")
        time.sleep(1)

    return True

def perform_deep_sleep(reason_message, announce_done_msg):
    """深度休眠：存檔+備份+停止 → 確認停妥 → 關面板。"""
    global is_shutting_down, is_server_asleep

    if is_shutting_down:
        log_to_gui("⏳ 深度休眠進行中，略過重複觸發")
        return False

    is_shutting_down = True
    try:
        log_to_gui("🔴 開始深度休眠（存檔 → 備份 → 停止 → 確認停妥 → 關面板）...")
        ok = gui_save_backup_stop(do_backup=True, kill_agent_after=True)
        if not ok:
            log_to_gui("⚠️ 深度休眠流程未完全成功")
        is_server_asleep = True
        log_to_gui(announce_done_msg)
        return True
    finally:
        is_shutting_down = False

def mark_server_awake(source=""):
    """訪客喚醒或偵測到伺服器恢復時，解除休眠鎖定並重設閒置計時。"""
    global is_server_asleep
    if is_server_asleep:
        is_server_asleep = False
        tip = f"（{source}）" if source else ""
        log_to_gui(f"🌅 伺服器已喚醒{tip}，重新開始閒置監控")

def auto_shutdown_monitor():
    global ADMIN_PASSWORD, REST_API_URL, AUTO_SHUTDOWN_MINUTES, is_server_asleep, is_shutting_down
    
    empty_counter = 0
    log_to_gui(f"⏱️ 系統啟動 (目前自動休眠設定為：{AUTO_SHUTDOWN_MINUTES} 分鐘)")

    while True:
        time.sleep(60) 
        
        if is_shutting_down:
            continue

        if AUTO_SHUTDOWN_MINUTES <= 0:
            empty_counter = 0
            continue
            
        if not ADMIN_PASSWORD:
            continue

        if is_server_asleep:
            continue
            
        try:
            resp = requests.get(f"{REST_API_URL}/v1/api/metrics", auth=HTTPBasicAuth("admin", ADMIN_PASSWORD), timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                current_players = int(data.get("currentplayernum", 0))
                
                if current_players == 0:
                    empty_counter += 1
                    if empty_counter == 1 or empty_counter % 5 == 0:
                        log_to_gui(f"⚠️ 伺服器目前無人，已閒置 {empty_counter} 分鐘...")
                else:
                    if empty_counter > 0:
                        log_to_gui(f"👥 玩家上線，中斷關機倒數！")
                    empty_counter = 0
                    
                if empty_counter >= AUTO_SHUTDOWN_MINUTES and not is_shutting_down and not is_server_asleep:
                    log_to_gui("🔴 閒置時間達標，啟動自動深度休眠！", play_sound=True)
                    perform_deep_sleep(
                        "Server shutting down due to inactivity.",
                        "✅ 任務全部完成，伺服器已進入休眠！之後不會再自動循環關機，需訪客喚醒後才重新計時。"
                    )
                    empty_counter = 0
                    
        except Exception:
            empty_counter = 0

def safe_shutdown_task():
    """一般安全關機：面板存檔 → 停止（含倒數）→ 確認停妥（不關面板）。"""
    try:
        log_to_gui("🛑 開始一般安全關機（面板存檔 → 停止 → 確認停妥）...")
        ok = gui_save_backup_stop(do_backup=False, kill_agent_after=False)
        if ok:
            log_to_gui("✅ 伺服器已透過面板安全關機！", play_sound=True)
        else:
            log_to_gui("❌ 面板關機失敗，請到 palserver GUI 手動點「停止」", play_sound=True)
    except Exception as e:
        log_to_gui(f"❌ 關機異常: {e}", play_sound=True)

def deep_sleep_task():
    global is_shutting_down
    if is_shutting_down:
        log_to_gui("⏳ 深度休眠進行中，略過重複觸發")
        return
    try:
        log_to_gui("🔴 啟動手動深度休眠程序！", play_sound=True)
        perform_deep_sleep(
            "Server shutting down for deep sleep.",
            "✅ 深度休眠完成！已確認停服後關閉面板程式。"
        )
    except Exception as e:
        log_to_gui(f"❌ 深度休眠異常: {e}", play_sound=True)

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
    acquired = gui_action_lock.acquire(blocking=False)
    if not acquired:
        log_to_gui("⏳ 面板忙碌中，稍後再試訪客啟動")
        return "<h3>系統忙碌中，請稍後再試</h3>", 503

    try:
        if not ensure_palserver_agent():
            raise Exception("無法啟動 palserver-agent")

        driver = create_chrome_driver()
        wait_short = open_server_on_gui(driver, wait_timeout=5)
        
        try:
            xpath_start_btn = "//button[contains(., '啟動') and not(contains(., '未'))]"
            start_btn = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_start_btn)))
            is_running = False
        except Exception:
            is_running = True

        if is_running:
            uptime = get_server_uptime()
            players = get_player_count() 
            mark_server_awake("訪客造訪且伺服器運作中")
            
            if players.isdigit():
                player_display = f"<br><span style='font-size: 0.9em; color: #00E676;'>👥 目前線上人數：{players} 人</span>"
            else:
                player_display = f"<br><span style='font-size: 0.9em; color: #777;'>👥 線人數：{players}</span>"

            status_msg = f"<span style='color: #4CAF50;'>✅ 伺服器已在運作中！<br><span style='font-size: 0.9em; color: #B0BEC5;'>⏱️ 本次已開機：{uptime}</span>{player_display}<br>不要猶豫，直接連線吧！</span>"
            log_to_gui(f"✅ 回報 {visitor_name}：伺服器運作中 (人數: {players})")
        else:
            log_to_gui("🚀 正在於面板點擊「啟動」...")
            driver.execute_script("arguments[0].click();", start_btn)
            time.sleep(3)
            mark_server_awake("訪客喚醒啟動")
            status_msg = "<span style='color: #FFC107;'>🚀 伺服器剛剛已為你成功喚醒！<br><span style='font-size: 0.9em; color: #B0BEC5;'>⏱️ 系統正在載入世界...</span><br>請等個幾十秒再進入遊戲喔！</span>"
            log_to_gui(f"✅ 已為 {visitor_name} 在面板點擊「啟動」")
            
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
            try:
                driver.quit()
            except Exception:
                pass
        if acquired:
            gui_action_lock.release()

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
    window.title(f"{SERVER_NAME} 主控台 V1.5.1")
    window.geometry("480x880")
    window.configure(bg="#f0f0f0")

    try:
        icon_path = get_resource_path("app_master_icon.ico")
        if os.path.exists(icon_path):
            window.iconbitmap(icon_path)
    except Exception:
        pass

    top_frame = tk.Frame(window, bg="#f0f0f0")
    top_frame.pack(fill=tk.X, padx=15, pady=10)
    
    lbl_status = tk.Label(top_frame, text="🟢 狀態：API 正常開放", fg="#4CAF50", bg="#f0f0f0", font=("微軟正黑體", 12, "bold"))
    lbl_status.pack(side=tk.LEFT)

    def open_settings():
        settings_win = tk.Toplevel(window)
        settings_win.title("修改伺服器設定")
        settings_win.geometry("440x550")
        settings_win.configure(bg="#f0f0f0")
        settings_win.grab_set() 

        tk.Label(settings_win, text="⚙️ 修改伺服器參數", font=("微軟正黑體", 12, "bold"), bg="#f0f0f0").pack(pady=15)

        fields = [
            ("伺服器名稱 (顯示於網頁)", SERVER_NAME),
            ("遊戲連線 IP 與 Port", SERVER_IP_PORT),
            ("管理員密碼 (AdminPassword)", ADMIN_PASSWORD),
            ("伺服器面板網址", GUI_URL),
            ("REST API 埠號（面板顯示的數字，例如 8213）", rest_api_port_for_display(REST_API_URL)),
            ("面板實例 ID (留空則系統自動抓取)", INSTANCE_ID)
        ]
        
        entries = []
        for text, current_val in fields:
            frame = tk.Frame(settings_win, bg="#f0f0f0")
            frame.pack(fill=tk.X, padx=40, pady=3)
            tk.Label(frame, text=text, font=("微軟正黑體", 9, "bold"), bg="#f0f0f0").pack(anchor="w")
            entry = tk.Entry(frame, font=("微軟正黑體", 10))
            entry.insert(0, current_val)
            entry.pack(fill=tk.X)
            entries.append(entry)

        def save_settings():
            global SERVER_NAME, SERVER_IP_PORT, ADMIN_PASSWORD, GUI_URL, REST_API_URL, INSTANCE_ID
            SERVER_NAME = entries[0].get()
            SERVER_IP_PORT = entries[1].get()
            ADMIN_PASSWORD = entries[2].get()
            GUI_URL = entries[3].get().strip() or "http://localhost:8250"
            REST_API_URL = normalize_rest_api_url(entries[4].get())
            INSTANCE_ID = entries[5].get()
            
            new_config = {
                "SERVER_NAME": SERVER_NAME,
                "SERVER_IP_PORT": SERVER_IP_PORT,
                "ADMIN_PASSWORD": ADMIN_PASSWORD,
                "GUI_URL": GUI_URL,
                "REST_API_URL": rest_api_port_for_display(REST_API_URL),  # 設定檔只存埠號
                "INSTANCE_ID": INSTANCE_ID,
                "AUTO_SHUTDOWN_MINUTES": AUTO_SHUTDOWN_MINUTES
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
                window.title(f"{SERVER_NAME} 主控台 V1.5.1") 
                settings_win.destroy()
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存失敗：{e}", parent=settings_win)

        tk.Button(settings_win, text="💾 儲存並套用", bg="#2196F3", fg="white", font=("微軟正黑體", 10, "bold"), command=save_settings, relief="flat", padx=10).pack(pady=20)

    btn_settings = tk.Button(top_frame, text="⚙️ 修改設定", bg="#607D8B", fg="white", font=("微軟正黑體", 9, "bold"), command=open_settings, relief="flat")
    btn_settings.pack(side=tk.RIGHT)

    # === ⏱️ 自動深度休眠設定區塊 ===
    frame_auto = tk.LabelFrame(window, text="自動深度休眠設定", bg="#f0f0f0", font=("微軟正黑體", 9))
    frame_auto.pack(fill=tk.X, padx=15, pady=5)

    tk.Label(frame_auto, text="閒置幾分鐘執行 (0為停用):", bg="#f0f0f0", font=("微軟正黑體", 9)).pack(side=tk.LEFT, padx=5, pady=5)
    
    entry_auto_min = tk.Entry(frame_auto, font=("微軟正黑體", 10), width=5, justify="center")
    entry_auto_min.insert(0, str(AUTO_SHUTDOWN_MINUTES))
    entry_auto_min.pack(side=tk.LEFT, pady=5)

    def apply_auto_min():
        global AUTO_SHUTDOWN_MINUTES
        try:
            new_val = int(entry_auto_min.get())
            AUTO_SHUTDOWN_MINUTES = new_val
            
            base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_path, CONFIG_FILE)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                cfg['AUTO_SHUTDOWN_MINUTES'] = AUTO_SHUTDOWN_MINUTES
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
                    
            log_to_gui(f"✅ 自動休眠時間已更新為 {AUTO_SHUTDOWN_MINUTES} 分鐘", play_sound=True)
        except ValueError:
            log_to_gui("❌ 請輸入有效的數字格式", play_sound=True)

    btn_apply_auto = tk.Button(frame_auto, text="💾 儲存套用", bg="#FF9800", fg="white", font=("微軟正黑體", 9, "bold"), command=apply_auto_min, relief="flat", padx=10)
    btn_apply_auto.pack(side=tk.RIGHT, padx=10, pady=5)

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

    frame_announce = tk.LabelFrame(window, text="伺服器對話框廣播 (Announce)", bg="#f0f0f0", font=("微軟正黑體", 9))
    frame_announce.pack(fill=tk.X, padx=15, pady=5)

    entry_announce = tk.Entry(frame_announce, font=("微軟正黑體", 10))
    entry_announce.insert(0, "哈囉！台主上線啦！")
    entry_announce.pack(fill=tk.X, pady=10, padx=10)

    def trigger_announce():
        msg = entry_announce.get()
        if not msg:
            return
            
        def send_task():
            if not ADMIN_PASSWORD:
                log_to_gui("❌ 廣播失敗：未設定管理員密碼", play_sound=True)
                return
            try:
                data = {"message": msg}
                resp = requests.post(f"{REST_API_URL}/v1/api/announce", json=data, auth=HTTPBasicAuth("admin", ADMIN_PASSWORD), timeout=5)
                
                if resp.status_code == 200:
                    log_to_gui(f"📢 廣播成功：{msg}", play_sound=False)
                    window.after(0, lambda: entry_announce.delete(0, tk.END)) 
                else:
                    log_to_gui(f"❌ 廣播失敗 (狀態碼: {resp.status_code})")
            except Exception:
                log_to_gui("❌ 廣播連線異常，伺服器可能未開啟", play_sound=True)

        threading.Thread(target=send_task, daemon=True).start()

    btn_announce = tk.Button(frame_announce, text="發送全服訊息", bg="#008CBA", fg="white", font=("微軟正黑體", 10, "bold"), command=trigger_announce, relief="flat", padx=10, pady=5)
    btn_announce.pack(pady=5)

    # === 🔌 電源與備份管理區塊 ===
    frame_power = tk.LabelFrame(window, text="電源與備份管理", bg="#f0f0f0", font=("微軟正黑體", 9))
    frame_power.pack(fill=tk.X, padx=15, pady=5)

    def manual_backup():
        threading.Thread(target=trigger_gui_backup, daemon=True).start()

    btn_backup = tk.Button(frame_power, text="📦 獨立執行 GUI 備份（面板 API）", bg="#8D6E63", fg="white", font=("微軟正黑體", 10, "bold"), command=manual_backup, relief="flat", padx=10, pady=5)
    btn_backup.pack(fill=tk.X, padx=10, pady=2)

    def trigger_shutdown():
        threading.Thread(target=safe_shutdown_task, daemon=True).start()

    btn_shutdown = tk.Button(frame_power, text="🛑 一般安全關機（存檔+停止，確認停妥）", bg="#37474F", fg="white", font=("微軟正黑體", 10, "bold"), command=trigger_shutdown, relief="flat", padx=10, pady=2)
    btn_shutdown.pack(fill=tk.X, padx=10, pady=2)

    def trigger_deep_sleep():
        threading.Thread(target=deep_sleep_task, daemon=True).start()

    btn_deep_sleep = tk.Button(frame_power, text="🌙 手動深度休眠（停妥後才關面板）", bg="#512DA8", fg="white", font=("微軟正黑體", 10, "bold"), command=trigger_deep_sleep, relief="flat", padx=10, pady=5)
    btn_deep_sleep.pack(fill=tk.X, padx=10, pady=5)

    lbl_log = tk.Label(window, text="近期訪客與事件日誌：", bg="#f0f0f0", font=("微軟正黑體", 9))
    lbl_log.pack(anchor="w", padx=15)
    
    log_box = tk.Listbox(window, height=15, font=("微軟正黑體", 9), bg="#ffffff")
    log_box.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
    log_to_gui(f"✅ 系統啟動完畢，已載入 {SERVER_NAME} 設定檔")

    def create_tray_image():
        try:
            img_path = get_resource_path("app_master_icon.ico")
            if os.path.exists(img_path):
                return Image.open(img_path)
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
    
    monitor_thread = threading.Thread(target=auto_shutdown_monitor, daemon=True)
    monitor_thread.start()
    
    build_gui()