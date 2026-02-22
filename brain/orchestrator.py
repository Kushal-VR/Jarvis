# =====================================================
# ORCHESTRATOR - CENTRAL DECISION ENGINE
# =====================================================

from guardian.security import scan_system
from brain.memory import get_all_memory
from brain.llm import ask_llm
from brain.intent_engine import IntentEngine
from brain.file_resolver import resolve_filename
from brain.planner import Planner

from brain.web.news import get_ai_news
from brain.web.search import search_duckduckgo
from brain.web.scraper import extract_titles
from brain.web.summarizer import summarize_list
from brain.context import store_results, get_last_results

# =====================================================
# INIT
# =====================================================
intent_engine = IntentEngine()
planner = Planner()


# =====================================================
# HELPER: DETECT RISKY PROCESS
# =====================================================
def detect_risky_process(report_text):

    lines = report_text.split("\n")
    risky = []

    for line in lines:
        if "→ Risk Score:" in line:
            try:
                name = line.split("→")[0].strip()
                score = int(line.split("Risk Score:")[1].split()[0])

                if score >= 20:
                    risky.append((name, score))

            except:
                continue

    if not risky:
        return None

    risky.sort(key=lambda x: x[1], reverse=True)
    return risky[0][0]


# =====================================================
# MAIN ORCHESTRATOR
# =====================================================
def orchestrate(user_input: str):

    text = user_input.lower()

    # =====================================================
    # 🧠 INTENT DETECTION
    # =====================================================
    intent_data = intent_engine.detect_intent(user_input)

    print("🧠 ORCHESTRATOR INTENT:", intent_data)

    intent = intent_data["intent"]
    entities = intent_data["entities"]

    # =====================================================
    # 🧠 CREATE PLAN
    # =====================================================
    plan = planner.create_plan(intent_data)
    print("🧠 PLAN:", plan)

    # =====================================================
    # 📂 FILE READ
    # =====================================================
    if intent == "read_file":
        raw_filename = entities.get("file")

        if raw_filename:
            filename = resolve_filename(raw_filename)
            print(f"🛠 RESOLVED FILE: {raw_filename} → {filename}")

            return {
                "action": "dev_read",
                "target": filename
            }

        return {"message": "Please specify file name clearly."}

    # =====================================================
    # 🌐 SMART WEB SEARCH (FIXED + INTELLIGENT)
    # =====================================================
    if intent == "search_web":

        query = entities.get("query", "").lower().strip().replace(".", "")

        # =====================================================
        # 🔥 AI NEWS ONLY
        # =====================================================
        if "ai" in query:
            print("📰 Fetching AI news...")
            news = get_ai_news()

            print("📰 RAW NEWS:", news)

            if not news:
                return {"message": "Couldn't fetch AI news right now."}

            summary = "Here’s latest AI news:\n\n"

            for i, item in enumerate(news, 1):
                summary += f"{i}. {item.strip()}\n"
            store_results(news)   # 🔥 STORE RESULTS
            return {"message": summary.strip()}

        # =====================================================
        # 🌍 GENERAL SEARCH
        # =====================================================
        print("🌍 Fetching general web results...")

        data = None

        for step in plan:
            tool = step["tool"]

            if tool == "web_search":
                data = search_duckduckgo(query)

            elif tool == "web_scraper":
                data = extract_titles(data)

            elif tool == "summarizer":
                data = summarize_list(data)

        if not data:
            return {"message": "No results found."}
        store_results(data)   # 🔥 STORE RESULTS
        return {"message": data}

    # =====================================================
    # SECURITY
    # =====================================================
    if "scan system" in text:
        result = scan_system()
        return {"message": result["report"]}

    if "close risky" in text:
        result = scan_system()
        report = result["report"]
        suspect = result.get("suspect")

        if suspect:
            return {
                "action": "terminate",
                "target": suspect,
                "message": report + f"\n\n⚠ Suspected: {suspect}"
            }

        risky = detect_risky_process(report)

        if risky:
            return {
                "action": "terminate",
                "target": risky,
                "message": report + f"\n\n⚠ Suggested: {risky}"
            }

        return {"message": report}

    # =====================================================
    # MEMORY
    # =====================================================
    if "what do you remember" in text:
        return {"message": get_all_memory()}
    # =====================================================
    # 🧠 CONTEXT-AWARE FOLLOW UPS
    # =====================================================
    if "first" in text or "second" in text or "third" in text:

        results = get_last_results()

        if not results:
           return {"message": "No previous results found."}

        index = 0

        if "second" in text:
         index = 1
        elif "third" in text:
         index = 2

        if index >= len(results):
         return {"message": "Result not available."}

        item = results[index]

        return {
          "message": f"Here is more about it:\n{item}"
        }


    if "summarize" in text or "summary" in text:

        results = get_last_results()

        if not results:
          return {"message": "Nothing to summarize."}

        summary = "Summary of results:\n\n"

        for i, item in enumerate(results[:3], 1):
           summary += f"{i}. {item}\n"

        return {"message": summary.strip()}
    # =====================================================
    # DEFAULT → LLM
    # =====================================================
    response = ask_llm(user_input)

    return {
        "message": response
    }