import logging
import time
import os
from jarvis.web.browser import PlaywrightBrowserManager

class WhatsAppWebAutomator:
    def __init__(self, browser_manager: PlaywrightBrowserManager, workspace_path: str):
        self.browser = browser_manager
        self.workspace_path = workspace_path
        self.logger = logging.getLogger("Jarvis.WhatsApp")

    def _ensure_authenticated(self) -> bool:
        """
        Navigates to WhatsApp Web and checks login status.
        If QR code is present, captures screenshot to let user scan.
        """
        page = self.browser.get_page()
        if not page.url.startswith("https://web.whatsapp.com"):
            self.browser.navigate("https://web.whatsapp.com")
            # Wait for either the chat list or the QR code
            time.sleep(5.0)

        # Selector for chat list search box (means logged in)
        search_selector = "div[contenteditable='true'][data-tab='3']"
        # Selector for QR code canvas (means needs login)
        qr_selector = "canvas"

        try:
            # Check login
            if page.locator(search_selector).is_visible():
                self.logger.info("WhatsApp Web is authenticated.")
                return True
                
            if page.locator(qr_selector).is_visible():
                self.logger.warning("WhatsApp Web requires authentication. Capturing QR code...")
                qr_path = os.path.join(self.workspace_path, "whatsapp_qr.png")
                # Screenshot the QR code area
                page.locator(qr_selector).screenshot(path=qr_path)
                self.logger.warning(f"Please scan the WhatsApp QR code located at: {qr_path}")
                
                # Check for login periodically up to 60 seconds
                for i in range(12):
                    self.logger.info(f"Waiting for scan... ({i*5}s / 60s)")
                    time.sleep(5.0)
                    if page.locator(search_selector).is_visible():
                        self.logger.info("Scan successful! WhatsApp Web authenticated.")
                        if os.path.exists(qr_path):
                            os.remove(qr_path)
                        return True
                        
            return False
        except Exception as e:
            self.logger.error(f"WhatsApp authentication check failed: {e}")
            return False

    def send_whatsapp_message(self, recipient_name: str, message: str) -> bool:
        """
        Automates WhatsApp Web to send a message.
        """
        self.logger.info(f"Attempting to send WhatsApp message to '{recipient_name}'...")
        try:
            self.browser.start()
            if not self._ensure_authenticated():
                self.logger.error("WhatsApp Web authentication failed or timed out.")
                return False

            page = self.browser.get_page()
            
            # Selector for contact search box
            search_selector = "div[contenteditable='true'][data-tab='3']"
            page.click(search_selector)
            # Clear search box and type recipient name
            page.fill(search_selector, "")
            page.type(search_selector, recipient_name)
            time.sleep(2.0)
            
            # Press enter to open chat
            page.press(search_selector, "Enter")
            time.sleep(2.0)
            
            # Selector for chat message entry field
            message_box_selector = "footer div[contenteditable='true'][data-tab='10']"
            if not page.locator(message_box_selector).is_visible():
                self.logger.error(f"Could not open chat with recipient: '{recipient_name}'")
                return False
                
            page.click(message_box_selector)
            page.type(message_box_selector, message)
            time.sleep(1.0)
            
            # Press enter to send
            page.press(message_box_selector, "Enter")
            time.sleep(1.0)
            
            self.logger.info(f"WhatsApp message sent successfully to '{recipient_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send WhatsApp message: {e}")
            return False
