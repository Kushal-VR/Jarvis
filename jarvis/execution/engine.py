import os
import shutil
import logging
import traceback
from typing import Dict, Any, List
from jarvis.security.sandbox import SecuritySandbox
from jarvis.security.permissions import PermissionManager
from .tool_registry import ToolRegistry

class ExecutionEngine:
    def __init__(self, registry: ToolRegistry, sandbox: SecuritySandbox, permissions: PermissionManager):
        self.registry = registry
        self.sandbox = sandbox
        self.permissions = permissions
        self.logger = logging.getLogger("Jarvis.ExecutionEngine")
        
        # Transaction state for rollbacks
        self._created_files = []
        self._created_folders = []

    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a planned graph of steps.
        Enforces sandboxing, requests permission prompts, and handles rollbacks on error.
        """
        steps = plan.get("steps", [])
        if not steps:
            return {"status": "SUCCESS", "message": "No steps to execute.", "results": []}

        self.logger.info(f"Starting execution of plan containing {len(steps)} steps.")
        self._created_files.clear()
        self._created_folders.clear()

        results = []
        success = True
        error_msg = ""

        try:
            for idx, step in enumerate(steps):
                # Check for Escape key abort
                try:
                    import ctypes
                    if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                        raise RuntimeError("Plan execution aborted by user (Escape key pressed).")
                except Exception as e:
                    if "aborted by user" in str(e):
                        raise e

                tool_name = step.get("tool")
                args = step.get("args", {})
                
                tool_func = self.registry.get_tool(tool_name)
                metadata = self.registry.get_metadata(tool_name)
                
                if not tool_func or not metadata:
                    raise ValueError(f"Execution Error: Unknown tool '{tool_name}' in step {idx+1}")
                
                # Retrieve permission level
                perm_level = metadata["permission_level"]
                
                # Check sandbox for path-based tools
                self._verify_sandbox_constraints(tool_name, args)
                
                # Ask user permission
                desc = f"Invoke tool '{tool_name}' with arguments: {args}"
                approved = self.permissions.request_approval(tool_name, desc, perm_level)
                
                if not approved:
                    raise PermissionError(f"Execution Aborted: User denied permission for '{tool_name}'")

                self.logger.info(f"Executing step {idx+1}/{len(steps)}: {tool_name}")
                
                # Keep track of file system side effects for transaction rollback
                self._track_side_effects(tool_name, args)
                
                # Run tool
                output = tool_func(**args)
                
                results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "status": "SUCCESS",
                    "output": output
                })

        except Exception as e:
            success = False
            error_msg = str(e)
            self.logger.error(f"Plan execution failed at step {len(results)+1}: {e}\n{traceback.format_exc()}")
            self.rollback()

        if success:
            self.logger.info("Plan executed successfully.")
            return {
                "status": "SUCCESS",
                "results": results
            }
        else:
            return {
                "status": "FAILURE",
                "message": error_msg,
                "results": results
            }

    def _verify_sandbox_constraints(self, tool_name: str, args: dict):
        """
        Verify that path parameters are within sandbox.
        """
        # Specific system tools are allowed to access any path with user consent
        if tool_name in ["locate_path", "read_file_content", "write_file_content", "open_path", "list_files"]:
            return

        path_keys = ["path", "file_path", "repo_path", "folder_path", "dest", "src"]
        for key in path_keys:
            if key in args and isinstance(args[key], str):
                # Verify and resolve paths safely
                args[key] = self.sandbox.validate_and_resolve(args[key])

    def _track_side_effects(self, tool_name: str, args: dict):
        """
        Record created files and folders so they can be rolled back if execution fails later.
        """
        if tool_name == "create_file" and "path" in args:
            file_path = args["path"]
            if not os.path.exists(file_path):
                self._created_files.append(file_path)
        elif tool_name == "create_folder" and "path" in args:
            folder_path = args["path"]
            if not os.path.exists(folder_path):
                self._created_folders.append(folder_path)

    def rollback(self):
        """
        Reverts file system changes made during the current failed execution transaction.
        """
        self.logger.warning("Initiating rollback system...")
        
        # Rollback files first
        for file_path in self._created_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    self.logger.info(f"Rollback: Removed created file '{file_path}'")
            except Exception as e:
                self.logger.error(f"Rollback failed to remove file '{file_path}': {e}")
                
        # Rollback folders
        for folder_path in self._created_folders:
            try:
                if os.path.exists(folder_path):
                    shutil.rmtree(folder_path)
                    self.logger.info(f"Rollback: Removed created folder '{folder_path}'")
            except Exception as e:
                self.logger.error(f"Rollback failed to remove folder '{folder_path}': {e}")

        self._created_files.clear()
        self._created_folders.clear()
