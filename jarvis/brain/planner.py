import json
import logging
from typing import Dict, Any, List
from .model_manager import OllamaModelManager

class TaskPlanner:
    def __init__(self, model_manager: OllamaModelManager):
        self.model_manager = model_manager
        self.logger = logging.getLogger("Jarvis.Planner")

    def plan_task(self, user_prompt: str, context: dict = None) -> Dict[str, Any]:
        """
        Decomposes user_prompt into a list of structured steps using qwen2.5:7b-instruct.
        """
        system_prompt = (
            "You are the orchestrator and master planner agent of Jarvis. Your goal is to plan steps to fulfill a user request.\n"
            "Analyze the user's intent and context. Decompose the request into a series of tool invocations.\n"
            "\n"
            "AVAILABLE TOOLS:\n"
            "- open_app: args: {'app_name': 'name of application'}\n"
            "- close_app: args: {'app_name': 'name of application'}\n"
            "- create_folder: args: {'path': 'relative folder path under workspace'}\n"
            "- create_file: args: {'path': 'relative path', 'content': 'string text'}\n"
            "- list_files: args: {'path': 'optional relative path'}\n"
            "- open_path: args: {'path': 'absolute path to open a file or folder in default application'}\n"
            "- read_file_content: args: {'file_path': 'absolute path to read content from a file'}\n"
            "- write_file_content: args: {'file_path': 'absolute path to write content to a file', 'content': 'string text to write'}\n"
            "- locate_path: args: {'name': 'file or folder name to search on all drives'}\n"
            "- get_user_text_input: args: {'prompt': 'prompt text to display to user', 'is_password': boolean}\n"
            "- search_web: args: {'query': 'search terms'}\n"
            "- web_scrape: args: {'url': 'target website link'}\n"
            "- collect_google_maps_leads: args: {'search_query': 'business type', 'location': 'location name', 'output_file': 'optional filename'}\n"
            "- click_coordinate: args: {'x': integer, 'y': integer}\n"
            "- type_text: args: {'text': 'string to type'}\n"
            "- press_key: args: {'key': 'key name, e.g. enter, ctrl+c'}\n"
            "- send_message: args: {'message': 'text content', 'recipient': 'recipient identifier'}\n"
            "- send_email: args: {'to': 'email address', 'subject': 'text', 'body': 'text'}\n"
            "- dev_create_project: args: {'name': 'project directory name', 'language': 'python/node'}\n"
            "- dev_write_code: args: {'file_path': 'relative path', 'code': 'source code text'}\n"
            "- dev_run_command: args: {'command': 'command line execution string'}\n"
            "- git_commit_and_push: args: {'repo_path': 'path', 'commit_message': 'message'}\n"
            "- screen_read: args: {}\n"
            "- describe_screen: args: {}\n"
            "- play_music: args: {'query': 'optional music query', 'profile_name': 'optional profile name, e.g. Kushalvr', 'guest_mode': 'optional boolean'}\n"
            "\n"
            "OUTPUT FORMAT:\n"
            "You MUST respond ONLY with a JSON object conforming to the following schema. Do not write introductory, conversational, or concluding text.\n"
            "{\n"
            "  \"action\": \"EXECUTE\",\n"
            "  \"steps\": [\n"
            "    {\n"
            "      \"tool\": \"tool_name\",\n"
            "      \"args\": {}\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "If the request cannot be fulfilled with the available tools, return an empty steps list."
        )

        prompt = f"User Request: \"{user_prompt}\"\nContext: {json.dumps(context or {})}"
        
        self.logger.info("Generating execution plan using qwen2.5:7b-instruct...")
        response_str = self.model_manager.chat(
            model_key="planning",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            format_json=True
        )

        try:
            # Clean response text
            clean_res = response_str.strip()
            if clean_res.startswith("```"):
                clean_res = clean_res.split("```")[1]
                if clean_res.startswith("json"):
                    clean_res = clean_res[4:]
            clean_res = clean_res.strip()
            
            plan = json.loads(clean_res)
            self.logger.info(f"Generated plan with {len(plan.get('steps', []))} steps.")
            return plan
        except Exception as e:
            self.logger.error(f"Failed to generate structured plan: {e}. Output was: {response_str}")
            return {
                "action": "EXECUTE",
                "steps": []
            }
