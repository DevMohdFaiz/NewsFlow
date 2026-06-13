import logging
import requests
from datetime import datetime, timezone, timedelta
from newsapi import NewsApiClient
from serpapi import GoogleSearch
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)


class NewsFetcher:
    def __init__(self):
        self.newsapi = NewsApiClient(api_key=settings.news_api_key)

    #  NewsAPI 
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def fetch_newsapi(self, page_size: int = 100) -> list[dict]:
        """
        Fetch recent articles from NewsAPI using get_everything()
        so we are not locked to a single source.
        """
        from_date = (
            datetime.now(timezone.utc) - timedelta(hours=6)
        ).strftime("%Y-%m-%dT%H:%M:%S")

        try:
            response = self.newsapi.get_everything(
                q = "news",
                language="en",
                sort_by="publishedAt",
                from_param=from_date,
                page_size=page_size,
            )
            articles = response.get("articles", [])
            logger.info(f"[NewsAPI] Fetched {len(articles)} articles")
            return self._normalize_newsapi(articles)

        except Exception as e:
            logger.error(f"[NewsAPI] Fetch failed: {e}")
            return []

    def _normalize_newsapi(self, articles: list[dict]) -> list[dict]:
        results = []
        for a in articles:
            url   = a.get("url", "")
            title = a.get("title", "").strip()

            # skip removed articles and items with no URL or title
            if not url or not title or title == "[Removed]":
                continue

            results.append({
                "title":        title,
                "url":          url,
                "source":       a.get("source", {}).get("name", "Unknown"),
                "published_at": a.get("publishedAt"),
                "description":  a.get("description") or "",
                "body":         "",   # filled by extractor
                "origin":       "newsapi",
            })
        return results

    #  SerpAPI 
    def fetch_serpapi(self, queries: list[str] | None = None) -> list[dict]:
        """Discover trending stories via Google News search."""
        if queries is None:
            queries = [
                "world news today",
                "breaking news today",
                "top stories today",
            ]

        results = []
        for query in queries:
            try:
                results.extend(self._fetch_serpapi_query(query))
            except Exception as e:
                logger.error(f"[SerpAPI] Query '{query}' failed after retries: {e}")
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _fetch_serpapi_query(self, query: str) -> list[dict]:
        search = GoogleSearch({
            "q":       query,
            "tbm":     "nws",
            "num":     20,
            "api_key": settings.serp_api_key,
        })
        data         = search.get_dict()
        news_results = data.get("news_results", [])
        logger.info(f"[SerpAPI] '{query}' → {len(news_results)} results")
        return self._normalize_serpapi(news_results)

    def _normalize_serpapi(self, articles: list[dict]) -> list[dict]:
        results = []
        for a in articles:
            url   = a.get("link", "")
            title = a.get("title", "").strip()
            if not url or not title:
                continue
            results.append({
                "title":        title,
                "url":          url,
                "source":       a.get("source", "Unknown"),
                "published_at": a.get("date"),
                "description":  a.get("snippet", ""),
                "body":         "",
                "origin":       "serpapi",
            })
        return results

    #  Newsdata.io 
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def fetch_newsdata(self, query: str = "latest news") -> list[dict]:
        """
        Fetch from newsdata.io.
        Note: 'link' is the URL field in their API response.
        'category' is a list — we take only the first element.
        """
        url = (
            f"https://newsdata.io/api/1/latest"
            f"?apikey={settings.newsdata_api_key}"
            f"&q={query}"
            f"&language=en"
        )
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data    = response.json()
            results = data.get("results", [])
            logger.info(f"[Newsdata] Fetched {len(results)} articles")
            return self._normalize_newsdata(results)

        except Exception as e:
            logger.error(f"[Newsdata] Fetch failed: {e}")
            return []

    def _normalize_newsdata(self, articles: list[dict]) -> list[dict]:
        results = []
        for a in articles:
            # newsdata uses 'link' not 'url'
            url   = a.get("link", "")
            title = a.get("title", "").strip()
            if not url or not title:
                continue

            # category is a list in newsdata — flatten to string or empty
            category_raw = a.get("category", [])
            category     = category_raw[0] if isinstance(category_raw, list) and category_raw else ""

            results.append({
                "title":        title,
                "url":          url,
                "source":       a.get("source_id", "Unknown"),
                "published_at": a.get("pubDate"),   # newsdata uses pubDate not publishedAt
                "description":  a.get("description") or "",
                "body":         a.get("content") or "",   # free tier returns this as None usually
                "origin":       "newsdata",
            })
        return results

    #  Combined 
    def fetch_all(self) -> list[dict]:
        newsapi_articles  = self.fetch_newsapi()
        newsdata_articles = self.fetch_newsdata()
        # serpapi_articles = self.fetch_serpapi()  

        combined = newsapi_articles + newsdata_articles

        # Deduplicate by URL
        seen:  set[str]  = set()
        deduped: list[dict] = []
        for article in combined:
            url = article.get("url", "").strip().rstrip("/")
            if url and url not in seen:
                seen.add(url)
                deduped.append(article)

        logger.info(
            f"[NewsFetcher] {len(combined)} raw → {len(deduped)} after dedup"
        )
        return deduped