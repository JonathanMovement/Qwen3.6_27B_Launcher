import requests
from html.parser import HTMLParser

class TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "svg", "form"}
    BLOCK_TAGS = {"p", "div", "br", "li", "tr", "table", "section", "article",
                  "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0 # > 0 while inside a tag we ignore

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n") # new paragraph / table row = new line

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)

    def get_text(self):
        raw = " ".join(self.parts)
        lines = []
        for line in raw.split("\n"):
            line = " ".join(line.split()) # collapse repeated spaces
            if line:
                lines.append(line)
        return "\n".join(lines)

class SearXClient:
    def __init__(self, base_url="http://127.0.0.1:8081"):
        self.url = f"{base_url}/search"
        self.last_unresponsive = []

    def search(self, query, count=5):
        params ={
            "q": query,
            "format": "json",
            "language": "en",
            "safesearch": 0
        }

        response = requests.get(
            self.url,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()
        self.last_unresponsive = data.get("unresponsive_engines", [])

        snippets = []

        for box in data.get("infoboxes", []):
            url = box.get("id", "")
            box_urls = box.get("urls", [])
            if box_urls:
                url = box_urls[0].get("url", url)
            snippets.append(
                {
                    "title": box.get("infobox", ""),
                    "url": url,
                    "content": box.get("content", "")
                }
            )

        for result in data.get("results", [])[:count]:
            snippets.append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", "")
                }
            )
        return snippets

    def fetch_page(self, url, max_chars=4000):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                 "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        try:
            response = requests.get(url, headers=headers, timeout=6)
            response.raise_for_status()
        except Exception:
            return "" # blocked, timed out or missing - just skip this page

        if "html" not in response.headers.get("Content-Type", ""):
            return "" # PDFs, images etc.

        encoding = response.encoding
        if encoding is None or encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding # avoid broken characters

        parser = TextExtractor()
        try:
            parser.feed(response.text)
        except Exception:
            return ""

        text = parser.get_text()
        if len(text) < 200:
            return "" # JavaScript-only page or a bot-check page, nothing useful
        return text[:max_chars]        
