import hashlib
import html
import logging
import re
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser

from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

MAX_AGE_HOURS = settings.rolling_window_days * 24


class Normalizer:

    def normalize(self, articles: list[dict]) -> list[dict]:
        """
        1. Parse + validate timestamps
        2. Drop articles outside the rolling window
        3. Deduplicate by URL and title fingerprint
        4. Clean HTML entities from body/description
        """
        parsed    = [a for a in (self._parse_dates(a) for a in articles) if a]
        windowed  = [a for a in parsed if self._within_window(a)]
        unique    = self._deduplicate(windowed)
        for a in unique:
            a["body"]        = self._clean_text(a.get("body", ""))
            a["description"] = self._clean_text(a.get("description", ""))
            a["title"]       = self._clean_text(a.get("title", ""))

        logger.info(
            f"[Normalizer] {len(articles)} in → "
            f"{len(parsed)} parsed → "
            f"{len(windowed)} in window → "
            f"{len(unique)} unique"
        )
        return unique

    # ── Date Parsing ─────────────────────────────────────────
    def _parse_dates(self, article: dict) -> dict | None:
        raw = article.get("published_at")
        if not raw:
            # default to now if completely missing
            article["published_at"] = datetime.now(timezone.utc).isoformat()
            return article
        try:
            dt = dateparser.parse(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            article["published_at"] = dt.isoformat()
            return article
        except Exception:
            logger.debug(f"[Normalizer] Could not parse date: {raw}")
            return None

    # ── Rolling Window ────────────────────────────────────────
    def _within_window(self, article: dict) -> bool:
        try:
            # published_at is already a normalized ISO 8601 string from _parse_dates;
            # use fromisoformat instead of the slower dateparser regex engine.
            dt  = datetime.fromisoformat(article["published_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - dt
            return age <= timedelta(hours=MAX_AGE_HOURS)
        except Exception:
            return False

    # ── Deduplication ─────────────────────────────────────────
    def _deduplicate(self, articles: list[dict]) -> list[dict]:
        seen_urls        = set()
        seen_fingerprints = set()
        unique           = []

        for a in articles:
            url         = a.get("url", "").strip().rstrip("/")
            fingerprint = self._title_fingerprint(a.get("title", ""))

            if url in seen_urls or fingerprint in seen_fingerprints:
                continue

            seen_urls.add(url)
            seen_fingerprints.add(fingerprint)
            unique.append(a)

        return unique

    def _clean_text(self, text: str) -> str:
        """Decode HTML entities and strip any residual HTML tags."""
        if not text:
            return ""
        text = html.unescape(text)                          # &amp; &#160; &mdash; etc.
        text = re.sub(r"<[^>]+>", " ", text)               # strip <tags>
        text = re.sub(r"\s+", " ", text).strip()           # normalise whitespace
        return text

    def _title_fingerprint(self, title: str) -> str:
        """Normalize title and hash it — catches near-identical headlines."""
        cleaned = re.sub(r"[^a-z0-9 ]", "", title.lower().strip())
        cleaned = re.sub(r"\s+", " ", cleaned)
        return hashlib.md5(cleaned.encode()).hexdigest()