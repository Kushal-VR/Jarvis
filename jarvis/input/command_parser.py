import re
from typing import Optional, Dict, Any

class FastCommandParser:
    def __init__(self):
        # Define regex patterns for fast matched commands
        # Use negative lookahead to exclude " and " from paths so they can be split correctly
        self.patterns = [
            (r'^(?:open|launch)\s+([a-zA-Z0-9\s_\-\.]+)(?:\.exe)?$', self._handle_open_app),
            (r'^(?:create|make)\s+folder\s+((?:(?! and ).)+)$', self._handle_create_folder),
            (r'^(?:create|make)\s+file\s+((?:(?! and ).)+)$', self._handle_create_file),
            (r'^(?:list|show)\s+files?$', self._handle_list_files),
            (r'^(?:print|echo)\s+(.+)$', self._handle_echo),
            (r'^(?:send|write)\s+(?:message|msg|text)\s+"([^"]+)"\s+to\s+([a-zA-Z0-9\s_\-\.\+@]+)$', self._handle_send_message),
            (r'^(?:send|write)\s+(?:message|msg|text)\s+([^"]+)\s+to\s+([a-zA-Z0-9\s_\-\.\+@]+)$', self._handle_send_message),
        ]

    def parse(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parses text input. If matches any direct fast commands, returns structural tool instruction.
        Can split commands joined by ' and ' to execute multi-step direct actions.
        Otherwise returns None to fall back to the NLU/Planner.
        """
        cleaned_text = text.strip()
        
        # Try to parse as a whole first
        plan = self._parse_single(cleaned_text)
        if plan:
            return plan
            
        # Try to split by " and "
        if " and " in cleaned_text.lower():
            parts = re.split(r'\s+and\s+', cleaned_text, flags=re.IGNORECASE)
            combined_steps = []
            for part in parts:
                step_plan = self._parse_single(part.strip())
                if step_plan and step_plan.get("steps"):
                    combined_steps.extend(step_plan["steps"])
                else:
                    # If one of the chained parts cannot be fast-tracked, fall back completely to LLM planner
                    return None
            if combined_steps:
                return {
                    "action": "EXECUTE",
                    "fast_track": True,
                    "steps": combined_steps
                }
        return None

    def _parse_single(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned_text = text.strip().lower()
        for pattern, handler in self.patterns:
            match = re.match(pattern, cleaned_text, re.IGNORECASE)
            if match:
                return handler(match)
        return None

    def _handle_open_app(self, match: re.Match) -> Dict[str, Any]:
        app_name = match.group(1).strip()
        return {
            "action": "EXECUTE",
            "fast_track": True,
            "steps": [{
                "tool": "open_app",
                "args": {"app_name": app_name}
            }]
        }

    def _handle_create_folder(self, match: re.Match) -> Dict[str, Any]:
        folder_path = match.group(1).strip()
        return {
            "action": "EXECUTE",
            "fast_track": True,
            "steps": [{
                "tool": "create_folder",
                "args": {"path": folder_path}
            }]
        }

    def _handle_create_file(self, match: re.Match) -> Dict[str, Any]:
        file_path = match.group(1).strip()
        return {
            "action": "EXECUTE",
            "fast_track": True,
            "steps": [{
                "tool": "create_file",
                "args": {"path": file_path}
            }]
        }

    def _handle_list_files(self, match: re.Match) -> Dict[str, Any]:
        return {
            "action": "EXECUTE",
            "fast_track": True,
            "steps": [{
                "tool": "list_files",
                "args": {}
            }]
        }

    def _handle_echo(self, match: re.Match) -> Dict[str, Any]:
        text = match.group(1).strip().strip('"')
        return {
            "action": "EXECUTE",
            "fast_track": True,
            "steps": [{
                "tool": "type_text",
                "args": {"text": text}
            }]
        }

    def _handle_send_message(self, match: re.Match) -> Dict[str, Any]:
        message_text = match.group(1).strip()
        contact = match.group(2).strip()
        return {
            "action": "EXECUTE",
            "fast_track": True,
            "steps": [{
                "tool": "send_message",
                "args": {"message": message_text, "recipient": contact}
            }]
        }
