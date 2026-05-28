import os
import logging
import pyautogui
from PIL import Image
from typing import List, Dict, Any

class ScreenOCR:
    def __init__(self):
        self.logger = logging.getLogger("Jarvis.OCR")
        self.reader = None

    def _init_reader(self):
        if self.reader is not None:
            return
        import sys
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except Exception:
                pass
        try:
            import easyocr
            self.logger.info("Initializing EasyOCR reader (English)...")
            # EasyOCR automatically detects if CUDA is available and uses it
            self.reader = easyocr.Reader(['en'], gpu=True)
            self.logger.info("EasyOCR initialized.")
        except Exception as e:
            self.logger.error(f"Failed to initialize EasyOCR: {e}")

    def capture_and_read(self) -> List[Dict[str, Any]]:
        """
        Captures the screen and extracts text elements with bounding boxes.
        Returns a list of dicts:
        {
          "text": str,
          "box": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],
          "center": (x, y)
        }
        """
        self._init_reader()
        if not self.reader:
            self.logger.error("EasyOCR reader is not available.")
            return []

        try:
            # Capture screenshot
            self.logger.info("Capturing screen screenshot...")
            screenshot = pyautogui.screenshot()
            
            # Save to temporary path
            temp_img_path = "temp_screen.png"
            screenshot.save(temp_img_path)
            
            # Run OCR
            self.logger.info("Extracting text from screenshot via EasyOCR...")
            results = self.reader.readtext(temp_img_path)
            
            # Clean up temp file
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

            extracted_items = []
            for bbox, text, confidence in results:
                # bbox contains 4 corners: [top_left, top_right, bottom_right, bottom_left]
                # Each corner is [x, y]
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                cx = int(sum(xs) / 4)
                cy = int(sum(ys) / 4)
                
                extracted_items.append({
                    "text": text,
                    "box": bbox,
                    "center": (cx, cy),
                    "confidence": float(confidence)
                })

            self.logger.info(f"Successfully extracted {len(extracted_items)} text boxes from screen.")
            return extracted_items

        except Exception as e:
            self.logger.error(f"Screen OCR extraction failed: {e}")
            return []

    def find_text_coordinates(self, target_text: str) -> List[Dict[str, Any]]:
        """
        Finds occurrences of target_text in the screen.
        """
        items = self.capture_and_read()
        matches = []
        target_lower = target_text.lower()
        
        for item in items:
            if target_lower in item["text"].lower():
                matches.append(item)
                
        return matches
