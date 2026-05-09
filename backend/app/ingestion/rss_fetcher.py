import logging
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

# 25 global RSS feeds
RSS_FEEDS = [
    # International Wire
    # ("Reuters", "https://feeds.reuters.com/reuters/topNews"),
    # ("AP News", "https://feeds.apnews.com/rss/apf-topnews"),
    ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    # ("DW", "https://rss.dw.com/rss/rss-en-all"),
    ("France 24", "https://www.france24.com/en/rss"),
    # US
    # ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("CNN", "http://rss.cnn.com/rss/edition_world.rss"),
    ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("Washington Post", "https://feeds.washingtonpost.com/rss/world"),
    # UK
    ("Guardian World", "https://www.theguardian.com/world/rss"),
    ("The Independent", "https://www.independent.co.uk/news/world/rss"),
    # Tech
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    # Business / Economy
    # ("FT", "https://www.ft.com/rss/home/us"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ("CNBC",   "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    # Science / Health
    ("Science Daily",   "https://www.sciencedaily.com/rss/all.xml"),
    # ("WHO",    "https://www.who.int/rss-feeds/news-releases-en.xml"),
    # Climate
    ("Carbon Brief", "https://www.carbonbrief.org/feed"),
    # Africa / Global South
    ("Africa News",     "https://www.africanews.com/feed/"),
    ("Premium Times",   "https://www.premiumtimesng.com/feed"),
    # ("The East African","https://www.theeastafrican.co.ke/tea/rss"),
    ("Mail & Guardian", "https://mg.co.za/feed/"),
]


class RSSFetcher:

    def fetch_all(self) -> list[dict]:
        all_articles = []
        for source_name, feed_url in RSS_FEEDS:
            articles = self._fetch_feed(source_name, feed_url)
            all_articles.extend(articles)

        logger.info(f"[RSS] Total articles from feeds: {len(all_articles)}")
        return all_articles 

    def _fetch_feed(self, source_name: str, feed_url: str) -> list[dict]:
        try:
            feed = feedparser.parse(feed_url)
            results = []
            for entry in feed.entries:
                url   = entry.get("link", "")
                title = entry.get("title", "").strip()
                if not url or not title:
                    continue

                results.append({
           "title": title,
           "url": url,
           "source": source_name,
           "published_at": self._parse_date(entry),
           "description": entry.get("summary", ""),
           "body":  "",
           "origin": "rss",
                })

            logger.info(f"[RSS] {source_name} => {len(results)} entries")
            return results

        except Exception as e:
            logger.warning(f"[RSS] Failed to fetch {source_name}: {e}")
            return []

    def _parse_date(self, entry) -> str | None:
        """Parse RSS date to ISO 8601 UTC string."""
        # feedparser provides published_parsed as time.struct_time
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        # fallback: raw published string
        raw = entry.get("published") or entry.get("updated")
        if raw:
            try:
                dt = parsedate_to_datetime(raw).astimezone(timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        return None