import os
import sys
import yaml
import time
import signal
import atexit
import logging
import argparse
import threading
import socket
from typing import Dict, Any

socket.setdefaulttimeout(90.0)

# Ensure workspace packages can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from jarvis.security import SecuritySandbox, PermissionManager, CommandValidator
from jarvis.brain import OllamaModelManager, NaturalLanguageUnderstander, TaskPlanner, DeepReasoner
from jarvis.memory import ShortTermMemory, LongTermMemory, SimpleVectorStore
from jarvis.learning import PersonalityEngine
from jarvis.automation import ScreenController, OSController
from jarvis.vision import ScreenOCR, ScreenDetector
from jarvis.web import PlaywrightBrowserManager, WebScraper, WebSearch
from jarvis.communication import EmailClient, TelegramNotifier, WhatsAppWebAutomator
from jarvis.dev import GitController, DeveloperAgent
from jarvis.voice import VoiceOutputSystem
from jarvis.input import FastCommandParser, VoiceInputSystem
from jarvis.execution import ToolRegistry, ExecutionEngine
from jarvis.execution.tool_impl import register_all_tools
from jarvis.ui import JarvisOverlay

def setup_logging(log_dir: str):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "jarvis.log")
    
    # Configure logging to console and file
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

class JarvisSystem:
    def __init__(self, config_path: str):
        self.config = load_config(config_path)
        setup_logging(self.config["paths"]["logs"])
        self.logger = logging.getLogger("Jarvis.Core")
        self.logger.info("Initializing Jarvis Operating Assistant...")

        # 1. Initialize Security Sandbox & Validator
        self.sandbox = SecuritySandbox(self.config["paths"]["workspace"])
        self.permissions = PermissionManager(self.config["security"])
        self.validator = CommandValidator(self.config["security"]["whitelist_commands"])

        # 2. Initialize Model Manager & LLM pipelines
        self.model_manager = OllamaModelManager(self.config)
        self.nlu = NaturalLanguageUnderstander(self.model_manager)
        self.planner = TaskPlanner(self.model_manager)
        self.reasoner = DeepReasoner(self.model_manager)

        # 3. Initialize Memory Systems
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(self.config["paths"]["memory"])
        self.vector_store = SimpleVectorStore(self.config["paths"]["memory"])
        self.personality = PersonalityEngine(self.config["paths"]["memory"])

        # 4. Initialize Automation & OS Control
        self.screen_ctrl = ScreenController()
        self.os_ctrl = OSController()

        # 5. Initialize Vision
        self.ocr = ScreenOCR()
        self.detector = ScreenDetector(self.config)

        # 6. Initialize Web
        self.browser_mgr = PlaywrightBrowserManager(self.config)
        self.scraper = WebScraper(self.browser_mgr)
        self.searcher = WebSearch(self.browser_mgr)

        # 7. Initialize Communications
        # Telegram notification details can be loaded from Preferences dynamically
        tg_token = self.long_term.get_preference("telegram_token", "dummy")
        tg_chat = self.long_term.get_preference("telegram_chat_id", "dummy")
        self.telegram = TelegramNotifier(tg_token, tg_chat)
        self.email = EmailClient()
        self.whatsapp = WhatsAppWebAutomator(self.browser_mgr, self.config["paths"]["workspace"])

        # 8. Initialize Dev Agent
        self.git = GitController()
        self.dev_agent = DeveloperAgent(self.model_manager)

        # 9. Initialize Voice Input/Output pipelines
        self.voice_out = VoiceOutputSystem(self.config)
        self.voice_in = VoiceInputSystem(self.config)

        # 10. Start HUD overlay and wire to voice output AND voice input
        self.overlay = JarvisOverlay()
        self.voice_out.set_overlay(self.overlay)
        self.voice_in.set_overlay(self.overlay)   # live partial transcription
        self.voice_in.set_voice_out(self.voice_out)  # barge-in interrupt
        self.voice_in.set_system(self)
        self.overlay.set_command_callback(self.handle_hud_command)

        # Wire voice systems to PermissionManager for spoken confirmations
        self.permissions.set_voice_systems(self.voice_in, self.voice_out)

        # Set default user identity on first run
        if self.long_term.get_user_name() in ("User", ""):
            self.long_term.set_user_name("Kushal")
            self.long_term.add_nickname("King")
            self.long_term.remember_fact(
                "User's name is Kushal, also known as King.", permanent=True)
            self.long_term.remember_fact(
                "User prefers concise spoken answers, no bullet points.", permanent=True)

        # 11. Fast Command Parser
        self.fast_parser = FastCommandParser()

        # 12. Execution Engine & Registry
        self.registry = ToolRegistry()
        self.execution_engine = ExecutionEngine(self.registry, self.sandbox, self.permissions)

        # 13. Register tools
        register_all_tools(
            self.registry, self.screen_ctrl, self.os_ctrl, self.ocr, self.detector,
            self.browser_mgr, self.scraper, self.searcher, self.email, self.telegram,
            self.whatsapp, self.git, self.dev_agent, self.vector_store,
            self.short_term, self.long_term, self
        )

        # 14. Scan top-level system folders for accurate path indexing
        self._sys_folders = {}
        try:
            import string
            roots = []
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    roots.append(drive_path)
            user_home = os.path.expanduser("~")
            if user_home not in roots:
                roots.append(user_home)

            for r in roots:
                try:
                    for item in os.listdir(r):
                        item_path = os.path.join(r, item)
                        try:
                            if os.path.isdir(item_path) and not item.startswith("."):
                                self._sys_folders[item.lower()] = item_path
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning(f"Failed to scan system folders: {e}")

        self.last_located_path = None
        self.last_located_paths = []

        # 15. Register graceful shutdown handlers
        self._shutdown_event = threading.Event()
        self._register_shutdown_handlers()

        # 16. Pre-warm Ollama models and Florence-2 in background so the first command is instant
        def pre_warm_models():
            try:
                self.logger.info("Pre-warming Ollama models (intent and planning)...")
                self.model_manager.get_embeddings("hello")
                self.model_manager.generate(model_key="intent", prompt="hello", options={"temperature": 0.0})
                self.model_manager.chat(model_key="planning", messages=[{"role": "user", "content": "hello"}], format_json=True)
                self.logger.info("Ollama models pre-warmed successfully.")
            except Exception as e:
                self.logger.warning(f"Failed to pre-warm Ollama models: {e}")
                
            try:
                self.logger.info("Pre-warming Florence-2 vision model...")
                self.detector._init_model()
                self.logger.info("Florence-2 vision model pre-warmed successfully.")
            except Exception as e:
                self.logger.warning(f"Failed to pre-warm Florence-2 vision model: {e}")

        threading.Thread(target=pre_warm_models, daemon=True).start()
        
        self.logger.info("Jarvis System fully initialized.")

    def _register_shutdown_handlers(self):
        """Register OS-level signals and atexit hook for graceful shutdown."""
        def handler(signum=None, frame=None):
            if not self._shutdown_event.is_set():
                self._shutdown_event.set()
                self._graceful_shutdown()

        atexit.register(handler)
        signal.signal(signal.SIGINT,  handler)
        signal.signal(signal.SIGTERM, handler)
        # Windows-specific: Ctrl+Break / system shutdown
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, handler)

    def _graceful_shutdown(self):
        """Clean up all subsystems within 5 seconds for safe OS shutdown."""
        self.logger.info("Jarvis: Initiating graceful shutdown...")
        try:
            # Stop voice listener thread
            if hasattr(self, 'voice_in'):
                try:
                    self.voice_in.close()
                except Exception:
                    pass
            # Save memory state
            if hasattr(self, 'long_term'):
                try:
                    self.long_term.save()
                except Exception:
                    pass
            # Close browser
            if hasattr(self, 'browser_mgr'):
                try:
                    self.browser_mgr.close()
                except Exception:
                    pass
            # Close HUD overlay
            if hasattr(self, 'overlay'):
                try:
                    self.overlay.destroy_safe()
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        self.logger.info("Jarvis: Shutdown complete.")

    def shutdown(self):
        """Public method to trigger shutdown."""
        if not self._shutdown_event.is_set():
            self._shutdown_event.set()
            self._graceful_shutdown()

    # ── Real-time web search helper ───────────────────────────────────────

    _REALTIME_KEYWORDS = [
        "today", "now", "current", "latest", "live", "score", "result",
        "weather", "news", "stock", "price", "match", "who won", "ipl",
        "cricket", "football", "time in", "temperature", "trending",
        "this week", "right now", "what happened", "update",
    ]

    def _clean_search_query(self, query: str) -> str:
        """Strip wake words and assistant name from the search query."""
        q = query.lower()
        # Strip prefixes
        for word in ["jarvis,", "jarvis", "hey jarvis,", "hey jarvis", "hi jarvis,", "hi jarvis"]:
            if q.startswith(word):
                q = q[len(word):].strip()
        # Strip general trailing punctuation
        q = q.strip("?.!,")
        # Return cleaned query if not empty, otherwise original
        return q if q else query

    def _needs_web_search(self, text: str) -> bool:
        """Return True if the query asks for real-time information."""
        t = text.lower()
        
        # Always search for IPL / cricket queries
        if "ipl" in t or "indian premier league" in t:
            return True
            
        # Check if it matches keyword triggers
        if not any(kw in t for kw in self._REALTIME_KEYWORDS):
            return False
            
        # Exclude questions about conversation history / prompts / memory
        history_kws = ["prompt", "command", "ask", "said", "say", "earlier", "previous", "history", "remember", "conversation"]
        if any(hk in t for hk in history_kws):
            return False
            
        # Exclude simple date/time questions since they are already in the system info facts
        date_time_kws = ["date today", "today's date", "date is it today", "time is it", "current time", "what time", "what date"]
        if any(dt in t for dt in date_time_kws):
            return False
            
        # Exclude simple greetings/status questions
        greetings = ["how are you today", "how's it going today", "hello today", "hi today"]
        if any(g in t for g in greetings):
            return False
            
        return True

    def _web_search_answer(self, query: str) -> str:
        """
        Fetch Yahoo search results and ask the LLM to summarise
        them into a concise spoken answer.
        """
        try:
            import datetime
            date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
            cleaned_query = self._clean_search_query(query)
            self.logger.info(f"Web search: '{cleaned_query}' (original: '{query}')")

            # Check if query is about IPL, cricket, or general live scores/matches
            q_lower = query.lower()
            is_ipl_cricket = any(w in q_lower for w in ["ipl", "indian premier league", "cricket", "cricbuzz"])
            is_generic_score_match = any(w in q_lower for w in ["live score", "score card", "match today", "matches today", "who is playing today", "today's match"])
            if is_ipl_cricket or is_generic_score_match:
                self.logger.info("IPL/Cricket query detected — fetching programmatically.")
                return self._get_programmatic_ipl_response(query)

            results = self.searcher.search(cleaned_query, max_results=4)
            if not results:
                return ""
            snippets = "\n".join(
                f"- {r.get('title','')} : {r.get('snippet','')}"
                for r in results
            )
            prompt = (
                f"You are a search assistant. Summarize these search snippets to answer: '{cleaned_query}'.\n"
                f"Today's Date: {date_str}\n\n"
                f"Search Snippets:\n{snippets}\n\n"
                f"Response (concise, 1-2 sentences, no cutoff disclaimers, no markdown):"
            )
            answer = self.model_manager.generate(model_key="intent", prompt=prompt, options={"temperature": 0.0})
            return answer.strip()
        except Exception as e:
            self.logger.error(f"Web search failed: {e}")
            return ""

    def _background_chrome_search_fallback(self, query: str):
        """
        Launches Google Chrome to search Google, open the first link, 
        and read the screen via OCR. Runs in a background thread.
        """
        def run_fallback():
            try:
                import urllib.parse
                import time
                import ctypes
                import pyautogui
                import subprocess
                
                self.logger.info(f"Starting background Chrome search fallback for: '{query}'")
                
                # Step 1: Open Google Chrome with the search query
                encoded_query = urllib.parse.quote_plus(query)
                search_url = f"https://www.google.com/search?q={encoded_query}"
                self.logger.info(f"Launching Chrome to: {search_url}")
                
                # Speak/Overlay notification to the user
                self.overlay.show_live_text("Opening Chrome to search...")
                self._say("Opening Chrome to search...")
                
                subprocess.Popen(f'start chrome.exe "{search_url}"', shell=True)
                
                # Step 2: Wait for Chrome to open and load the page
                time.sleep(4.0)
                
                # Step 3: Activate/Focus Google Chrome window
                user32 = ctypes.windll.user32
                hwnd_list = []
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                
                def enum_cb(hwnd, lp):
                    if user32.IsWindowVisible(hwnd):
                        class_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, class_buf, 256)
                        if class_buf.value == "Chrome_WidgetWin_1":
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
                
                time.sleep(1.5)
                
                # Step 4: Run Screen OCR on the Google search results page to find links
                self.logger.info("Running OCR to find search links...")
                ocr_items = self.ocr.capture_and_read()
                
                # Find a link to click.
                # Filter out standard Google headers and navigation.
                click_target = None
                for item in ocr_items:
                    text = item["text"].lower()
                    cx, cy = item["center"]
                    # Google search results are usually in the middle-left of the screen (e.g. x between 100 and 800, y > 250)
                    if 100 < cx < 800 and cy > 250:
                        # Exclude navigation/UI terms
                        exclude_terms = [
                            "google", "images", "videos", "news", "maps", "shopping", "books", "search settings", 
                            "sign in", "about", "feedback", "privacy", "terms", "people also ask", "sponsored", "ad"
                        ]
                        if not any(term in text for term in exclude_terms) and len(text) > 10:
                            click_target = item
                            break
                
                if click_target:
                    self.logger.info(f"Clicking link: '{click_target['text']}' at {click_target['center']}")
                    pyautogui.moveTo(click_target["center"][0], click_target["center"][1], duration=0.5)
                    pyautogui.click()
                    
                    # Wait for page to load
                    time.sleep(6.0)
                    
                    # Step 5: Read screen again to extract the webpage content
                    self.logger.info("Reading webpage screen content via OCR...")
                    page_items = self.ocr.capture_and_read()
                    all_text = " ".join([item["text"] for item in page_items])
                    
                    # Ask LLM to summarize based on screen text
                    prompt = (
                        f"You are a search assistant. Based on this text extracted from the user's browser screen, "
                        f"provide a concise 1-2 sentence answer to: '{query}'.\n\n"
                        f"Screen Text:\n{all_text[:3000]}\n\n"
                        f"Answer:"
                    )
                    answer = self.model_manager.generate(model_key="intent", prompt=prompt, options={"temperature": 0.0})
                    self.logger.info(f"Chrome fallback answer: {answer}")
                    
                    # Notify user
                    self.short_term.add_message("assistant", answer)
                    self.overlay.show_live_text(answer)
                    self._say(answer)
                else:
                    self.logger.warning("No clickable links found on Google Search results page.")
                    # If we couldn't find a link, let's just read the search results page itself
                    all_text = " ".join([item["text"] for item in ocr_items])
                    prompt = (
                        f"You are a search assistant. Based on this text extracted from the Google Search results screen, "
                        f"provide a concise 1-2 sentence answer to: '{query}'.\n\n"
                        f"Screen Text:\n{all_text[:3000]}\n\n"
                        f"Answer:"
                    )
                    answer = self.model_manager.generate(model_key="intent", prompt=prompt, options={"temperature": 0.0})
                    self.short_term.add_message("assistant", answer)
                    self.overlay.show_live_text(answer)
                    self._say(answer)
                    
            except Exception as e:
                self.logger.error(f"Background Chrome search fallback failed: {e}", exc_info=True)
                
        import threading
        threading.Thread(target=run_fallback, daemon=True).start()

    def handle_hud_command(self, cmd: str):
        """Callback for processing commands entered directly in the HUD overlay text entry."""
        self.logger.info(f"Command received from HUD Entry: '{cmd}'")
        self.overlay.reset_sleep_timer()
        self.overlay.set_state("thinking")
        self.overlay.show_live_text(cmd)
        
        # Execute command flow
        response = self.run_command_flow(cmd)
        
        # Speak and show response
        self.overlay.set_state("speaking")
        self._say(response)
        self.overlay.set_state("idle")

    def run_command_flow(self, user_input: str) -> str:
        """
        Main execution flow:
        Web Search (realtime) → Fast Parser → NLU → Executor / Direct / Reasoner
        """
        self.logger.info(f"Received Command: '{user_input}'")

        # Quick greeting & simple conversational interception
        t_clean = user_input.lower().strip("?.!, \t\n\r")
        
        # Pause & Resume check
        if t_clean in ["continue", "resume", "carry on", "go on"]:
            if hasattr(self.voice_out, "_interrupted_remaining") and self.voice_out._interrupted_remaining:
                rem = " ".join(self.voice_out._interrupted_remaining)
                self.voice_out._interrupted_remaining = []
                self.overlay.show_live_text("Continuing...")
                self._say(rem)
                return f"Continuing: {rem}"
            else:
                response = "There is nothing to continue."
                self.short_term.add_message("assistant", response)
                return response
        
        # Clean wake words from the greeting check
        t_clean_g = t_clean
        for prefix in ["hey jarvis", "hi jarvis", "hello jarvis", "jarvis"]:
            if t_clean_g.startswith(prefix):
                t_clean_g = t_clean_g[len(prefix):].strip("?.!, \t\n\r")
                break
        
        greetings = {
            "hi": f"Hello {self._get_name()}! How can I help you today?",
            "hey": f"Hey {self._get_name()}! What's on your mind?",
            "hello": f"Hello {self._get_name()}! How can I assist you?",
            "good morning": f"Good morning {self._get_name()}! Hope you have a great day. How can I help?",
            "good afternoon": f"Good afternoon {self._get_name()}! How can I help you?",
            "good evening": f"Good evening {self._get_name()}! How can I assist you tonight?",
            "how are you": "I'm doing great, thank you for asking! How can I help you?",
            "how are you today": "I am operating at peak efficiency today. How can I help you?",
            "how's it going": "Everything is running smoothly! How can I assist you?",
            "what's up": "Not much! Just here and ready to help. What's on your mind?",
            "sup": "Not much! Ready to help you. What's on your mind?",
            "thank you": "You're very welcome!",
            "thanks": "My pleasure! Happy to help.",
            "thank you jarvis": "You're very welcome!",
            "thanks jarvis": "My pleasure! Happy to help.",
            "who are you": "I am Jarvis, your voice-activated operating assistant. How can I help you today?",
            "what is your name": "I am Jarvis, your voice-activated operating assistant.",
        }
        
        # Match against either the cleaned-wake-word version or full text
        response_found = None
        if t_clean_g in greetings:
            response_found = greetings[t_clean_g]
        elif t_clean in greetings:
            response_found = greetings[t_clean]
            
        if response_found:
            self.short_term.add_message("assistant", response_found)
            return response_found

        if t_clean in ["clear screen", "clear response", "clear hud", "clear text"]:
            self.overlay.clear_live_text()
            # Clear response typewriter/text area
            def _clear_resp():
                try:
                    self.overlay._txt_resp.config(state="normal")
                    self.overlay._txt_resp.delete("1.0", "end")
                    self.overlay._txt_resp.config(state="disabled")
                except Exception:
                    pass
            self.overlay.root.after(0, _clear_resp)
            response = "HUD display cleared."
            self.short_term.add_message("assistant", response)
            return response

        # Codeword substitution: check if user input references HUD entry text
        if hasattr(self, "overlay") and self.overlay:
            entry_val = self.overlay.get_entry_text()
            if entry_val:
                codewords = ["text prompt", "prompttext", "prompt text", "with text", "using text", "read text", "read prompt"]
                substituted = False
                for cw in codewords:
                    if cw in user_input.lower():
                        import re
                        pattern = re.compile(re.escape(cw), re.IGNORECASE)
                        user_input = pattern.sub(entry_val, user_input)
                        substituted = True
                        break
                if substituted:
                    self.logger.info(f"Substituted codeword in voice command. New command: '{user_input}'")
                    # Clear the entry text since it has been consumed
                    self.overlay.clear_entry_text()

        self.short_term.add_message("user", user_input)

        # ── USER UNDERSTANDING & PERSONALITY SYSTEM ──
        # 1. Intercept Memory Reset
        t_clean = user_input.lower().strip("?.!, \t\n\r")
        if t_clean in ["clear my memory", "forget everything", "reset learning", "clear memory"]:
            self.personality.reset_memory()
            self.long_term.reset_memory()
            output = "I have cleared all of my memory and personalized learning profiles. I am restarting fresh."
            self.short_term.add_message("assistant", output)
            return output

        # 2. Intercept Synonym Registration / Learning Shortcut
        import re
        alias_match = re.search(r"^alias\s+(.+?)\s+to\s+(.+)$", t_clean, re.IGNORECASE)
        if not alias_match:
            alias_match = re.search(r"^learn\s+that\s+(.+?)\s+means\s+(.+)$", t_clean, re.IGNORECASE)
        if alias_match:
            phrase = alias_match.group(1).strip()
            canonical = alias_match.group(2).strip()
            self.personality.learn_synonym(phrase, canonical)
            output = f"Got it! I've learned that '{phrase}' means '{canonical}'."
            self.short_term.add_message("assistant", output)
            return output

        # 3. Resolve synonyms
        resolved_input = self.personality.resolve_synonyms(user_input)
        if resolved_input != user_input:
            self.logger.info(f"Resolved synonym: '{user_input}' -> '{resolved_input}'")

        # 4. Personality Analysis (Mood, slang mapping, skill updates)
        p_analysis = self.personality.analyze(resolved_input)
        self.personality.update_skill_level(resolved_input)
        
        # 5. Resolve contextual queries (it, yesterday, project, him)
        cmd_text = self._resolve_contextual_query(p_analysis["normalized"])
        if cmd_text != p_analysis["normalized"]:
            self.logger.info(f"Resolved context: '{p_analysis['normalized']}' -> '{cmd_text}'")

        t_lower = cmd_text.lower()
        t_clean = t_lower.strip("?.!,")

        # Intercept follow-up commands referencing the last located path
        if self.last_located_path:
            # 1. Open follow-ups
            open_kws = ["open it", "open that", "open the folder", "open that folder", "open the file", "open that file", "open path", "open last path"]
            if any(t_clean == kw for kw in open_kws) or t_clean.startswith("open the located"):
                self.logger.info(f"Intercepted follow-up open command for path: {self.last_located_path}")
                res = self._execute_single_tool("open_path", {"path": self.last_located_path})
                self.short_term.add_message("assistant", res)
                return res
            
            # 2. Read follow-ups
            read_kws = ["read it", "read that", "read the file", "read that file", "read content", "read the content"]
            if any(t_clean == kw for kw in read_kws):
                self.logger.info(f"Intercepted follow-up read command for path: {self.last_located_path}")
                if os.path.isdir(self.last_located_path):
                    res = f"The located path '{self.last_located_path}' is a directory, not a file. Would you like me to open it or list its contents?"
                else:
                    res = self._execute_single_tool("read_file_content", {"file_path": self.last_located_path})
                self.short_term.add_message("assistant", res)
                return res

            # 3. List files follow-ups
            list_kws = ["list it", "list files in it", "list files in that", "list files", "show files in it", "show files", "what is in it", "what is in there"]
            if any(t_clean == kw for kw in list_kws):
                self.logger.info(f"Intercepted follow-up list files command for path: {self.last_located_path}")
                if os.path.isfile(self.last_located_path):
                    res = f"The located path '{self.last_located_path}' is a file, not a directory. You can read its content instead."
                else:
                    res = self._execute_single_tool("list_files", {"path": self.last_located_path})
                self.short_term.add_message("assistant", res)
                return res

        # Intercept folder/file location questions
        if any(w in t_lower for w in ["where is", "find", "locate", "path of"]) and any(w in t_lower for w in ["folder", "directory", "file", "path"]):
            target_name = self._extract_target_name(cmd_text)
            if target_name:
                matched_folders = []
                target_words = [w for w in target_name.split() if len(w) > 2]
                
                # Check cache
                for folder_name, folder_path in self._sys_folders.items():
                    if target_name in folder_name or folder_name in target_name or (target_words and any(w in folder_name for w in target_words)):
                        matched_folders.append((folder_name, folder_path))
                
                # Walk system dynamically if not in cache
                if not matched_folders:
                    self.logger.info(f"Folder '{target_name}' not in cache. Scanning drives dynamically...")
                    scanned_matches = self._locate_on_system(target_name)
                    for path in scanned_matches:
                        basename = os.path.basename(path).lower()
                        self._sys_folders[basename] = path
                        matched_folders.append((basename, path))
                
                if matched_folders:
                    seen = set()
                    unique_matches = []
                    for fname, fpath in matched_folders:
                        if fpath.lower() not in seen:
                            seen.add(fpath.lower())
                            unique_matches.append((fname, fpath))
                    
                    # Store the matched paths
                    self.last_located_paths = [fp for _, fp in unique_matches]
                    self.last_located_path = self.last_located_paths[0] if self.last_located_paths else None
                    
                    desc_list = []
                    for fname, fpath in unique_matches[:3]:
                        drive, _ = os.path.splitdrive(fpath)
                        drive_letter = drive.replace(":", "").upper() if drive else ""
                        
                        is_outside = True
                        try:
                            wp = os.path.abspath(self.config['paths']['workspace'])
                            fp = os.path.abspath(fpath)
                            if fp.startswith(wp):
                                is_outside = False
                        except Exception:
                            pass
                        
                        loc_desc = f"at path {fpath}"
                        if drive_letter:
                            loc_desc = f"on the {drive_letter} drive at path {fpath}"
                        
                        outside_desc = " (outside the Jarvis workspace)" if is_outside else ""
                        desc_list.append(f"the '{fname}' folder is located {loc_desc}{outside_desc}")
                    
                    output = "I found it: " + " and ".join(desc_list) + "."
                    self.short_term.add_message("assistant", output)
                    return output
                else:
                    output = f"I couldn't find any folder or file named '{target_name}' on your system."
                    self.short_term.add_message("assistant", output)
                    return output

        # Step A: Check Fast Command Parser
        fast_plan = self.fast_parser.parse(cmd_text)
        if fast_plan:
            self.logger.info("Direct Match: Executing fast-track command bypass.")
            res = self.execution_engine.execute_plan(fast_plan)
            if res.get("status") == "SUCCESS":
                for step in fast_plan.get("steps", []):
                    self._log_tool_usage_to_profile(step.get("tool"), step.get("args", {}))
            output = f"Fast Execution Result: {res.get('status')}. Results: {res.get('results')}"
            self.short_term.add_message("assistant", output)
            return output

        # Step B: LLM-based NLU Classification
        nlu_analysis   = self.nlu.analyze(cmd_text)
        classification = nlu_analysis.get("classification", "DIRECT")

        if classification == "COMMAND":
            self.logger.info("NLU classified as COMMAND. Building execution graph...")
            
            max_attempts = 3
            attempt = 0
            last_error = None
            plan_context_addition = ""
            plan = None
            res = None
            
            while attempt < max_attempts:
                attempt += 1
                self.logger.info(f"Task planning & execution attempt {attempt}/{max_attempts}...")
                
                query_embed = self.model_manager.get_embeddings(cmd_text)
                memories    = self.vector_store.search(query_embed, top_k=2)
                context = {
                    "recent_history":   self.short_term.get_context_messages()[-4:],
                    "semantic_memories": [m["text"] for m in memories],
                    "user_name":         self.long_term.get_user_name(),
                    "last_located_path": self.last_located_path,
                    "last_file":         self.personality.context.get("last_file"),
                    "last_project":      self.personality.context.get("last_project"),
                    "last_app":          self.personality.context.get("last_app"),
                    "last_person":       self.personality.context.get("last_person"),
                }
                
                # Feed error back to the planner on retry
                if last_error:
                    context["previous_attempt_error"] = last_error
                    context["retry_count"] = attempt - 1
                
                # Generate the plan (with context updates)
                plan = self.planner.plan_task(cmd_text + plan_context_addition, context)
                
                # Execute
                res = self.execution_engine.execute_plan(plan)
                
                if res.get("status") == "SUCCESS":
                    self.logger.info(f"Plan executed successfully on attempt {attempt}.")
                    break
                else:
                    last_error = res.get("message")
                    self.logger.warning(f"Plan execution attempt {attempt} failed with error: {last_error}")
                    # Guide the planner to correct the error on the next attempt
                    plan_context_addition = (
                        f" (Note: A previous attempt to execute this request failed with error: '{last_error}'. "
                        f"Please generate a new, corrected plan to accomplish the user's task using alternative tools, "
                        f"correct file paths, or different arguments as needed.)"
                    )
            
            if res.get("status") == "SUCCESS":
                results_str = ""
                for r in res.get("results", []):
                    results_str += f"Tool: {r.get('tool')}\nOutput: {r.get('output')}\n\n"
                
                prompt = (
                    f"You are Jarvis, an intelligent, friendly conversational AI assistant.\n"
                    f"The user requested: \"{cmd_text}\"\n"
                    f"You planned and executed tools successfully to fulfill this. Here are the tools and their outputs:\n\n"
                    f"{results_str}\n"
                    f"Based on the tool outputs, provide a warm, natural, and conversational human-like response to the user's request. "
                    f"If the tool read or described the screen, explain what is on the screen and what needs to be done. "
                    f"Address the user as {self._get_name()}.\n"
                    f"Reply in 2-3 sentences max. Spoken sentences only, no markdown, no lists."
                )
                
                # Dynamic Response Model Selection:
                # If explaining code, screen, debugging, or complex outputs, route to 'planning' (7B) for high quality
                use_model = "intent"
                if any(w in cmd_text.lower() for w in ["explain", "debug", "code", "why", "error", "fail", "create", "program"]):
                    use_model = "planning"  # qwen2.5:7b-instruct is excellent at explaining code/commands
                    
                self.logger.info(f"Routing final response generation to model key: '{use_model}'")
                output = self.model_manager.generate(model_key=use_model, prompt=prompt, options={"temperature": 0.0}).strip()
                
                for step in plan.get("steps", []):
                    self._log_tool_usage_to_profile(step.get("tool"), step.get("args", {}))
                self.vector_store.add_item(
                    text=f"Executed command: '{cmd_text}' successfully. Output: {output}",
                    embedding=self.model_manager.get_embeddings(cmd_text),
                    metadata={"type": "command_success"},
                )
            else:
                output = f"I tried to complete the task {max_attempts} times, but encountered errors: {res.get('message')}"
            
            self.short_term.add_message("assistant", output)
            return output

        elif classification == "THINKING":
            self.logger.info("NLU classified as THINKING. Launching Deep Reasoner...")
            response = self.reasoner.think(cmd_text)
            self.short_term.add_message("assistant", response)
            return response

        else:
            # DIRECT — conversational / knowledge answer
            # Check if it needs real-time web search
            web_search_attempted = False
            if self._needs_web_search(cmd_text):
                self.logger.info("Query needs live data — running web search.")
                answer = self._web_search_answer(cmd_text)
                web_search_attempted = True
                if answer:
                    self.short_term.add_message("assistant", answer)
                    return answer
                else:
                    self.logger.warning("Yahoo web search returned empty. Triggering background Chrome fallback...")
                    self._background_chrome_search_fallback(cmd_text)
                    msg = "I couldn't find results immediately. I'm opening Chrome in the background to search and read the screen for you."
                    self.short_term.add_message("assistant", msg)
                    return msg

            self.logger.info("NLU classified as DIRECT. Querying quick response...")
            response = self.model_manager.generate(
                model_key="intent", prompt=self._build_prompt(cmd_text, p_analysis), options={"temperature": 0.0})
            
            # Fallback search if the response mentions a knowledge cutoff
            resp_lower = response.lower()
            cutoff_phrases = [
                "2023", "cutoff", "cut-off", "real-time", "real time",
                "do not have access", "don't have access", "current information",
                "as an ai", "limitations"
            ]
            if any(p in resp_lower for p in cutoff_phrases) and not web_search_attempted:
                self.logger.info("Direct response mentioned knowledge cutoff or limits. Triggering fallback web search...")
                search_ans = self._web_search_answer(cmd_text)
                if search_ans:
                    response = search_ans
                else:
                    self.logger.warning("Yahoo fallback web search failed/empty. Triggering background Chrome fallback...")
                    self._background_chrome_search_fallback(cmd_text)
                    response = "I'm opening Google Chrome in the background to search and read the details from the screen."
            
            self.short_term.add_message("assistant", response)
            self.personality.record_exchange(cmd_text, response)
            return response


    def _get_name(self) -> str:
        """Return the preferred name to address the user."""
        return self.long_term.get_display_name() or "there"

    def _say(self, text: str):
        """Speak and show in HUD overlay."""
        self.voice_out.speak(text, block=True)

    def _web_search_simple(self, query: str) -> str:
        """
        HTTP-only Yahoo search — no browser required.
        Returns a short summary via Ollama.
        """
        import urllib.request, urllib.parse
        from bs4 import BeautifulSoup
        import datetime

        try:
            date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
            cleaned_query = self._clean_search_query(query)
            self.logger.info(f"HTTP web search: '{cleaned_query}' (original: '{query}')")

            # Check if query is about IPL, cricket, or general live scores/matches
            q_lower = query.lower()
            is_ipl_cricket = any(w in q_lower for w in ["ipl", "indian premier league", "cricket", "cricbuzz"])
            is_generic_score_match = any(w in q_lower for w in ["live score", "score card", "match today", "matches today", "who is playing today", "today's match"])
            if is_ipl_cricket or is_generic_score_match:
                self.logger.info("IPL/Cricket query detected — fetching programmatically.")
                return self._get_programmatic_ipl_response(query)

            enc = urllib.parse.quote_plus(cleaned_query)
            url = f"https://search.yahoo.com/search?q={enc}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            soup = BeautifulSoup(html, "html.parser")
            results = []
            for result_div in soup.find_all("div", class_=lambda x: x and "algo" in x.split()):
                title_h3 = result_div.find("h3", class_=lambda x: x and "title" in x.split())
                if not title_h3:
                    continue
                title = title_h3.get_text().strip()
                
                parent_a = title_h3.find_parent("a")
                if not parent_a:
                    continue
                
                snippet_div = result_div.find("div", class_=lambda x: x and "compText" in x.split())
                snippet = snippet_div.get_text().strip() if snippet_div else ""
                
                # Sanitize text
                title = "".join(c for c in title if c.isprintable())
                snippet = "".join(c for c in snippet if c.isprintable())
                
                results.append(f"- Title: {title}\n  Snippet: {snippet}")
                if len(results) >= 5:
                    break

            if not results:
                return ""

            context = "\n".join(results)
            prompt = (
                f"You are a search assistant. Summarize these search snippets to answer: '{cleaned_query}'.\n"
                f"Today's Date: {date_str}\n\n"
                f"Search Snippets:\n{context}\n\n"
                f"Response (concise, 1-2 sentences, no cutoff disclaimers, no markdown):"
            )
            answer = self.model_manager.generate(model_key="intent", prompt=prompt, options={"temperature": 0.0})
            return answer.strip()
        except Exception as e:
            self.logger.error(f"HTTP web search failed: {e}")
            return ""

    def voice_interaction_loop(self, startup_greeting: bool = False):
        """
        Continuous voice loop with:
          - Step-by-step narration (Jarvis says what it's doing)
          - User addressed by name (King / Kushal)
          - HTTP web search for live queries (no browser needed)
          - Barge-in: say 'Jarvis' mid-speech to interrupt
          - Memory extraction from conversations
        """
        name = self._get_name()
        prediction = self.personality.predict_next_action()
        suggestion = ""
        if prediction:
            suggestion = f" Based on your habits, would you like me to {prediction}?"

        if startup_greeting:
            time.sleep(0.8)
            self.overlay.set_state("speaking")
            self._say(
                f"Hello {name}! Jarvis is online. "
                f"Systems are ready.{suggestion} Say Jarvis anytime to command me.")
        else:
            self.overlay.set_state("speaking")
            self._say(f"Voice mode activated. Say Jarvis to wake me, {name}.{suggestion}")

        self.overlay.set_state("idle")
        self.overlay.reset_sleep_timer()

        def on_wake_word():
            name = self._get_name()
            was_sleeping = (self.overlay._state == self.overlay.STATE_SLEEPING)

            # Clear any leftover interrupt flag from previous barge-in
            self.voice_out.clear_interrupt()

            self.overlay.wake_from_sleep()
            self.overlay.set_state("listening")
            self.overlay.reset_sleep_timer()

            # Check if there is active user speech in the queue (single-breath command)
            if self.voice_in.has_active_speech_in_queue():
                self.logger.info("Single-breath command detected. Processing immediately.")
                self.overlay.set_state("listening")
                self.overlay.show_text("Listening…")
                transcription = self.voice_in.record_and_transcribe(bypass_delay=True)
            else:
                self.logger.info("User paused after wake word or was sleeping. Speaking wake greeting.")
                self._say(f"Yes, {name}?")
                self.overlay.set_state("listening")
                self.overlay.show_text("Listening…")
                transcription = self.voice_in.record_and_transcribe(bypass_delay=False)

            if not transcription.strip():
                if was_sleeping:
                    self._say("I didn't catch that. Please try again.")
                self.overlay.set_state("idle")
                return

            self.logger.info(f"Command: '{transcription}'")
            self.overlay.set_state("thinking")
            self.overlay.show_live_text(transcription)

            # Direct check for sleep command
            t_lower = transcription.strip().lower().rstrip("?.!")
            if t_lower in ["go to sleep", "sleep", "goodnight", "shutdown voice", "exit voice"]:
                self._say("Goodnight. Say Jarvis to wake me up.")
                self.overlay._go_to_sleep()
                return

            # Direct check for just saying the wake word
            if t_lower in ["jarvis", "hey jarvis", "hi jarvis"]:
                self._say(f"Yes, {name}?")
                self.overlay.set_state("idle")
                return

            # Direct check for text area request
            if any(w in t_lower for w in ["give text area", "show text area", "give text input", "show text input", "open text box", "i can't spell", "i cant spell"]):
                self.overlay.set_state("speaking")
                self._say("Sure, opening text entry area.")
                typed_text = self.get_themed_text_input("Jarvis Text Entry", "Please type your input or command:")
                if typed_text.strip():
                    self.logger.info(f"User entered text via popup: '{typed_text}'")
                    response = self.run_command_flow(typed_text)
                    self.overlay.set_state("speaking")
                    self._say(response)
                    self._extract_and_remember(typed_text, response)
                self.overlay.set_state("idle")
                return

            # ── Route query ───────────────────────────────────────────────
            try:
                # Intercept folder/file location questions directly for voice loop
                if any(w in t_lower for w in ["where is", "find", "locate", "path of"]) and any(w in t_lower for w in ["folder", "directory", "file", "path"]):
                    target_name = self._extract_target_name(transcription)
                    if target_name:
                        matched_folders = []
                        target_words = [w for w in target_name.split() if len(w) > 2]
                        for folder_name, folder_path in self._sys_folders.items():
                            if target_name in folder_name or folder_name in target_name or (target_words and any(w in folder_name for w in target_words)):
                                matched_folders.append((folder_name, folder_path))
                        
                        if not matched_folders:
                            self.logger.info(f"Folder '{target_name}' not in cache. Scanning drives dynamically...")
                            scanned_matches = self._locate_on_system(target_name)
                            for path in scanned_matches:
                                basename = os.path.basename(path).lower()
                                self._sys_folders[basename] = path
                                matched_folders.append((basename, path))
                        
                        if matched_folders:
                            seen = set()
                            unique_matches = []
                            for fname, fpath in matched_folders:
                                if fpath.lower() not in seen:
                                    seen.add(fpath.lower())
                                    unique_matches.append((fname, fpath))
                            
                            # Store the matched paths
                            self.last_located_paths = [fp for _, fp in unique_matches]
                            self.last_located_path = self.last_located_paths[0] if self.last_located_paths else None
                            
                            desc_list = []
                            for fname, fpath in unique_matches[:3]:
                                drive, _ = os.path.splitdrive(fpath)
                                drive_letter = drive.replace(":", "").upper() if drive else ""
                                
                                is_outside = True
                                try:
                                    wp = os.path.abspath(self.config['paths']['workspace'])
                                    fp = os.path.abspath(fpath)
                                    if fp.startswith(wp):
                                        is_outside = False
                                except Exception:
                                    pass
                                
                                loc_desc = f"at path {fpath}"
                                if drive_letter:
                                    loc_desc = f"on the {drive_letter} drive at path {fpath}"
                                
                                outside_desc = " (outside the Jarvis workspace)" if is_outside else ""
                                desc_list.append(f"the '{fname}' folder is located {loc_desc}{outside_desc}")
                            
                            response = "I found it: " + " and ".join(desc_list) + "."
                        else:
                            response = f"I couldn't find any folder or file named '{target_name}' on your system."
                        
                        self.short_term.add_message("user", transcription)
                        self.short_term.add_message("assistant", response)
                        self.overlay.set_state("speaking")
                        self._say(response)
                        self.overlay.set_state("idle")
                        self.overlay.reset_sleep_timer()
                        return

                # Narrate searching if it's a web search
                if self._needs_web_search(transcription):
                    self._say("Let me search that for you.")
                    self.overlay.set_state("thinking")
                    self.overlay.show_text("Searching the web…")

                # Route standard queries through run_command_flow
                response = self.run_command_flow(transcription)

                # ── Speak response ────────────────────────────────────────
                if response and response.strip():
                    self.overlay.set_state("speaking")
                    self._say(response)
                    # Learn from this exchange
                    self._extract_and_remember(transcription, response)
                else:
                    self._say("I'm not sure about that. Try asking differently.")

            except Exception as e:
                self.logger.error(f"Voice command error: {e}", exc_info=True)
                self._say("Sorry, something went wrong. Please try again.")

            self.overlay.set_state("idle")
            self.overlay.reset_sleep_timer()

        self.voice_in.listen_for_wakeword(on_wake_word)

        try:
            while not self._shutdown_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Voice loop terminated by user.")
        finally:
            self.voice_in.close()

    def _extract_target_name(self, text: str) -> str:
        """Extracts the folder or file name from questions like 'Where is X folder?'"""
        t = text.lower()
        
        # Strip conversational fillers/prefixes
        prefixes = [
            "can you check where is the", "can you check where is my", "can you check where is",
            "do you know where is the", "do you know where is my", "do you know where is",
            "where is the", "where is my", "where is", 
            "find my", "find the", "find", 
            "locate my", "locate the", "locate",
            "where can i find the", "where can i find my", "where can i find",
            "show me the location of the", "show me the location of my", "show me the location of"
        ]
        # Sort prefixes by length descending so we match the longest one first
        prefixes.sort(key=len, reverse=True)
        for pattern in prefixes:
            if t.startswith(pattern):
                t = t[len(pattern):].strip()
                break
                
        # Strip trailing fillers/suffixes
        suffixes = [
            "in my laptop", "on my laptop", "in my computer", "on my computer", 
            "in my pc", "on my pc", "in my system", "on my system",
            "folder located", "folder is located", "folder", 
            "directory located", "directory is located", "directory", 
            "project folder", "project directory", "project",
            "file located", "file is located", "file"
        ]
        
        # Repeatedly clean suffixes and whitespace
        changed = True
        while changed:
            changed = False
            t = t.strip("?.!, \t\n\r")
            for suffix in suffixes:
                if t.endswith(suffix):
                    t = t[:-len(suffix)].strip()
                    changed = True
                    break
        
        t = t.strip("?.!, \t\n\r")
        return t

    def _locate_on_system(self, name: str) -> list:
        """Scans all drives dynamically for folders/files matching name."""
        import string
        drives = []
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(drive_path)
        
        matches = []
        name_lower = name.lower()
        skip_dirs = {
            "windows", "program files", "program files (x86)", "programdata",
            "appdata", "node_modules", ".git", "venv", "env", "$recycle.bin",
            "system volume information", "microsoft", "cache", "tmp", "temp"
        }
        
        for drive in drives:
            try:
                for root, dirs, files in os.walk(drive):
                    # Filter dirs in-place to avoid walking huge folders
                    dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith(".")]
                    
                    depth = root.count(os.sep) - drive.count(os.sep)
                    if depth > 6:  # Walk up to 6 levels deep
                        dirs.clear()
                        continue
                    
                    for d in dirs:
                        if name_lower in d.lower():
                            matches.append(os.path.join(root, d))
                    for f in files:
                        if name_lower in f.lower():
                            matches.append(os.path.join(root, f))
                            
                    if len(matches) >= 10:
                        break
            except Exception:
                pass
            if len(matches) >= 10:
                break
        return matches

    def _fetch_cricbuzz_ipl_score(self) -> str:
        """Fetch real-time IPL scores and schedules from Cricbuzz using regex text extraction."""
        import urllib.request
        from bs4 import BeautifulSoup
        import re
        try:
            url = "https://www.cricbuzz.com/cricket-match/live-scores"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()
            clean_text = re.sub(r'\s+', ' ', text)
            
            # 1. Get live scorecards (length <= 400 matches under league)
            live_scores = []
            pattern = r'(Indian Premier League \d{4}|Indian Premier League|IPL \d{4})[^|]*?(?=Live Score|Scorecard|Full Commentary|Preview|Match Centre)'
            for m in re.finditer(pattern, clean_text):
                match_str = m.group(0).strip()
                if len(match_str) > 400:
                    continue
                match_str = "".join(c for c in match_str if c.isprintable())
                match_str = re.sub(r'\s+', ' ', match_str)
                if match_str not in live_scores:
                    live_scores.append(match_str)

            # 2. Get full schedule list under LEAGUE IPL
            schedule_matches = []
            ipl_block_match = re.search(r'LEAGUE\s*IPL[^\w]*(.*?)(?=T20 Blast|DOMESTIC|WOMEN|INTERNATIONAL|$)', clean_text, re.IGNORECASE)
            if ipl_block_match:
                block_text = ipl_block_match.group(1)
                pattern_sched = r'([A-Za-z0-9\s\'\-\&]+? vs [A-Za-z0-9\s\'\-\&]+?(?:LIVE)?\s*\d+(?:st|nd|rd|th)\s*Match)'
                sched_matches = re.findall(pattern_sched, block_text)
                for sm in sched_matches:
                    sm_clean = re.sub(r'\s+', ' ', "".join(c for c in sm if c.isprintable())).strip()
                    sm_clean = re.sub(r'^\d+', '', sm_clean).strip()  # Remove leading year digits
                    schedule_matches.append(sm_clean)

            # 3. Get header quick status list (MATCHES list)
            quick_statuses = []
            matches_header = re.search(r'MATCHES(.*?)(?=ALL|All|Live Now|Today)', clean_text, re.IGNORECASE)
            if matches_header:
                header_text = matches_header.group(1)
                pattern_qs = r'([A-Z]{2,4}\s+vs\s+[A-Z]{2,4}\s*-\s*.*?)(?=[A-Z]{2,4}\s+vs|$)'
                matches_found = re.findall(pattern_qs, header_text)
                for m in matches_found:
                    m_clean = re.sub(r'\s+', ' ', "".join(c for c in m if c.isprintable())).strip()
                    quick_statuses.append(m_clean)

            # Build the combined response
            output_lines = []
            
            if live_scores:
                output_lines.append("Live Matches:")
                for score in live_scores:
                    score_clean = self._clean_live_score_text(score)
                    output_lines.append(f"- {score_clean}")
            else:
                ipl_quick = [qs for qs in quick_statuses if any(team in qs for team in ["RR", "MI", "KKR", "DC", "LSG", "PBKS", "CSK", "RCB", "SRH", "GT"])]
                if ipl_quick:
                    output_lines.append("Live Score Overview:")
                    for qs in ipl_quick:
                        output_lines.append(f"- {qs}")
                        
            if schedule_matches:
                output_lines.append("\nIPL Schedule & Today's Games:")
                for sm in schedule_matches:
                    output_lines.append(f"- {sm}")

            return "\n".join(output_lines)
        except Exception as e:
            self.logger.warning(f"Failed to fetch Cricbuzz score: {e}")
            return ""

    def _clean_live_score_text(self, score_str: str) -> str:
        """Parses a Cricbuzz raw live score string into a clean, human-readable sentence."""
        import re
        # Remove non-ascii characters (like replacement character)
        score_str = re.sub(r'[^\x00-\x7F]+', ' ', score_str)
        
        team_names = {
            "RR": "Rajasthan Royals",
            "MI": "Mumbai Indians",
            "KKR": "Kolkata Knight Riders",
            "DC": "Delhi Capitals",
            "LSG": "Lucknow Super Giants",
            "PBKS": "Punjab Kings",
            "CSK": "Chennai Super Kings",
            "RCB": "Royal Challengers Bengaluru",
            "SRH": "Sunrisers Hyderabad",
            "GT": "Gujarat Titans"
        }
        
        # Parse scores for two teams playing
        match = re.search(r'([A-Za-z0-9\s\'\-\&]+?)([A-Z]{2,4})(\d+-\d+|\d+)\s*\((\d+(?:\.\d+)?)\)\s*([A-Za-z0-9\s\'\-\&]+?)([A-Z]{2,4})(\d+-\d+|\d+)\s*\((\d+(?:\.\d+)?)\)\s*(.*)', score_str)
        if match:
            t1, ta1, s1, o1, t2, ta2, s2, o2, status = match.groups()
            t1_name = team_names.get(ta1.upper(), t1.strip())
            t2_name = team_names.get(ta2.upper(), t2.strip())
            return f"In the IPL, {t1_name} scored {s1} in {o1} overs. {t2_name} is at {s2} after {o2} overs. {status.strip()}."
            
        # Check if only one team has batted/is batting
        match2 = re.search(r'([A-Za-z0-9\s\'\-\&]+?)([A-Z]{2,4})(\d+-\d+|\d+)\s*\((\d+(?:\.\d+)?)\)\s*(.*)', score_str)
        if match2:
            t1, ta1, s1, o1, status = match2.groups()
            t1_name = team_names.get(ta1.upper(), t1.strip())
            return f"In the IPL, {t1_name} is at {s1} in {o1} overs. {status.strip()}."
            
        return score_str

    def _execute_single_tool(self, tool_name: str, args: dict) -> str:
        """Executes a single tool using the ExecutionEngine plan wrapper."""
        plan = {
            "action": "EXECUTE",
            "steps": [
                {
                    "tool": tool_name,
                    "args": args
                }
            ]
        }
        res = self.execution_engine.execute_plan(plan)
        if res.get("status") == "SUCCESS" and res.get("results"):
            self._log_tool_usage_to_profile(tool_name, args)
            return res.get("results")[0].get("output", "")
        else:
            return f"Execution failed: {res.get('message')}"

    def _log_tool_usage_to_profile(self, tool: str, args: dict):
        """Track file, app, folder, and contact usage to enrich contextual memory."""
        try:
            if not tool or not args:
                return
                
            # 1. Track file usage
            file_keys = ["file_path", "path", "src", "dest"]
            for k in file_keys:
                if k in args and isinstance(args[k], str):
                    path_val = args[k]
                    if os.path.isfile(path_val) or ("." in os.path.basename(path_val) and not os.path.isdir(path_val)):
                        self.personality.context["last_file"] = path_val
                        recent = self.personality.context.setdefault("recent_files", [])
                        if path_val not in recent:
                            self.personality.context["recent_files"] = (recent + [path_val])[-10:]
                        self.personality.context["last_topic"] = "files"
                        
            # 2. Track project / directory usage
            folder_keys = ["path", "folder_path", "repo_path", "dest", "src"]
            for k in folder_keys:
                if k in args and isinstance(args[k], str):
                    path_val = args[k]
                    if os.path.isdir(path_val):
                        self.personality.context["last_project"] = path_val
                        recent_dirs = self.personality.context.setdefault("recent_projects", [])
                        if path_val not in recent_dirs:
                            self.personality.context["recent_projects"] = (recent_dirs + [path_val])[-10:]
                            
            # 3. Track app usage
            if tool in ["open_app", "close_app"] and "app_name" in args:
                app = args["app_name"]
                self.personality.context["last_app"] = app
                recent_apps = self.personality.context.setdefault("recent_apps", [])
                if app not in recent_apps:
                    self.personality.context["recent_apps"] = (recent_apps + [app])[-10:]
                    
            # 4. Track contact usage
            contact_keys = ["recipient", "to"]
            for k in contact_keys:
                if k in args and isinstance(args[k], str):
                    contact = args[k]
                    self.personality.context["last_person"] = contact
                    recent_people = self.personality.context.setdefault("recent_people", [])
                    if contact not in recent_people:
                        self.personality.context["recent_people"] = (recent_people + [contact])[-10:]
            
            # Save the updated context
            self.personality.save_all()
        except Exception as e:
            self.logger.warning(f"Error logging tool usage to profile: {e}")

    def _resolve_contextual_query(self, query: str) -> str:
        """Resolve contextual words like 'it', 'him', 'yesterday', 'project' to actual paths or items."""
        q = query.lower()
        
        # 1. Resolve "yesterday" / "what I used yesterday" / "it" / "that" for files
        if any(w in q for w in ["yesterday", "last file", "what i used yesterday", "that thing i used", "open it", "read it", "open that", "read that", "that file", "this file"]):
            last_file = self.personality.context.get("last_file")
            if not last_file and self.personality.context.get("recent_files"):
                last_file = self.personality.context.get("recent_files")[-1]
            if last_file:
                self.logger.info(f"Contextual query resolution: replacing yesterday/it reference with last_file: {last_file}")
                if "read" in q or "content" in q:
                    return f"read the file {last_file}"
                else:
                    return f"open the file {last_file}"
                    
        # 2. Resolve "open the project" / "open project"
        if "open the project" in q or "open my project" in q or "open project" in q:
            last_project = self.personality.context.get("last_project")
            if last_project:
                self.logger.info(f"Contextual query resolution: replacing project reference with last_project: {last_project}")
                return f"open the folder {last_project}"
            else:
                workspace = self.config["paths"]["workspace"]
                return f"open the folder {workspace}"

        # 3. Resolve "send it to him" / "message him" / "email him"
        if any(term in q for term in ["to him", "to her", "email him", "email her", "message him", "message her"]):
            recent_people = self.personality.context.get("recent_people", [])
            last_person = self.personality.context.get("last_person")
            person = last_person or (recent_people[-1] if recent_people else None)
            if person:
                self.logger.info(f"Contextual query resolution: replacing him/her reference with person: {person}")
                q_resolved = query
                for term in ["to him", "to her", "him", "her"]:
                    if term in q_resolved.lower():
                        idx = q_resolved.lower().find(term)
                        q_resolved = q_resolved[:idx] + f"to {person}" + q_resolved[idx+len(term):]
                        break
                return q_resolved

        return query


    def _get_programmatic_ipl_response(self, query: str) -> str:
        """Fetch Cricbuzz live scores/schedule and construct a programmatic response."""
        import urllib.request
        from bs4 import BeautifulSoup
        import re
        import datetime

        try:
            url = "https://www.cricbuzz.com/cricket-match/live-scores"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()
            clean_text = re.sub(r'\s+', ' ', text)
            
            # 1. Parse live match scorecards
            live_scores = []
            pattern = r'(Indian Premier League \d{4}|Indian Premier League|IPL \d{4})[^|]*?(?=Live Score|Scorecard|Full Commentary|Preview|Match Centre)'
            for m in re.finditer(pattern, clean_text):
                match_str = m.group(0).strip()
                if len(match_str) > 400:
                    continue
                match_str = "".join(c for c in match_str if c.isprintable())
                match_str = re.sub(r'\s+', ' ', match_str)
                if match_str not in live_scores:
                    live_scores.append(match_str)
            
            # 2. Parse schedule matches
            schedule_matches = []
            ipl_block_match = re.search(r'LEAGUE\s*IPL[^\w]*(.*?)(?=T20 Blast|DOMESTIC|WOMEN|INTERNATIONAL|$)', clean_text, re.IGNORECASE)
            if ipl_block_match:
                block_text = ipl_block_match.group(1)
                pattern_sched = r'([A-Za-z0-9\s\'\-\&]+? vs [A-Za-z0-9\s\'\-\&]+?(?:LIVE)?\s*\d+(?:st|nd|rd|th)\s*Match)'
                sched_matches = re.findall(pattern_sched, block_text)
                for sm in sched_matches:
                    sm_clean = re.sub(r'\s+', ' ', "".join(c for c in sm if c.isprintable())).strip()
                    sm_clean = re.sub(r'^\d+', '', sm_clean).strip()  # Remove leading year digits
                    sm_clean = sm_clean.replace("LIVE", " (LIVE) ")
                    schedule_matches.append(sm_clean)

            # Build response based on user intent
            q_lower = query.lower()
            is_schedule_query = any(w in q_lower for w in ["schedule", "match today", "matches today", "playing today", "who plays today", "fixtures"])
            is_score_query = any(w in q_lower for w in ["score", "live", "who is winning", "status", "result"])
            
            if is_score_query or not is_schedule_query:
                if live_scores:
                    formatted_scores = []
                    for ls in live_scores:
                        formatted_scores.append(self._clean_live_score_text(ls))
                    return " ".join(formatted_scores)
                else:
                    quick_statuses = []
                    matches_header = re.search(r'MATCHES(.*?)(?=ALL|All|Live Now|Today)', clean_text, re.IGNORECASE)
                    if matches_header:
                        header_text = matches_header.group(1)
                        pattern_qs = r'([A-Z]{2,4}\s+vs\s+[A-Z]{2,4}\s*-\s*.*?)(?=[A-Z]{2,4}\s+vs|$)'
                        matches_found = re.findall(pattern_qs, header_text)
                        for m in matches_found:
                            m_clean = re.sub(r'\s+', ' ', "".join(c for c in m if c.isprintable())).strip()
                            quick_statuses.append(m_clean)
                    ipl_quick = [qs for qs in quick_statuses if any(team in qs for team in ["RR", "MI", "KKR", "DC", "LSG", "PBKS", "CSK", "RCB", "SRH", "GT"])]
                    if ipl_quick:
                        return "Here are the current IPL scores: " + " and ".join(ipl_quick) + "."
                    
                    # If no live matches, fallback to schedule
                    if schedule_matches:
                        matches_desc = []
                        for sm in schedule_matches:
                            sm_clean = re.sub(r'(\d+)(st|nd|rd|th)\s*Match', r'the \1\2 match', sm, flags=re.IGNORECASE)
                            matches_desc.append(sm_clean)
                        if len(matches_desc) == 1:
                            return f"There are no live IPL matches right now. Today's scheduled match is {matches_desc[0]}."
                        elif len(matches_desc) == 2:
                            return f"There are no live IPL matches right now. Today's scheduled matches are {matches_desc[0]} and {matches_desc[1]}."
                        else:
                            return f"There are no live IPL matches right now. Today's scheduled matches are: " + ", ".join(matches_desc[:-1]) + f", and {matches_desc[-1]}."
                            
                    return "There are no live IPL matches currently playing and no scheduled matches found."
            else:
                if schedule_matches:
                    matches_desc = []
                    for sm in schedule_matches:
                        sm_clean = re.sub(r'(\d+)(st|nd|rd|th)\s*Match', r'the \1\2 match', sm, flags=re.IGNORECASE)
                        matches_desc.append(sm_clean)
                    
                    if len(matches_desc) == 1:
                        return f"Today's IPL match is {matches_desc[0]}."
                    elif len(matches_desc) == 2:
                        return f"Today's IPL matches are {matches_desc[0]} and {matches_desc[1]}."
                    else:
                        return f"Today's IPL matches are: " + ", ".join(matches_desc[:-1]) + f", and {matches_desc[-1]}."
                else:
                    if live_scores:
                        formatted_scores = []
                        for ls in live_scores:
                            formatted_scores.append(self._clean_live_score_text(ls))
                        return "I couldn't find a schedule, but here is the live match status: " + " ".join(formatted_scores)
                    return "I couldn't find any scheduled IPL matches for today."
                    
        except Exception as e:
            self.logger.warning(f"Error fetching/parsing Cricbuzz data: {e}")
            return "I'm sorry, I encountered an error while trying to fetch the IPL scores."

    def _build_prompt(self, user_text: str, analysis: dict = None) -> str:
        """Build a context-aware prompt using memory facts and conversation history."""
        import datetime
        facts = self.long_term.get_permanent_facts()
        name  = self._get_name()
        
        fact_list = []
        if facts:
            fact_list.extend(facts[:5])
        
        # Inject correct system folder paths so Jarvis never lies about folder locations
        fact_list.append(f"Workspace path is: {self.config['paths']['workspace']}")
        fact_list.append(f"Logs path is: {self.config['paths']['logs']}")
        fact_list.append(f"Memory path is: {self.config['paths']['memory']}")
        
        # Inject current date and time
        date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
        fact_list.append(f"Today's date is: {date_str}.")

        # Check user query against scanned folders or search them dynamically
        matched_folders = []
        t_lower = user_text.lower()
        if any(w in t_lower for w in ["where is", "find", "locate", "path of"]) and any(w in t_lower for w in ["folder", "directory", "file", "path"]):
            target_name = self._extract_target_name(user_text)
            if target_name:
                # 1. Look in cached _sys_folders using word-based matching
                target_words = [w for w in target_name.split() if len(w) > 2]
                for folder_name, folder_path in self._sys_folders.items():
                    if target_name in folder_name or folder_name in target_name or (target_words and any(w in folder_name for w in target_words)):
                        matched_folders.append((folder_name, folder_path))
                
                # 2. If nothing found in cache, walk the system drives dynamically
                if not matched_folders:
                    self.logger.info(f"Folder '{target_name}' not in cache. Scanning drives dynamically...")
                    scanned_matches = self._locate_on_system(target_name)
                    for path in scanned_matches:
                        basename = os.path.basename(path).lower()
                        self._sys_folders[basename] = path
                        matched_folders.append((basename, path))
        
        # Inject matched folder locations into facts
        for fname, fpath in matched_folders:
            drive, _ = os.path.splitdrive(fpath)
            drive_letter = drive.replace(":", "").upper() if drive else ""
            
            is_outside = True
            try:
                wp = os.path.abspath(self.config['paths']['workspace'])
                fp = os.path.abspath(fpath)
                if fp.startswith(wp):
                    is_outside = False
            except Exception:
                pass
            
            location_desc = f"at path: {fpath}"
            if drive_letter:
                location_desc = f"on the {drive_letter} drive, at path: {fpath}"
            
            outside_desc = f". It is completely outside of the Jarvis workspace" if is_outside else ""
            fact_list.append(f"The '{fname}' folder/file is located {location_desc}{outside_desc}.")

        if self.last_located_path:
            fact_list.append(f"The most recently located path is: {self.last_located_path}.")

        # Extract mood and style params
        mood = "calm"
        max_sent = 2
        tone = "helpful"
        mood_instruction = "Respond naturally."
        
        if analysis:
            mood = analysis.get("mood", "calm")
            style = analysis.get("response_style", {})
            max_sent = style.get("max_sentences", 2)
            tone = style.get("tone", "helpful")
            
            mood_instruction = {
                "stressed":   "The user seems stressed. Be very brief and calm.",
                "frustrated": "The user seems frustrated. Apologize if needed, be direct.",
                "excited":    "The user is excited. Match their energy.",
                "curious":    "The user is curious. Provide a helpful explanation.",
                "tired":      "The user seems tired. Keep it very short and gentle.",
                "focused":    "The user is focused. Give a concise direct answer.",
                "calm":       "Respond naturally.",
            }.get(mood, "Respond naturally.")

        ctx_summary = self.personality.get_context_summary()
        if ctx_summary:
            fact_list.append(f"Contextual state: {ctx_summary}")

        skill_level = self.personality.get_skill_level("coding")
        fact_list.append(f"User coding skill level is: {skill_level}. Adapt explanation complexity accordingly.")

        fact_str = "\n\nSystem info & known facts:\n" + "\n".join(f"- {f}" for f in fact_list)

        # Retrieve recent conversation history
        recent = self.short_term.get_context_messages()[-6:]
        history_str = ""
        if recent:
            history_str = "\n\nRecent conversation history:\n" + "\n".join(
                f"{'User' if msg['role'] == 'user' else 'Jarvis'}: {msg['content']}"
                for msg in recent
            )

        return (
            f"You are Jarvis, an intelligent, friendly and conversational AI assistant. "
            f"Address the user as {name}. "
            f"{mood_instruction} "
            f"Answer concisely in {max_sent} spoken sentences, no markdown, no bullet points. "
            f"Be conversational, warm, and speak like a natural human companion. "
            f"Tone: {tone}.\n"
            f"If the user is asking about system locations or folder paths, rely ONLY on the facts listed below. Do not guess, assume, or hallucinate any drive letters, folders, or paths not explicitly listed. If the facts say a folder is on the D drive, say it is on the D drive."
            f"{fact_str}"
            f"{history_str}"
            f"\n\nUser: {user_text}\nJarvis:"
        )

    def _extract_and_remember(self, user_text: str, jarvis_response: str):
        """Save memorable facts from the conversation."""
        t = user_text.lower()
        # Explicit remember commands
        if any(kw in t for kw in
               ["remember that", "don't forget", "keep in mind",
                "note that", "save this", "memorize"]):
            clean_fact = user_text
            for prefix in ["remember that", "don't forget", "keep in mind", "note that", "save this", "memorize"]:
                if t.startswith(prefix):
                    clean_fact = user_text[len(prefix):].strip()
                    break
            self.long_term.remember_fact(clean_fact, permanent=False)
            self.logger.info(f"Learned explicit fact: {clean_fact}")

        # Name updates
        import re as _re
        m = _re.search(r"(?:call me|my name is)\s+(\w+)", t)
        if m:
            new_name = m.group(1).capitalize()
            self.long_term.add_nickname(new_name)
            self.long_term.remember_fact(
                f"User also goes by '{new_name}'.", permanent=True)
            self.logger.info(f"Learned nickname: {new_name}")

        # Automatic Fact Extraction in background thread
        def auto_extract():
            try:
                prompt = (
                    "You are Jarvis's memory extraction module. Analyze this user input and extract any permanent personal facts, "
                    "preferences, habits, or details about the user (e.g. name, location, profession, likes, dislikes) that Jarvis should remember.\n\n"
                    f"User Input: \"{user_text}\"\n\n"
                    "If a fact is found, output only the clean fact (e.g. 'User lives in Karnataka', 'User likes cricket'). "
                    "If no new personal fact or preference is found, reply with 'NONE'. Do not include any other text."
                )
                extracted = self.model_manager.generate(model_key="intent", prompt=prompt, options={"temperature": 0.0}).strip()
                if extracted and extracted.upper() != "NONE" and len(extracted) < 100:
                    existing = self.long_term.get_permanent_facts()
                    if not any(extracted.lower() in f.lower() or f.lower() in extracted.lower() for f in existing):
                        self.long_term.remember_fact(extracted, permanent=True)
                        self.logger.info(f"Automatically learned fact: {extracted}")
            except Exception as e:
                self.logger.warning(f"Auto-extraction of memory failed: {e}")

        import threading
        threading.Thread(target=auto_extract, daemon=True).start()


    def terminal_interactive_shell(self):
        """
        Sleek CLI interactive prompt shell.
        """
        name = self._get_name()
        prediction = self.personality.predict_next_action()
        
        print("\n" + "="*50)
        print(" Jarvis Operating Assistant CLI Shell")
        print(" Type 'exit' to quit. Type 'voice' to trigger Vosk loop.")
        print("="*50 + "\n")

        if prediction:
            print(f"* Suggestion: Based on your habits, would you like me to '{prediction}'?")
            print("   (Just press Enter or say yes to execute, or type a command)\n")

        self.voice_out.speak(f"Jarvis CLI shell active. Hello {name}!")

        while True:
            try:
                user_input = input("Jarvis> ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit"]:
                    self.voice_out.speak("Shutting down Jarvis. Goodbye.")
                    break
                if user_input.lower() == "voice":
                    self.voice_interaction_loop()
                    break

                # Reset sleep timer on any user interaction
                self.overlay.reset_sleep_timer()
                self.overlay.set_state("thinking")
                self.overlay.show_live_text(user_input)

                response = self.run_command_flow(user_input)
                self.voice_out.speak(response, block=False)
            except KeyboardInterrupt:
                print("\nType 'exit' to exit.")
            except Exception as e:
                self.logger.error(f"Error processing command: {e}")
                print(f"Error: {e}")

        # Graceful teardown
        self._graceful_shutdown()

    def get_themed_text_input(self, title: str, prompt: str, is_password: bool = False) -> str:
        """Opens a themed, Windows-topmost input dialog to safely capture text input."""
        import tkinter as tk
        result = None

        def on_ok(event=None):
            nonlocal result
            result = entry.get()
            root.destroy()

        def on_cancel(event=None):
            root.destroy()

        try:
            root = tk.Tk()
            root.title(title)
            root.geometry("380x160")
            root.attributes("-topmost", True)
            root.configure(bg="#060a14")
            root.resizable(False, False)

            # Center on screen
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = (sw - 380) // 2
            y = (sh - 160) // 2
            root.geometry(f"380x160+{x}+{y}")

            lbl = tk.Label(root, text=prompt, font=("Segoe UI", 10), fg="#c8e8ff", bg="#060a14", wraplength=340)
            lbl.pack(pady=(15, 10))

            entry = tk.Entry(root, font=("Segoe UI", 10), width=32, bg="#0b1221", fg="#c8e8ff", insertbackground="#00d4ff",
                             highlightthickness=1, highlightbackground="#1c3a5e", highlightcolor="#00d4ff", bd=0,
                             show="*" if is_password else "")
            entry.pack(pady=5)
            entry.focus_set()

            btn_frame = tk.Frame(root, bg="#060a14")
            btn_frame.pack(pady=(15, 10))

            btn_ok = tk.Button(btn_frame, text="OK", width=12, command=on_ok, bg="#1c3a5e", fg="#c8e8ff", relief="flat", font=("Segoe UI", 9, "bold"))
            btn_ok.pack(side="left", padx=10)

            btn_cancel = tk.Button(btn_frame, text="Cancel", width=12, command=on_cancel, bg="#0f1a2e", fg="#c8e8ff", relief="flat", font=("Segoe UI", 9, "bold"))
            btn_cancel.pack(side="right", padx=10)

            root.bind("<Return>", on_ok)
            root.bind("<Escape>", on_cancel)

            root.mainloop()
        except Exception as e:
            self.logger.warning(f"Failed to open text input popup: {e}")
            import getpass
            if is_password:
                result = getpass.getpass(f"{prompt}: ")
            else:
                result = input(f"{prompt}: ")

        return result if result is not None else ""

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="Jarvis AI Operating Assistant System")
    parser.add_argument(
        "--voice", action="store_true",
        help="Start Jarvis directly in voice wake-word mode")
    parser.add_argument(
        "--startup", action="store_true",
        help="Silent startup mode (from auto-login): show HUD + speak greeting")
    parser.add_argument(
        "--cli", action="store_true",
        help="Start Jarvis in terminal CLI shell mode")
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config.yaml file")
    parser.add_argument(
        "--register-startup", dest="register", action="store_true",
        help="Register Jarvis as a Windows auto-startup application")
    parser.add_argument(
        "--unregister-startup", dest="unregister", action="store_true",
        help="Remove Jarvis from Windows auto-startup")
    args = parser.parse_args()

    # ── Startup registration helpers (no Jarvis init needed) ──
    if args.register or args.unregister:
        import subprocess
        flag = "--unregister" if args.unregister else ""
        subprocess.run([sys.executable, "register_startup.py", flag],
                       check=False)
        return

    try:
        jarvis = JarvisSystem(args.config)
        if args.cli:
            jarvis.terminal_interactive_shell()
        else:
            # Default to voice loop
            jarvis.voice_interaction_loop(startup_greeting=args.startup)
    except Exception as e:
        logging.getLogger("Jarvis").critical(
            f"Fatal error launching Jarvis: {e}", exc_info=True)
        print(f"Fatal error: {e}")


if __name__ == "__main__":
    main()
