import requests
from bs4 import BeautifulSoup


def search_duckduckgo(query):
    """
    Perform DuckDuckGo search and return raw HTML links
    """

    try:
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.post(url, data=params, headers=headers)

        if response.status_code != 200:
            return None

        return response.text

    except Exception as e:
        print("Search error:", e)
        return None