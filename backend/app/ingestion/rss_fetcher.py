import logging
from datetime import UTC, datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser  # type: ignore

logger = logging.getLogger(__name__)

# 25 global RSS feeds
RSS_FEEDS = [
    # International Wire
    # ("Reuters", "https://feeds.reuters.com/reuters/topNews"),
    # ("Reuters", "https://ir.thomsonreuters.com/rss-feeds"),
    # ("AP News", "https://feeds.apnews.com/rss/apf-topnews"),
    ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("DW", "https://rss.dw.com/rdf/rss-en-all"),
    ("France 24", "https://www.france24.com/en/rss"),
    # US
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
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
    ("FT", "https://www.ft.com/rss/home/us"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ("CNBC",   "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    # Science / Health
    ("Science Daily",   "https://www.sciencedaily.com/rss/all.xml"),
    ("WHO",    "https://www.who.int/rss-feeds/news-releases-en.xml"),
    # Climate
    ("Carbon Brief", "https://www.carbonbrief.org/feed"),
    # Africa / Nigeria
    ("Africa News",       "https://www.africanews.com/feed/"),
    ("Premium Times",     "https://www.premiumtimesng.com/feed"),
    ("Daily Trust",        "https://dailytrust.com/feed/"),
    ("Guardian Nigeria",  "https://guardian.ng/feed"),
    ("PM News",           "https://pmnewsnigeria.com/feed/"),
    ("Channels TV",       "https://www.channelstv.com/feed/"),
    ("Vanguard",          "https://www.vanguardngr.com/feed/"),
    ("Punch",             "https://punchng.com/feed/"),
    ("The Cable",         "https://www.thecable.ng/feed"),
    ("Mail & Guardian",   "https://mg.co.za/feed/"),
]


class RSSFetcher:

    def fetch_all(self) -> list[dict]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        all_articles = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_feed = {
                executor.submit(self._fetch_feed, source_name, feed_url): source_name
                for source_name, feed_url in RSS_FEEDS
            }
            for future in as_completed(future_to_feed):
                source_name = future_to_feed[future]
                try:
                    articles = future.result()
                    all_articles.extend(articles)
                except Exception as e:
                    logger.warning(f"[RSS] Unhandled exception for {source_name}: {e}")

        logger.info(f"[RSS] Total articles from feeds: {len(all_articles)}")
        return all_articles

    def _fetch_feed(self, source_name: str, feed_url: str) -> list[dict]:
        import re

        import requests

        def strip_html(html_str):
            if not html_str: return ""
            text = re.sub(r'<[^>]+>', ' ', html_str)
            return ' '.join(text.split())

        try:
            resp = requests.get(feed_url, timeout=20)
            feed = feedparser.parse(resp.content)
            results = []
            for entry in feed.entries:
                url   = entry.get("link", "")
                title = entry.get("title", "").strip()
                if not url or not title:
                    continue
            # return entry
                # Try to get the longest text available in the RSS feed
                content_html = ""
                if "content" in entry and len(entry.content) > 0:
                    content_html = entry.content[0].get("value", "")
                summary_html = entry.get("summary", "")

                body = strip_html(content_html)
                if len(body) < 150:
                    body = strip_html(summary_html)

                results.append({
           "title": title,
           "url": url,
           "source": source_name,
           "published_at": self._parse_date(entry),
           "description": strip_html(summary_html),
           "body":  body,
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
        if (hasattr(entry, "published_parsed") and entry.published_parsed) or (hasattr(entry, "updated_parsed") and entry.updated_parsed):
            try:
                parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                dt = datetime(parsed[0], parsed[1], parsed[2],
                            parsed[3], parsed[4], parsed[5], tzinfo=UTC)
                return dt.isoformat()
            except (IndexError, TypeError, ValueError):
                pass

        # fallback: raw published string
        raw = entry.get("published") or entry.get("updated")
        if raw:
            try:
                print("=="*50)
                print(f"{entry['links'][0]['href'][11:30]}")
                print("="*50)
                dt = parsedate_to_datetime(raw).astimezone(UTC)
                return dt.isoformat()
            except Exception:
                logger.exception("Failed to parse publication date")

        return None
