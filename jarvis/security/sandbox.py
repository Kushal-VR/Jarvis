import os
from pathlib import Path

class SecuritySandbox:
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(os.path.abspath(workspace_path))
        os.makedirs(self.workspace_path, exist_ok=True)

    def is_safe_path(self, target_path: str) -> bool:
        """
        Verify if a target path is located within the workspace boundary.
        Prevents directory traversal attacks (e.g., ../../../).
        """
        try:
            target_abs = Path(os.path.abspath(target_path))
            # Resolve symbolic links to get real absolute paths
            target_resolved = target_abs.resolve()
            workspace_resolved = self.workspace_path.resolve()
            
            # Check if the workspace path is a prefix of the target path
            return workspace_resolved in target_resolved.parents or target_resolved == workspace_resolved
        except Exception:
            return False

    def validate_and_resolve(self, target_path: str) -> str:
        """
        Validates target path. Raises PermissionError if unsafe, otherwise returns resolved absolute path.
        """
        resolved = os.path.abspath(target_path)
        if not self.is_safe_path(resolved):
            raise PermissionError(f"Security Sandbox Violation: Path '{target_path}' is outside the authorized workspace: '{self.workspace_path}'")
        return resolved
