import logging
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from .browser import PlaywrightBrowserManager

class WebSearch:
    def __init__(self, browser_manager: PlaywrightBrowserManager):
        self.browser = browser_manager
        self.logger = logging.getLogger("Jarvis.WebSearch")

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Runs a web search using search.yahoo.com and parses results.
        Returns a list of result dicts: {"title": str, "snippet": str, "url": str}
        """
        self.logger.info(f"Executing web search for: '{query}'")
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://search.yahoo.com/search?q={encoded_query}"
        
        try:
            self.browser.navigate(url)
            page = self.browser.get_page()
            html = page.content()
            
            soup = BeautifulSoup(html, "html.parser")
            results = []
            
            for result_div in soup.find_all("div", class_=lambda x: x and "algo" in x.split()):
                title_h3 = result_div.find("h3", class_=lambda x: x and "title" in x.split())
                if not title_h3:
                    continue
                title = title_h3.get_text().strip()
                
                parent_a = title_h3.find_parent("a")
                if not parent_a:
                    continue
                url_href = parent_a.get("href")
                
                snippet_div = result_div.find("div", class_=lambda x: x and "compText" in x.split())
                snippet = snippet_div.get_text().strip() if snippet_div else ""
                
                # Sanitize text
                title = "".join(c for c in title if c.isprintable())
                snippet = "".join(c for c in snippet if c.isprintable())
                
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": url_href
                })
                
                if len(results) >= max_results:
                    break
                    
            self.logger.info(f"Web search found {len(results)} matches.")
            return results
        except Exception as e:
            self.logger.error(f"Search query failed: {e}")
            return []
