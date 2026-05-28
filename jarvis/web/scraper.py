import logging
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from .browser import PlaywrightBrowserManager

class WebScraper:
    def __init__(self, browser_manager: PlaywrightBrowserManager):
        self.browser = browser_manager
        self.logger = logging.getLogger("Jarvis.WebScraper")

    def scrape_url(self, url: str) -> Dict[str, Any]:
        """
        Navigates to the url and extracts structured textual data.
        """
        try:
            self.browser.navigate(url)
            page = self.browser.get_page()
            html = page.content()
            title = page.title()
            
            return self.scrape_html(html, title, url)
        except Exception as e:
            self.logger.error(f"Failed to scrape url '{url}': {e}")
            return {"error": str(e), "title": "", "text": "", "links": [], "tables": []}

    def scrape_html(self, html_content: str, title: str = "", url: str = "") -> Dict[str, Any]:
        """
        Parses raw HTML content to extract text, links, and tables.
        """
        self.logger.info(f"Parsing HTML content for: {title}")
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Clean up script and style tags
        for element in soup(["script", "style", "header", "footer", "nav"]):
            element.decompose()

        # Extract textual content
        text = soup.get_text(separator="\n")
        # Clean whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)

        # Extract links
        links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Ignore anchors or javascript calls
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            links.append({
                "label": a_tag.get_text().strip(),
                "url": href
            })

        # Extract tables
        tables = []
        for table_tag in soup.find_all("table"):
            rows = []
            for row in table_tag.find_all("tr"):
                cols = [col.get_text().strip() for col in row.find_all(["td", "th"])]
                rows.append(cols)
            tables.append(rows)

        return {
            "title": title,
            "url": url,
            "text": clean_text[:5000], # Cap text length for reasoning memory
            "links": links[:50],       # Top 50 links
            "tables": tables
        }
