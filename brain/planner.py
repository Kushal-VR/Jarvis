# brain/planner.py

"""
Planner

Breaks user intent into multi-step execution plan.
This is what enables "agent-like" behavior.
"""


class Planner:

    def create_plan(self, intent_data: dict) -> list:
        """
        Convert intent into execution steps

        Returns:
            list of steps
        """

        intent = intent_data["intent"]

        # =========================================
        # 🌐 WEB SEARCH PLAN
        # =========================================
        if intent == "search_web":
            return [
                {"step": "search", "tool": "web_search"},
                {"step": "extract", "tool": "web_scraper"},
                {"step": "summarize", "tool": "summarizer"}
            ]

        # =========================================
        # 📂 FILE READ (SINGLE STEP)
        # =========================================
        if intent == "read_file":
            return [
                {"step": "execute", "tool": "read_file"}
            ]

        # =========================================
        # DEFAULT
        # =========================================
        return [
            {"step": "execute", "tool": intent}
        ]