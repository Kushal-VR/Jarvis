import time
import logging
import pyautogui

# Set safety settings for PyAutoGUI
pyautogui.FAILSAFE = True  # Move mouse to upper-left corner to abort execution
pyautogui.PAUSE = 0.3      # Add micro-delays between actions to keep UI responsive

class ScreenController:
    def __init__(self):
        self.logger = logging.getLogger("Jarvis.ScreenControl")

    def click(self, x: int, y: int, clicks: int = 1, button: str = 'left'):
        """Clicks at specific screen coordinate."""
        try:
            self.logger.info(f"Clicking at ({x}, {y}) clicks={clicks} button={button}")
            pyautogui.moveTo(x, y, duration=0.2)
            pyautogui.click(x, y, clicks=clicks, button=button)
        except Exception as e:
            self.logger.error(f"Failed to click at ({x}, {y}): {e}")
            raise

    def type_text(self, text: str, delay: float = 0.05):
        """Types text with a small delay between keystrokes."""
        try:
            self.logger.info(f"Typing text: '{text}'")
            pyautogui.write(text, interval=delay)
        except Exception as e:
            self.logger.error(f"Failed to type text: {e}")
            raise

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5):
        """Drags mouse from start coordinates to end coordinates."""
        try:
            self.logger.info(f"Dragging from ({start_x}, {start_y}) to ({end_x}, {end_y})")
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
        except Exception as e:
            self.logger.error(f"Failed to drag: {e}")
            raise

    def scroll(self, clicks: int):
        """Scrolls up (positive) or down (negative)."""
        try:
            self.logger.info(f"Scrolling by {clicks} clicks")
            pyautogui.scroll(clicks)
        except Exception as e:
            self.logger.error(f"Failed to scroll: {e}")
            raise

    def press_shortcut(self, key_combination: str):
        """Presses a single key or shortcut (e.g. 'ctrl', 'c' or 'alt+tab')."""
        try:
            self.logger.info(f"Pressing shortcut: {key_combination}")
            keys = [k.strip().lower() for k in key_combination.split('+')]
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
        except Exception as e:
            self.logger.error(f"Failed to press key combination: {key_combination}. Error: {e}")
            raise
