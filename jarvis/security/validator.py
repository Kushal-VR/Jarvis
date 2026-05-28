import re
import shlex

class CommandValidator:
    def __init__(self, whitelist_commands: list):
        self.whitelist = whitelist_commands

    def is_safe_command(self, cmd_line: str) -> bool:
        """
        Check if the command line conforms to security guidelines.
        """
        try:
            tokens = shlex.split(cmd_line)
        except Exception:
            # If shlex parsing fails, treat it as unsafe
            return False

        if not tokens:
            return True

        base_cmd = tokens[0].lower()
        
        # Strip system paths or extensions if present (e.g. C:\Windows\System32\ping.exe -> ping)
        base_cmd_clean = re.sub(r'^.*[\\/]', '', base_cmd)
        base_cmd_clean = re.sub(r'\.(exe|bat|cmd|sh)$', '', base_cmd_clean)

        # Check against whitelist
        if base_cmd_clean not in self.whitelist:
            return False

        # Block obvious malicious shell constructs
        dangerous_patterns = [
            r'rmdir\s+/s\s+/q\s+C:',
            r'del\s+/s\s+/q\s+C:',
            r'format\s+',
            r'mkfs',
            r'>\s*/dev/sd',
            r':\(\)\{\s*:\s*\|\s*:\s*&\s*\}\s*;', # Fork bomb
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd_line, re.IGNORECASE):
                return False

        return True
