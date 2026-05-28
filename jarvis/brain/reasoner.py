import logging
import re
from .model_manager import OllamaModelManager

class DeepReasoner:
    def __init__(self, model_manager: OllamaModelManager):
        self.model_manager = model_manager
        self.logger = logging.getLogger("Jarvis.Reasoner")

    def think(self, user_prompt: str, system_prompt: str = None) -> str:
        """
        Queries deepseek-r1:7b for complex problem solving, explanation, or teaching.
        Parses and log/prints the thought process separately from the final response.
        """
        if system_prompt is None:
            system_prompt = (
                "You are Jarvis, a friendly, intelligent thinking assistant. Provide comprehensive, "
                "clear, and step-by-step explanations in a warm and conversational tone, as a human companion would. "
                "You possess deep software engineering, math, and reasoning capabilities."
            )

        self.logger.info("Executing deep reasoning query (deepseek-r1:7b)...")
        
        # Call generate or chat. Note that deepseek-r1 outputs thinking steps inside <thought> tags
        response_str = self.model_manager.generate(
            model_key="reasoning",
            prompt=user_prompt,
            system_prompt=system_prompt
        )

        # Parse <thought> blocks
        thought_match = re.search(r'<thought>(.*?)</thought>', response_str, re.DOTALL | re.IGNORECASE)
        
        if thought_match:
            thought_process = thought_match.group(1).strip()
            # Log the internal thinking process
            self.logger.info("DeepSeek Thinking Process:\n" + "="*40 + f"\n{thought_process}\n" + "="*40)
            
            # Clean up the output to exclude the thought tags for standard presentation
            clean_response = re.sub(r'<thought>.*?</thought>', '', response_str, flags=re.DOTALL | re.IGNORECASE).strip()
            return clean_response
        else:
            return response_str
