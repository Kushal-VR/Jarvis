import os
import subprocess
import logging
from typing import Dict, Any
from jarvis.brain.model_manager import OllamaModelManager

class DeveloperAgent:
    def __init__(self, model_manager: OllamaModelManager):
        self.model_manager = model_manager
        self.logger = logging.getLogger("Jarvis.DeveloperAgent")

    def create_project_structure(self, workspace_path: str, project_name: str, language: str) -> str:
        """
        Creates basic files and folder layout for a new programming project.
        """
        self.logger.info(f"Creating project '{project_name}' in language '{language}'")
        project_dir = os.path.join(workspace_path, project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        if language.lower() == "python":
            # Create src folder, main.py, requirements.txt, and a simple test file
            os.makedirs(os.path.join(project_dir, "src"), exist_ok=True)
            os.makedirs(os.path.join(project_dir, "tests"), exist_ok=True)
            
            with open(os.path.join(project_dir, "src", "main.py"), "w") as f:
                f.write('def main():\n    print("Hello from Jarvis Dev Agent!")\n\nif __name__ == "__main__":\n    main()\n')
            with open(os.path.join(project_dir, "requirements.txt"), "w") as f:
                f.write('# Add your project dependencies here\n')
            with open(os.path.join(project_dir, "tests", "test_main.py"), "w") as f:
                f.write('def test_dummy():\n    assert True\n')
                
        elif language.lower() in ["node", "javascript", "typescript"]:
            # Create package.json and index.js
            run_cmd = f"npm init -y"
            try:
                subprocess.run(run_cmd, cwd=project_dir, shell=True, check=True, stdout=subprocess.DEVNULL)
            except Exception:
                pass
            with open(os.path.join(project_dir, "index.js"), "w") as f:
                f.write('console.log("Hello from Jarvis Node Dev Agent!");\n')
                
        return f"Successfully created project structure for {project_name} at {project_dir}"

    def write_code(self, file_path: str, instruction: str) -> str:
        """
        Generates and writes source code to file_path based on user instructions.
        Uses qwen2.5-coder:7b.
        """
        self.logger.info(f"Generating code for file '{file_path}' using qwen2.5-coder...")
        system_prompt = (
            "You are the senior coder agent of Jarvis. Generate only correct, clean, and well-commented "
            "source code. Do not include markdown code block backticks (```python or ```) in your output, "
            "only return the raw code lines. Do not write explanation text."
        )
        
        prompt = f"Write code to implement: {instruction}\nTarget file name: {os.path.basename(file_path)}"
        
        code = self.model_manager.generate(
            model_key="coding",
            prompt=prompt,
            system_prompt=system_prompt
        )
        
        # Strip code formatting markers if the model included them anyway
        clean_code = code.strip()
        if clean_code.startswith("```"):
            lines = clean_code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_code = "\n".join(lines).strip()
            
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(clean_code)
            
        self.logger.info(f"Code successfully written to '{file_path}'")
        return f"Written code to {file_path}"

    def compile_and_debug(self, file_path: str, run_command_str: str, max_attempts: int = 3) -> bool:
        """
        Runs code execution tests and performs self-debugging if errors occur.
        """
        self.logger.info(f"Testing execution: '{run_command_str}' in folder '{os.path.dirname(file_path)}'")
        
        for attempt in range(1, max_attempts + 1):
            self.logger.info(f"Execution run attempt {attempt}/{max_attempts}...")
            
            # Execute run command
            res = subprocess.run(
                run_command_str,
                cwd=os.path.dirname(file_path),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if res.returncode == 0:
                self.logger.info(f"Execution succeeded on attempt {attempt}.")
                return True
                
            # Grab stderr
            error_output = res.stderr.strip()
            self.logger.warning(f"Run failed with error:\n{error_output}")
            
            if attempt == max_attempts:
                break
                
            # If failed, read file content and prompt debugger model to fix it
            with open(file_path, "r", encoding="utf-8") as f:
                current_code = f.read()
                
            system_prompt = (
                "You are the debugger agent of Jarvis. Fix bugs in source code. "
                "Output ONLY the corrected code without markdown backticks (```) or explanation text."
            )
            
            debug_prompt = (
                f"Source Code:\n{current_code}\n\n"
                f"Execution Command: {run_command_str}\n"
                f"Error Message:\n{error_output}\n\n"
                f"Please inspect the error trace, identify the cause, and return the fixed, complete source code file."
            )
            
            self.logger.info("Requesting code fix from debugger model...")
            fixed_code = self.model_manager.generate(
                model_key="coding",
                prompt=debug_prompt,
                system_prompt=system_prompt
            )
            
            clean_fixed = fixed_code.strip()
            if clean_fixed.startswith("```"):
                lines = clean_fixed.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_fixed = "\n".join(lines).strip()
                
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(clean_fixed)
                
            self.logger.info(f"Fixed code written back to file '{file_path}'. Re-running tests...")
            
        self.logger.error("Failed to fix code bugs after max debugging attempts.")
        return False
