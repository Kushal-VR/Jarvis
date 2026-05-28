import logging
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

class PlaywrightBrowserManager:
    def __init__(self, config: dict):
        self.config = config
        self.headless = config["web"].get("headless", True)
        self.user_agent = config["web"].get("user_agent", "")
        self.logger = logging.getLogger("Jarvis.Browser")
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.current_page = None

    def start(self):
        """Launches the Playwright chromium browser context."""
        if self.playwright is not None:
            return
            
        try:
            self.logger.info("Starting Playwright browser...")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=self.headless)
            
            # Create context with User Agent for scrape bypass
            extra_headers = {"User-Agent": self.user_agent} if self.user_agent else {}
            self.context = self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=self.user_agent
            )
            self.current_page = self.context.new_page()
            self.logger.info("Browser launched successfully.")
        except Exception as e:
            self.logger.error(f"Failed to start Playwright browser: {e}")
            self.close()
            raise

    def get_page(self) -> Page:
        if self.current_page is None:
            self.start()
        return self.current_page

    def navigate(self, url: str):
        """Navigates current page to url."""
        page = self.get_page()
        self.logger.info(f"Navigating to {url}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            self.logger.info(f"Page loaded: {page.title()}")
        except Exception as e:
            self.logger.error(f"Navigation to {url} failed: {e}")
            raise

    def click_element(self, selector: str):
        """Clicks an element by CSS selector."""
        page = self.get_page()
        self.logger.info(f"Clicking element with selector: '{selector}'")
        try:
            page.click(selector, timeout=5000)
        except Exception as e:
            self.logger.error(f"Click element '{selector}' failed: {e}")
            raise

    def fill_form(self, selector: str, text: str):
        """Fills a form field with text."""
        page = self.get_page()
        self.logger.info(f"Filling selector '{selector}' with text.")
        try:
            page.fill(selector, text, timeout=5000)
        except Exception as e:
            self.logger.error(f"Failed to fill selector '{selector}': {e}")
            raise

    def close(self):
        """Closes context and browser."""
        self.logger.info("Closing Playwright browser...")
        try:
            if self.current_page:
                self.current_page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            self.logger.warning(f"Error during browser teardown: {e}")
        finally:
            self.current_page = None
            self.context = None
            self.browser = None
            self.playwright = None
