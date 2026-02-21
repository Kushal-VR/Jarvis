from bs4 import BeautifulSoup


def extract_titles(html):
    """
    Extract titles from DuckDuckGo HTML
    """

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    results = []

    for result in soup.find_all("a", class_="result__a", limit=5):
        results.append(result.get_text())

    return results