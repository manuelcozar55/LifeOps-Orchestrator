import urllib.request
import urllib.error
import structlog
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict
from langsmith import traceable
import os
import json
from datetime import datetime

logger = structlog.get_logger()

# Resolve the data/ directory relative to this file's location so the cache
# works correctly regardless of the working directory from which the app is launched.
# src/tools/news.py → parents[1] = src/ → parents[2] = project root
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class NewsFetcherTool:
    """Fetches and parses RSS feeds to gather daily news."""

    DEFAULT_FEEDS = [
        "https://www.eldiario.es/rss/",
        "https://www.eleconomista.es/rss/rss-portada.php",
        "https://feeds.bbci.co.uk/news/world/rss.xml",  # Global top news
    ]

    def __init__(self, feeds: List[str] = None):
        self.feeds = feeds or self.DEFAULT_FEEDS

    @traceable(run_type="tool", name="fetch_rss_news")
    def fetch_news(self, max_items_per_feed: int = 3) -> List[Dict[str, str]]:
        """Fetches news from the configured RSS feeds and returns basic parsed data. Caches daily."""
        import re

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _DATA_DIR / "news_cache.json"
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Intentar leer desde caché diaria
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    if cache_data.get("date") == today_str:
                        logger.info("Retornando noticias desde la caché diaria local.")
                        return cache_data.get("news", [])
            except Exception as e:
                logger.warning("Fallo al procesar caché de noticias", error=str(e))
                
        results = []
        for feed_url in self.feeds:
            logger.info("Fetching RSS feed", url=feed_url)
            try:
                # Basic HTTP request without heavy requests dependency (built-in urllib)
                req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    rss_data = response.read()
                    
                # Pasamos el XML
                root = ET.fromstring(rss_data)
                channel = root.find("channel")
                
                count = 0
                for item in channel.findall("item"):
                    if count >= max_items_per_feed:
                        break
                    title = item.find("title").text if item.find("title") is not None else "No Title"
                    link = item.find("link").text if item.find("link") is not None else ""
                    # hackernews rss missing description sometimes
                    desc_elem = item.find("description")
                    description = desc_elem.text if desc_elem is not None else ""
                    # Strip HTML to save tokens
                    clean_desc = re.sub(r'<[^>]+>', '', description).strip()
                    
                    results.append({
                        "title": title,
                        "link": link,
                        "description": clean_desc[:300] + "..." if len(clean_desc) > 300 else clean_desc,
                        "source": feed_url
                    })
                    count += 1
            except Exception as e:
                logger.error("Failed to fetch or parse RSS feed", url=feed_url, error=str(e))
                
        # Guardar en caché
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"date": today_str, "news": results}, f, ensure_ascii=False, indent=2)
            logger.info("News cache written", path=str(cache_file))
        except Exception as e:
            logger.warning("Fallo al escribir caché de noticias", error=str(e))
            
        return results
