import os
import logging
import pyautogui
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from typing import Dict, Any, List

class ScreenDetector:
    def __init__(self, config: dict):
        self.config = config
        self.model_id = config["vision"].get("florence_model", "microsoft/Florence-2-base")
        self.use_gpu = config["vision"].get("use_gpu", True)
        self.logger = logging.getLogger("Jarvis.ScreenDetect")
        
        self.processor = None
        self.model = None
        self.device = "cuda" if (self.use_gpu and torch.cuda.is_available()) else "cpu"

    def _init_model(self):
        if self.model is not None:
            return
            
        try:
            self.logger.info(f"Loading Florence-2 model '{self.model_id}' on {self.device}...")
            # Load processor
            self.processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
            
            # Load model in float16 if on CUDA
            if self.device == "cuda":
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, 
                    trust_remote_code=True,
                    torch_dtype=torch.float16,
                    attn_implementation="eager"
                ).to(self.device)
            else:
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, 
                    trust_remote_code=True,
                    attn_implementation="eager"
                ).to(self.device)
                
            self.logger.info("Florence-2 model loaded successfully.")
        except Exception as e:
            self.logger.error(f"Failed to load Florence-2 model: {e}")

    def run_task(self, image_path: str, task_prompt: str, text_input: str = None) -> str:
        """
        Executes a Florence-2 task on the target image.
        """
        self._init_model()
        if not self.model or not self.processor:
            return "Model not initialized."

        try:
            image = Image.open(image_path).convert("RGB")
            
            # Construct task prompt format
            if text_input:
                prompt = task_prompt + text_input
            else:
                prompt = task_prompt
                
            inputs = self.processor(text=prompt, images=image, return_tensors="pt")
            
            if self.device == "cuda":
                inputs = {k: v.to(self.device).half() if v.dtype == torch.float32 else v.to(self.device) for k, v in inputs.items()}
            else:
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                generated_ids = self.model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=1024,
                    early_stopping=False,
                    do_sample=False,
                    num_beams=3,
                )
                
            # Process result
            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            parsed_answer = self.processor.post_process_generation(
                generated_text, 
                task=task_prompt, 
                image_size=(image.width, image.height)
            )
            return parsed_answer
        except Exception as e:
            self.logger.error(f"Error during Florence-2 execution: {e}")
            return {}

    def describe_screen(self) -> str:
        """Captures screen and returns natural language description."""
        screenshot = pyautogui.screenshot()
        temp_path = "temp_detect.png"
        screenshot.save(temp_path)
        
        result = self.run_task(temp_path, "<DETAILED_CAPTION>")
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if isinstance(result, str):
            return result
            
        # The result is a dictionary: {'<DETAILED_CAPTION>': 'description text'}
        return result.get("<DETAILED_CAPTION>", "No description available.")

    def find_element_on_screen(self, query: str) -> List[Dict[str, Any]]:
        """
        Visual Grounding: Finds coordinates for a query (e.g. 'the start menu icon').
        """
        screenshot = pyautogui.screenshot()
        temp_path = "temp_detect.png"
        screenshot.save(temp_path)
        
        # '<CAPTION_TO_PHRASE_GROUNDING>' resolves text queries to boxes
        result = self.run_task(temp_path, "<CAPTION_TO_PHRASE_GROUNDING>", text_input=query)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if isinstance(result, str):
            return []

        # Output format is: {'<CAPTION_TO_PHRASE_GROUNDING>': {'bboxes': [[x1, y1, x2, y2], ...], 'labels': [...]}}
        grounding = result.get("<CAPTION_TO_PHRASE_GROUNDING>", {})
        bboxes = grounding.get("bboxes", [])
        
        centers = []
        for box in bboxes:
            x1, y1, x2, y2 = box
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            centers.append({
                "bbox": [x1, y1, x2, y2],
                "center": (cx, cy)
            })
            
        return centers
