import requests

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
