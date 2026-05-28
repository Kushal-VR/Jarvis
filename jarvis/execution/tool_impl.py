import os
import logging
import subprocess
from typing import Dict, Any, List
from jarvis.automation import ScreenController, OSController
from jarvis.vision import ScreenOCR, ScreenDetector
from jarvis.web import PlaywrightBrowserManager, WebScraper, WebSearch
from jarvis.communication import EmailClient, TelegramNotifier, WhatsAppWebAutomator
from jarvis.dev import GitController, DeveloperAgent
from jarvis.memory import SimpleVectorStore, ShortTermMemory, LongTermMemory
from .tool_registry import ToolRegistry

def register_all_tools(
    registry: ToolRegistry,
    screen_ctrl: ScreenController,
    os_ctrl: OSController,
    ocr: ScreenOCR,
    detector: ScreenDetector,
    browser_mgr: PlaywrightBrowserManager,
    scraper: WebScraper,
    searcher: WebSearch,
    email: EmailClient,
    telegram: TelegramNotifier,
    whatsapp: WhatsAppWebAutomator,
    git: GitController,
    dev_agent: DeveloperAgent,
    vector_store: SimpleVectorStore,
    short_term: ShortTermMemory,
    long_term: LongTermMemory,
    jarvis_system = None
):
    logger = logging.getLogger("Jarvis.ToolsImpl")

    # 1. OS & App Control Tools
    @registry.register("open_app", permission_level="LOW")
    def open_app(app_name: str) -> str:
        """Opens a local application on Windows."""
        os_ctrl.open_application(app_name)
        return f"Successfully launched {app_name}"

    @registry.register("close_app", permission_level="LOW")
    def close_app(app_name: str) -> str:
        """Force closes an application process."""
        os_ctrl.close_application(app_name)
        return f"Closed application {app_name}"

    # 2. File System Tools
    @registry.register("create_folder", permission_level="LOW")
    def create_folder(path: str) -> str:
        """Creates a directory in the workspace sandbox."""
        os.makedirs(path, exist_ok=True)
        return f"Created folder at: {path}"

    @registry.register("create_file", permission_level="LOW")
    def create_file(path: str, content: str = "") -> str:
        """Creates or overwrites a file in the workspace sandbox."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Created file at: {path}"

    @registry.register("get_user_text_input", permission_level="LOW")
    def get_user_text_input(prompt: str, is_password: bool = False) -> str:
        """Opens a themed text input dialog to safely capture text input from the user."""
        if jarvis_system and hasattr(jarvis_system, "get_themed_text_input"):
            return jarvis_system.get_themed_text_input("Jarvis Secure Input", prompt, is_password)
        else:
            # Fallback to simple CLI prompt if jarvis_system is not available
            import getpass
            if is_password:
                return getpass.getpass(f"{prompt}: ")
            else:
                return input(f"{prompt}: ")

    @registry.register("list_files", permission_level="LOW")
    def list_files(path: str = ".") -> str:
        """Lists files in the target directory."""
        if not os.path.exists(path):
            return f"Path does not exist: {path}"
        files = os.listdir(path)
        return f"Files in {path}: " + ", ".join(files)

    @registry.register("open_path", permission_level="LOW")
    def open_path(path: str) -> str:
        """Opens a file or folder in its default desktop application on Windows."""
        try:
            if not os.path.exists(path):
                return f"Error: Path does not exist: {path}"
            os.startfile(path)
            return f"Successfully opened path: {path}"
        except Exception as e:
            return f"Error opening path: {e}"

    @registry.register("read_file_content", permission_level="LOW")
    def read_file_content(file_path: str) -> str:
        """Reads content from a text file on any drive."""
        try:
            if not os.path.exists(file_path):
                return f"Error: File does not exist at {file_path}"
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return f"Contents of {file_path}:\n{content[:2000]}"
        except Exception as e:
            return f"Error reading file: {e}"

    @registry.register("write_file_content", permission_level="LOW")
    def write_file_content(file_path: str, content: str) -> str:
        """Writes content to a text file on any drive."""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote content to {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    @registry.register("locate_path", permission_level="MEDIUM")
    def locate_path(name: str) -> str:
        """Searches all available drives for files or folders matching name."""
        import string
        drives = []
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(drive_path)
        
        matches = []
        max_matches = 10
        name_lower = name.lower()
        
        for drive in drives:
            try:
                for root, dirs, files in os.walk(drive):
                    depth = root.count(os.sep) - drive.count(os.sep)
                    if depth > 3:
                        dirs.clear()
                        continue
                    
                    for d in dirs:
                        if name_lower in d.lower():
                            matches.append(os.path.join(root, d))
                            if len(matches) >= max_matches:
                                break
                    if len(matches) >= max_matches:
                        break
                        
                    for f in files:
                        if name_lower in f.lower():
                            matches.append(os.path.join(root, f))
                            if len(matches) >= max_matches:
                                break
                    if len(matches) >= max_matches:
                        break
            except Exception:
                pass
            if len(matches) >= max_matches:
                break
                
        if not matches:
            return f"No files or folders matching '{name}' were found on any drives."
        return f"Found matching files/folders:\n" + "\n".join(matches)

    # 3. Web & Scraping Tools
    @registry.register("search_web", permission_level="LOW")
    def search_web(query: str) -> str:
        """Searches the internet for matching links and details."""
        results = searcher.search(query)
        formatted = []
        for idx, r in enumerate(results):
            formatted.append(f"{idx+1}. {r['title']} - {r['url']}\nSnippet: {r['snippet']}")
        return "\n\n".join(formatted) if formatted else "No search results found."

    @registry.register("web_scrape", permission_level="LOW")
    def web_scrape(url: str) -> str:
        """Extracts text content and tables from a web page."""
        data = scraper.scrape_url(url)
        if "error" in data:
            return f"Failed to scrape webpage: {data['error']}"
        return f"Title: {data['title']}\nContent Snippet:\n{data['text'][:1500]}"

    @registry.register("collect_google_maps_leads", permission_level="LOW")
    def collect_google_maps_leads(search_query: str, location: str, output_file: str = "google_maps_leads.csv") -> str:
        """Collects business leads from Google Maps (name, phone, address, socials) that don't have websites in a given location and saves to CSV."""
        from jarvis.web.maps_scraper import GoogleMapsScraper
        maps_scraper = GoogleMapsScraper(browser_mgr, searcher)
        return maps_scraper.collect_leads(search_query, location, output_file)

    # 4. GUI & Screen Control Tools
    @registry.register("click_coordinate", permission_level="LOW")
    def click_coordinate(x: int, y: int) -> str:
        """Clicks coordinates on screen."""
        screen_ctrl.click(x, y)
        return f"Clicked screen coordinate ({x}, {y})"

    @registry.register("type_text", permission_level="LOW")
    def type_text(text: str) -> str:
        """Types string text into the active focus window."""
        screen_ctrl.type_text(text)
        return f"Typed text into active window."

    @registry.register("press_key", permission_level="LOW")
    def press_key(key: str) -> str:
        """Presses a keyboard key or hotkey combination."""
        screen_ctrl.press_shortcut(key)
        return f"Pressed key command: {key}"

    @registry.register("screen_read", permission_level="LOW")
    def screen_read() -> str:
        """Captures the current screen and extracts all text content visible using OCR."""
        items = ocr.capture_and_read()
        if not items:
            return "No text detected on the screen or OCR initialization failed."
        # Format the text with coordinates
        text_lines = []
        for item in items:
            text_lines.append(f"Text: '{item['text']}' at center coordinate ({item['center'][0]}, {item['center'][1]})")
        return "\n".join(text_lines)

    @registry.register("describe_screen", permission_level="LOW")
    def describe_screen() -> str:
        """Captures the current screen and returns a natural language description using a vision model."""
        desc = detector.describe_screen()
        return f"Screen description: {desc}"

    @registry.register("play_music", permission_level="LOW")
    def play_music(query: str = "", profile_name: str = "", guest_mode: bool = False) -> str:
        """Plays music on YouTube or YouTube Music using a search query, with optional profile selection or guest mode."""
        import urllib.parse
        import ctypes
        from ctypes import wintypes
        import time
        import pyautogui
        
        # Safe abort checker for use inside the tool
        def check_abort_tool():
            # Escape key = 0x1B
            if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                raise RuntimeError("Music playback automation aborted by user (Escape key pressed).")

        def sleep_with_abort_tool(seconds):
            steps = int(seconds * 10)
            for _ in range(steps):
                time.sleep(0.1)
                check_abort_tool()

        # Helper to find and focus window
        def activate_picker_tool():
            check_abort_tool()
            user32 = ctypes.windll.user32
            hwnd_list = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            
            def enum_cb(hwnd, lp):
                if user32.IsWindowVisible(hwnd):
                    len_txt = user32.GetWindowTextLengthW(hwnd)
                    if len_txt > 0:
                        buf = ctypes.create_unicode_buffer(len_txt + 1)
                        user32.GetWindowTextW(hwnd, buf, len_txt + 1)
                        title = buf.value
                        class_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, class_buf, 256)
                        if class_buf.value == "Chrome_WidgetWin_1" and title == "Google Chrome":
                            hwnd_list.append(hwnd)
                return True
                
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if hwnd_list:
                hwnd = hwnd_list[0]
                pyautogui.press('alt')
                time.sleep(0.05)
                user32.ShowWindow(hwnd, 9) # Restore
                time.sleep(0.05)
                user32.ShowWindow(hwnd, 3) # Maximize
                time.sleep(0.05)
                user32.SetForegroundWindow(hwnd)
                return True
            return False

        # HWND tracking variables inside closure
        normal_hwnd_container = [None]

        def activate_chrome_tool(is_guest_mode=False):
            check_abort_tool()
            user32 = ctypes.windll.user32
            hwnd_list = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            
            def enum_cb(hwnd, lp):
                if user32.IsWindowVisible(hwnd):
                    len_txt = user32.GetWindowTextLengthW(hwnd)
                    if len_txt > 0:
                        buf = ctypes.create_unicode_buffer(len_txt + 1)
                        user32.GetWindowTextW(hwnd, buf, len_txt + 1)
                        title = buf.value
                        class_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, class_buf, 256)
                        if class_buf.value == "Chrome_WidgetWin_1":
                            if "antigravity ide" in title.lower() or "visual studio code" in title.lower():
                                return True
                            if title == "Google Chrome":
                                return True
                            if is_guest_mode:
                                if normal_hwnd_container[0] is not None and hwnd == normal_hwnd_container[0]:
                                    return True
                                hwnd_list.append(hwnd)
                            else:
                                hwnd_list.append(hwnd)
                return True
                
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if hwnd_list:
                hwnd = hwnd_list[0]
                if not is_guest_mode:
                    normal_hwnd_container[0] = hwnd
                pyautogui.press('alt')
                time.sleep(0.05)
                user32.ShowWindow(hwnd, 9) # Restore
                time.sleep(0.05)
                user32.ShowWindow(hwnd, 3) # Maximize
                time.sleep(0.05)
                user32.SetForegroundWindow(hwnd)
                return True
            return False

        def wait_youtube_load_tool(is_guest_mode=False, timeout=12.0):
            user32 = ctypes.windll.user32
            start_time = time.time()
            while time.time() - start_time < timeout:
                check_abort_tool()
                hwnd_list = []
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                
                def enum_cb(hwnd, lp):
                    if user32.IsWindowVisible(hwnd):
                        class_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, class_buf, 256)
                        if class_buf.value == "Chrome_WidgetWin_1":
                            len_txt = user32.GetWindowTextLengthW(hwnd)
                            if len_txt > 0:
                                buf = ctypes.create_unicode_buffer(len_txt + 1)
                                user32.GetWindowTextW(hwnd, buf, len_txt + 1)
                                title = buf.value
                                if "antigravity ide" not in title.lower() and "visual studio code" not in title.lower() and title != "Google Chrome":
                                    has_g = "guest" in title.lower()
                                    if is_guest_mode and has_g:
                                        hwnd_list.append(title)
                                    elif not is_guest_mode and not has_g:
                                        if normal_hwnd_container[0] is None or hwnd == normal_hwnd_container[0]:
                                            hwnd_list.append(title)
                    return True
                    
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
                if hwnd_list:
                    title = hwnd_list[0]
                    q_first = query.split()[0].lower() if query else "youtube"
                    if "youtube" in title.lower() and q_first in title.lower():
                        sleep_with_abort_tool(1.0)
                        return True
                sleep_with_abort_tool(0.1)
            return False

        def search_click_ocr_tool(target_word, crop_box, is_prof=False, fallback_coords=None):
            check_abort_tool()
            left, top, right, bottom = crop_box
            screenshot = pyautogui.screenshot()
            cropped_img = screenshot.crop((left, top, right, bottom))
            
            debug_path = os.path.join(os.getcwd(), f"temp_tool_crop_{'profile' if is_prof else 'video'}.png")
            cropped_img.save(debug_path)
            
            try:
                ocr._init_reader()
                reader = ocr.reader
                if not reader:
                    raise RuntimeError("OCR reader is not available.")
                results = reader.readtext(debug_path)
            finally:
                if os.path.exists(debug_path):
                    os.remove(debug_path)
                    
            valid_matches = []
            target_lower = target_word.lower().strip()
            
            for bbox, text, confidence in results:
                text_lower = text.lower().strip()
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                cx_rel = int(sum(xs) / 4)
                cy_rel = int(sum(ys) / 4)
                cx = left + cx_rel
                cy = top + cy_rel
                
                if is_prof:
                    text_clean = text_lower.replace(" ", "")
                    target_clean = target_lower.replace(" ", "")
                    is_exact = (text_lower == target_lower)
                    is_match = (is_exact or target_clean == text_clean or target_clean in text_clean)
                    if is_match:
                        valid_matches.append({
                            "text": text,
                            "center": (cx, cy),
                            "exact": is_exact
                        })
                else:
                    if target_lower in text_lower:
                        is_ad = (
                            "sponsored" in text_lower or
                            "promoted" in text_lower or
                            text_lower == "ad" or
                            "ad " in text_lower or
                            text_lower.startswith("ad ")
                        )
                        if not is_ad:
                            valid_matches.append({
                                "text": text,
                                "center": (cx, cy)
                            })
                            
            if valid_matches:
                if is_prof:
                    valid_matches.sort(key=lambda x: (not x["exact"], x["center"][1]))
                else:
                    valid_matches.sort(key=lambda x: x["center"][1])
                best_match = valid_matches[0]
                cx, cy = best_match["center"]
                pyautogui.moveTo(cx, cy, duration=0.2)
                pyautogui.click()
                if is_prof:
                    time.sleep(0.05)
                    pyautogui.click()
                return True
            else:
                if fallback_coords:
                    pyautogui.moveTo(fallback_coords[0], fallback_coords[1], duration=0.2)
                    pyautogui.click()
                    if is_prof:
                        time.sleep(0.05)
                        pyautogui.click()
                    return True
            return False

        def click_first_youtube_video_ocr(search_query: str) -> bool:
            check_abort_tool()
            width, height = pyautogui.size()
            crop_box = (200, 150, 1100, height - 50)
            left, top, right, bottom = crop_box
            
            screenshot = pyautogui.screenshot()
            cropped_img = screenshot.crop(crop_box)
            debug_path = os.path.join(os.getcwd(), "temp_youtube_results.png")
            cropped_img.save(debug_path)
            
            try:
                ocr._init_reader()
                reader = ocr.reader
                if not reader:
                    logger.warning("OCR reader not available for YouTube clicker.")
                    return False
                results = reader.readtext(debug_path)
            except Exception as e:
                logger.warning(f"YouTube OCR results search failed: {e}")
                results = []
            finally:
                if os.path.exists(debug_path):
                    os.remove(debug_path)
                    
            ignore_words = {"play", "song", "music", "video", "youtube", "by", "on", "in", "to", "a", "an", "the"}
            query_words = [w.lower() for w in search_query.split() if len(w) > 2 and w.lower() not in ignore_words]
            if not query_words:
                query_words = [w.lower() for w in search_query.split() if len(w) > 2]
            if not query_words:
                query_words = [search_query.lower()]
                
            valid_targets = []
            for bbox, text, confidence in results:
                text_lower = text.lower().strip()
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                cx_rel = int(sum(xs) / 4)
                cy_rel = int(sum(ys) / 4)
                cx = left + cx_rel
                cy = top + cy_rel
                
                is_ad = (
                    "sponsored" in text_lower or
                    "promoted" in text_lower or
                    text_lower == "ad" or
                    text_lower.startswith("ad ") or
                    " ad" in text_lower or
                    "advertisement" in text_lower
                )
                is_nav = any(term in text_lower for term in ["search", "filters", "youtube", "home", "shorts", "subscriptions", "library", "history", "views", "subscriber"])
                
                if not is_ad and not is_nav and len(text_lower) > 4:
                    match_count = sum(1 for w in query_words if w in text_lower)
                    if match_count > 0:
                        valid_targets.append({
                            "text": text,
                            "center": (cx, cy),
                            "y": cy,
                            "matches": match_count
                        })
                        
            if valid_targets:
                valid_targets.sort(key=lambda x: (-x["matches"], x["y"]))
                best_match = valid_targets[0]
                cx, cy = best_match["center"]
                logger.info(f"YouTube OCR clicked video: '{best_match['text']}' at {(cx, cy)}")
                pyautogui.moveTo(cx, cy, duration=0.2)
                pyautogui.click()
                return True
                
            logger.warning("YouTube OCR did not find any matching video titles. Falling back to blind coordinate click.")
            return False

        # Execute flow depending on arguments
        if guest_mode:
            search_query = query if query else "kavithe kavithe kannada song"
            encoded = urllib.parse.quote_plus(search_query)
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
            
            logger.info(f"Launching Guest Chrome directly to URL: {target_url}")
            subprocess.Popen(f'start chrome.exe --guest "{target_url}"', shell=True)
            
            guest_loaded = False
            for _ in range(50):
                check_abort_tool()
                if activate_chrome_tool(is_guest_mode=True):
                    guest_loaded = True
                    break
                sleep_with_abort_tool(0.1)
                
            wait_youtube_load_tool(is_guest_mode=True)
            
            pyautogui.scroll(-500)
            sleep_with_abort_tool(0.5)
            
            if not click_first_youtube_video_ocr(search_query):
                pyautogui.moveTo(600, 500, duration=0.2)
                pyautogui.click()
            
            return f"Successfully played '{search_query}' on YouTube in Guest Mode."
            
        elif profile_name:
            logger.info(f"Launching Chrome Profile Picker to select profile: {profile_name}")
            os_ctrl.open_application("chrome")
            
            picker_loaded = False
            for _ in range(50):
                check_abort_tool()
                if activate_picker_tool():
                    picker_loaded = True
                    break
                sleep_with_abort_tool(0.1)
                
            width, height = pyautogui.size()
            picker_box = (int(width * 0.2), int(height * 0.2), int(width * 0.8), int(height * 0.9))
            
            pyautogui.moveTo(1405, 555, duration=0.2)
            pyautogui.click()
            time.sleep(0.05)
            pyautogui.click()
            
            spec_success = False
            start_time = time.time()
            while time.time() - start_time < 3.0:
                check_abort_tool()
                if not activate_picker_tool():
                    spec_success = True
                    break
                sleep_with_abort_tool(0.1)
                
            if not spec_success:
                search_click_ocr_tool(profile_name, picker_box, is_prof=True, fallback_coords=(1405, 555))
                
            browser_loaded = False
            for _ in range(50):
                check_abort_tool()
                if activate_chrome_tool(is_guest_mode=False):
                    browser_loaded = True
                    break
                sleep_with_abort_tool(0.1)
                
            pyautogui.hotkey("ctrl", "l")
            sleep_with_abort_tool(0.5)
            
            search_query = query if query else "kavithe kavithe kannada song"
            encoded = urllib.parse.quote_plus(search_query)
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
            
            pyautogui.write(target_url, interval=0.005)
            sleep_with_abort_tool(0.2)
            pyautogui.press("enter")
            
            wait_youtube_load_tool(is_guest_mode=False)
            
            pyautogui.scroll(-500)
            sleep_with_abort_tool(0.5)
            
            if not click_first_youtube_video_ocr(search_query):
                pyautogui.moveTo(600, 500, duration=0.2)
                pyautogui.click()
            
            return f"Successfully played '{search_query}' on YouTube using profile '{profile_name}'."
            
        else:
            search_query = query if query else "kavithe kavithe kannada song"
            encoded = urllib.parse.quote_plus(search_query)
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
            subprocess.Popen(f'start chrome.exe "{target_url}"', shell=True)
            
            sleep_with_abort_tool(2.0)
            activate_chrome_tool(is_guest_mode=False)
            wait_youtube_load_tool(is_guest_mode=False)
            
            pyautogui.scroll(-500)
            sleep_with_abort_tool(0.5)
            
            if not click_first_youtube_video_ocr(search_query):
                pyautogui.moveTo(600, 500, duration=0.2)
                pyautogui.click()
            
            return f"Searching and playing '{search_query}' in Chrome browser."


    # 5. Communication Tools
    @registry.register("send_message", permission_level="MEDIUM")
    def send_message(message: str, recipient: str) -> str:
        """Sends WhatsApp, Telegram, or Email notification depending on formatting."""
        # Detect Telegram chat ID
        if recipient.isdigit() or recipient.startswith("-"):
            success = telegram.send_message(message, chat_id=recipient)
            return f"Telegram send result: {'Success' if success else 'Failed'}"
        # Detect Email
        elif "@" in recipient:
            # Requires credential configurations - fall back if configured or throw
            username = long_term.get_preference("smtp_user")
            password = long_term.get_preference("smtp_pass")
            if not username or not password:
                return "Aborted: Email credentials (smtp_user, smtp_pass) not configured in Preferences."
            email.send_email(username, password, recipient, "Notification from Jarvis", message)
            return f"Successfully sent email notification to {recipient}"
        # Fall back to WhatsApp Web automation
        else:
            success = whatsapp.send_whatsapp_message(recipient, message)
            return f"WhatsApp message send result: {'Success' if success else 'Failed'}"

    @registry.register("send_email", permission_level="MEDIUM")
    def send_email(to: str, subject: str, body: str) -> str:
        """Sends email via configured SMTP settings."""
        username = long_term.get_preference("smtp_user")
        password = long_term.get_preference("smtp_pass")
        if not username or not password:
            raise ValueError("Email credentials not configured in Preferences. Set 'smtp_user' and 'smtp_pass' in config.")
        email.send_email(username, password, to, subject, body)
        return f"Sent email to {to} successfully."

    # 6. Developer Agent Tools
    @registry.register("dev_create_project", permission_level="LOW")
    def dev_create_project(name: str, language: str) -> str:
        """Generates project folders and template files."""
        # Projects should reside in workspace sandbox
        workspace = os.path.dirname(os.path.abspath(__file__))
        # Get real resolved path
        resolved_workspace = os.path.abspath(os.path.join(workspace, "..", "workspace"))
        return dev_agent.create_project_structure(resolved_workspace, name, language)

    @registry.register("dev_write_code", permission_level="LOW")
    def dev_write_code(file_path: str, code: str) -> str:
        """Writes or modifies source code in target file."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        return f"Written code to {file_path}"

    @registry.register("dev_run_command", permission_level="LOW")
    def dev_run_command(command: str) -> str:
        """Executes a command (like running test scripts or installing npm dependencies)."""
        logger.info(f"Dev agent executing command: {command}")
        # Restrict environment execution within workspace path
        workspace = os.path.dirname(os.path.abspath(__file__))
        resolved_workspace = os.path.abspath(os.path.join(workspace, "..", "workspace"))
        
        result = subprocess.run(
            command,
            cwd=resolved_workspace,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return f"Exit Code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"

    @registry.register("git_commit_and_push", permission_level="HIGH")
    def git_commit_and_push(repo_path: str, commit_message: str) -> str:
        """Performs Git staging, commit, and remote push."""
        git.git_init(repo_path)
        git.git_add_all(repo_path)
        try:
            git.git_commit(repo_path, commit_message)
        except Exception:
            # If nothing to commit, proceed to push anyway
            pass
        git.git_push(repo_path)
        return "Staged, committed, and pushed changes successfully."

    logger.info("Registered all modular system tools.")
