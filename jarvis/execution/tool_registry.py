import logging
from typing import Callable, Dict, Any, Optional

class ToolRegistry:
    def __init__(self):
        self._registry: Dict[str, Callable] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger("Jarvis.ToolRegistry")

    def register(self, name: str, permission_level: str = "MEDIUM"):
        """
        Decorator to register a tool function.
        """
        def decorator(func: Callable):
            self._registry[name] = func
            self._metadata[name] = {
                "name": name,
                "permission_level": permission_level,
                "doc": func.__doc__ or ""
            }
            self.logger.debug(f"Registered tool '{name}' (Level: {permission_level})")
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._registry.get(name)

    def get_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        return self._metadata.get(name)

    def get_all_tools(self) -> Dict[str, Callable]:
        return self._registry

    def get_all_metadata(self) -> Dict[str, Dict[str, Any]]:
        return self._metadata
