"""
agents/ingestion.py
Scrapes the Mixlr broadcast page / RSS feed, detects the latest broadcast,
and downloads the audio file to output/broadcast.mp3.
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from config import Config

logger = logging.getLogger(__name__)

# Mixlr may expose an RSS feed at /broadcasts.rss or similar paths.
# We try RSS first, then fall back to HTML scraping.
_RSS_SUFFIXES = ["/broadcasts.rss", ".rss", "/rss"]
_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".aac")
_REQUEST_TIMEOUT = 30  # seconds
_DOWNLOAD_CHUNK = 65_536  # 64 KiB


class IngestionError(RuntimeError):
    """Raised when audio cannot be located or downloaded."""


def _extract_channel_name(url: str) -> str:
    """Best-effort extraction of a Mixlr channel name from a URL."""
    path = urlparse(url).path.strip("/")
    return path.split("/")[0] if path else urlparse(url).netloc


def _try_rss(base_url: str, timeout: int = _REQUEST_TIMEOUT) -> Optional[str]:
    """
    Attempt to locate an audio URL via Mixlr RSS feed.
    Returns the first enclosure URL found, or None.
    """
    for suffix in _RSS_SUFFIXES:
        rss_url = base_url.rstrip("/") + suffix
        try:
            feed = feedparser.parse(rss_url)
            if feed.bozo and not feed.entries:
                continue
            for entry in feed.entries:
                # Check enclosures (standard podcast / audio RSS)
                for enc in getattr(entry, "enclosures", []):
                    if enc.get("href") or enc.get("url"):
                        audio_url = enc.get("href") or enc.get("url")
                        logger.info("Found audio via RSS enclosure: %s", audio_url)
                        return audio_url
                # Some Mixlr feeds embed the link directly
                link = getattr(entry, "link", "")
                if any(link.lower().endswith(ext) for ext in _AUDIO_EXTENSIONS):
                    logger.info("Found audio link via RSS entry: %s", link)
                    return link
        except Exception as exc:  # noqa: BLE001
            logger.debug("RSS attempt failed for %s: %s", rss_url, exc)
    return None


def _try_html_scrape(
    page_url: str, session: requests.Session, timeout: int = _REQUEST_TIMEOUT
) -> Optional[str]:
    """
    Scrape the Mixlr page HTML for a direct audio download link or a
    JSON-LD / meta embed containing the stream URL.
    Returns the first plausible audio URL found, or None.
    """
    try:
        resp = session.get(page_url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise IngestionError(f"Failed to fetch page {page_url}: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Direct <a> or <source> tags pointing to audio
    for tag in soup.find_all(["a", "source"]):
        href = tag.get("href") or tag.get("src") or ""
        if any(href.lower().endswith(ext) for ext in _AUDIO_EXTENSIONS):
            return urljoin(page_url, href)

    # 2. Mixlr embeds its CDN URL inside JS / JSON blobs – look for mp3 patterns
    mp3_pattern = re.compile(
        r'https?://[^\s\'"<>]+(?:' + "|".join(_AUDIO_EXTENSIONS) + r')[^\s\'"<>]*'
    )
    for match in mp3_pattern.finditer(resp.text):
        url = match.group(0)
        logger.info("Found audio URL via regex scrape: %s", url)
        return url

    return None


def _download_audio(
    audio_url: str,
    dest_path: str,
    session: requests.Session,
    timeout: int = _REQUEST_TIMEOUT,
) -> None:
    """Stream-download an audio file to *dest_path*."""
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading audio from %s → %s", audio_url, dest_path)
    with session.get(audio_url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=_DOWNLOAD_CHUNK):
                if chunk:
                    fh.write(chunk)

    size_mb = os.path.getsize(dest_path) / (1024 * 1024)
    logger.info("Download complete. File size: %.2f MB", size_mb)


def run(cfg: Config) -> str:
    """
    Main entry point for the ingestion agent.

    Locates the latest Mixlr broadcast audio and downloads it.

    Returns:
        Path to the downloaded audio file.
    """
    logger.info("Ingestion agent started. Target: %s", cfg.mixlr_target_url)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; ContentPipelineBot/1.0; "
                "+https://github.com/dukemawex/FEAT)"
            )
        }
    )

    # 1. Try RSS feed
    audio_url = _try_rss(cfg.mixlr_target_url)

    # 2. Fall back to HTML scraping
    if not audio_url:
        logger.info("RSS lookup yielded nothing; falling back to HTML scrape.")
        audio_url = _try_html_scrape(cfg.mixlr_target_url, session)

    if not audio_url:
        raise IngestionError(
            f"Could not locate any audio broadcast at {cfg.mixlr_target_url}. "
            "Verify MIXLR_TARGET_URL is correct and the channel has recent broadcasts."
        )

    # 3. Download
    _download_audio(audio_url, cfg.output_audio, session)

    return cfg.output_audio
