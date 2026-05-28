import json
import logging
from typing import Dict, Any
from .model_manager import OllamaModelManager

class NaturalLanguageUnderstander:
    def __init__(self, model_manager: OllamaModelManager):
        self.model_manager = model_manager
        self.logger = logging.getLogger("Jarvis.NLU")

    def analyze(self, user_prompt: str) -> Dict[str, Any]:
        """
        Classifies the user prompt and extracts intent and entities.
        Uses llama3.2:1b with a strict classification schema.
        """
        system_prompt = (
            "You are the NLU intent classifier module of Jarvis. You must categorize user requests into one of:\n"
            "1. COMMAND: The request requires a system operation (e.g., open app, create file, run script, git commit, browser scrape).\n"
            "2. DIRECT: The request is a simple informational question requiring a fast answer without system tools (e.g., 'What is the capital of France?').\n"
            "3. THINKING: The request requires planning, reasoning, explanation, teaching, or complex software development (e.g., 'Teach me Python', 'Debug this complex code').\n"
            "\n"
            "Format your response as a strict JSON object with this exact structure:\n"
            "{\n"
            "  \"classification\": \"COMMAND\" | \"DIRECT\" | \"THINKING\",\n"
            "  \"intent\": \"string description of intent\",\n"
            "  \"entities\": {\"app\": \"name\", \"file\": \"path\", \"recipient\": \"name\", \"query\": \"search term\"},\n"
            "  \"reason\": \"brief reason for classification\"\n"
            "}\n"
            "Do not include any pre-text, conversational filler, or post-text. Return only valid JSON."
        )

        prompt = f"User Request: \"{user_prompt}\""
        
        self.logger.info("Sending prompt to NLU classifier (llama3.2:1b)...")
        response_str = self.model_manager.generate(
            model_key="intent",
            prompt=prompt,
            system_prompt=system_prompt,
            options={"temperature": 0.0}, # Zero temperature for deterministic classification
            format_json=True
        )

        try:
            # Strip markdown code blocks if any
            clean_res = response_str.strip()
            if clean_res.startswith("```"):
                clean_res = clean_res.split("```")[1]
                if clean_res.startswith("json"):
                    clean_res = clean_res[4:]
            clean_res = clean_res.strip()
            
            result = json.loads(clean_res)
            
            # Heuristic self-healing corrections for small models (llama3.2:1b)
            text = user_prompt.lower().strip()
            
            # Screen automation commands (reading, describing, clicking the screen)
            screen_indicators = [
                "what is on my screen", "what is on the screen", "explain my screen", 
                "explain what is on my screen", "describe my screen", "read my screen", 
                "describe the screen", "read screen", "what's on screen", "what is visible", 
                "screen ocr", "find on screen", "click on screen", "explain what is in my screen",
                "what is on my screen right now", "explain what is in my screen", "explain the screen",
                "what's on my screen right now"
            ]
            
            # Verbs that indicate a system action/command
            command_verbs = [
                "open", "launch", "run", "create", "delete", "send", "message", "write", 
                "git", "commit", "push", "pull", "type", "click", "play", "search", 
                "google", "scrape", "find", "locate", "npm", "pip", "install", "fork", "scan"
            ]

            # Verbs/Phrases that indicate a thinking/reasoning query
            thinking_triggers = [
                "explain", "teach", "how does", "how to", "why did", "debug", "refactor", 
                "write a code", "write code", "how do i", "explain this"
            ]

            is_screen_query = any(ind in text for ind in screen_indicators)
            has_command_verb = any(v in text.split() or text.startswith(v) for v in command_verbs)
            has_thinking_trigger = any(t in text for t in thinking_triggers)

            if is_screen_query:
                result["classification"] = "COMMAND"
                result["intent"] = "screen_automation"
                self.logger.info("Heuristic self-healing: forced screen command to COMMAND classification.")
                classification = "COMMAND"
            elif has_thinking_trigger:
                result["classification"] = "THINKING"
                classification = "THINKING"
                self.logger.info("Heuristic self-healing: forced query to THINKING classification.")
            elif has_command_verb and result.get("classification", "DIRECT") == "DIRECT":
                result["classification"] = "COMMAND"
                classification = "COMMAND"
                self.logger.info("Heuristic self-healing: forced command-verb query to COMMAND classification.")
            else:
                classification = result.get("classification", "DIRECT")
                
            if classification == "COMMAND":
                question_triggers = ["what is", "who is", "where is", "when was", "how many", "tell me a", "give me a fact", "what are", "why is", "how do"]
                is_question = any(text.startswith(t) or text.endswith("?") for t in question_triggers)
                has_verb = any(v in text for v in command_verbs)
                
                if is_question and not has_verb and not is_screen_query:
                    result["classification"] = "DIRECT"
                    self.logger.info("Heuristic self-healing: corrected misclassification from COMMAND to DIRECT.")
                    classification = "DIRECT"
                    
                if classification == "COMMAND":
                    if has_thinking_trigger and not is_screen_query:
                        result["classification"] = "THINKING"
                        self.logger.info("Heuristic self-healing: corrected misclassification from COMMAND to THINKING.")
            
            self.logger.info(f"NLU Classification: {result.get('classification')} (Intent: {result.get('intent')})")
            return result
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse NLU response as JSON: {response_str}. Exception: {e}")
            # Robust fallback logic based on keyword matching if LLM fails formatting
            return self._fallback_parse(user_prompt)

    def _fallback_parse(self, prompt: str) -> Dict[str, Any]:
        """
        Regex-based / heuristic NLU fallback if LLM json output is malformed.
        """
        text = prompt.lower()
        if any(w in text for w in ["open", "run", "launch", "create", "delete", "send", "message", "write", "git", "commit", "push"]):
            classification = "COMMAND"
        elif any(w in text for w in ["teach", "explain", "why", "how", "debug", "refactor", "code"]):
            classification = "THINKING"
        else:
            classification = "DIRECT"

        return {
            "classification": classification,
            "intent": "heuristic_fallback",
            "entities": {},
            "reason": "fallback parser due to json decode error"
        }
