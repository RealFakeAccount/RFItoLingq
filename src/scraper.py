import pathlib
import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

from .config import config


class RFIScraper:
    LISTING_EPISODE_REGEX = re.compile(r"/fr/podcasts/journal-en-fran%C3%A7ais-facile/(\d{8})-")
    MP3_REGEX = re.compile(r"https?://[^\s\"]+\.mp3")

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})

    def find_episode_links(self, list_page_html: str) -> List[Tuple[datetime, str]]:
        """Extract episode URLs and dates from the listing HTML."""
        soup = BeautifulSoup(list_page_html, "html.parser")
        found = {}
        for link in soup.find_all("a", href=self.LISTING_EPISODE_REGEX):
            href = link.get("href") or ""
            match = self.LISTING_EPISODE_REGEX.search(href)
            if not match:
                continue
            date_str = match.group(1)
            try:
                date = datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                continue
            absolute = urljoin(config.RFI_BASE_URL, href)
            found[absolute] = date
        return sorted([(date, url) for url, date in found.items()], key=lambda t: t[0], reverse=True)

    def fetch_listing(self, limit: Optional[int] = None, since: Optional[datetime] = None, pages: int = 3) -> List[Tuple[datetime, str]]:
        """Download listing pages and return sorted episode URLs with dates."""
        collected: dict[str, datetime] = {}
        for page in range(max(1, pages)):
            url = config.RFI_BASE_URL if page == 0 else f"{config.RFI_BASE_URL}?page={page}"
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                chunk = self.find_episode_links(resp.text)
                before = len(collected)
                for date, link in chunk:
                    collected[link] = date
                if len(collected) == before:
                    # no new links found on this page, stop early
                    break
            except requests.RequestException as e:
                print(f"[WARN] Failed to fetch listing page {page}: {e}")
                continue

        episodes = sorted([(date, url) for url, date in collected.items()], key=lambda t: t[0], reverse=True)
        if since:
            episodes = [item for item in episodes if item[0] >= since]
        if limit:
            episodes = episodes[:limit]
        return episodes

    def extract_transcript(self, html: str) -> Optional[str]:
        """Grab plain transcript text from the on-page transcription block."""
        soup = BeautifulSoup(html, "html.parser")
        trans = soup.find(class_="m-transcription")
        if not trans:
            return None
        # keep paragraphs separated by blank lines for readability
        paras = []
        for p in trans.find_all("p"):
            raw = p.get_text(" ", strip=True)
            # collapse any repeated whitespace (the page uses many consecutive spaces)
            clean = re.sub(r"\s+", " ", raw).strip()
            if clean:
                paras.append(clean)
        if paras:
            return "\n\n".join(paras)
        # fallback to full text
        fallback = re.sub(r"\s+", " ", trans.get_text(" ", strip=True)).strip()
        return fallback or None

    def extract_image_url(self, html: str) -> Optional[str]:
        """Pull og:image (preferred) or first figure image URL from episode HTML."""
        soup = BeautifulSoup(html, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og.get("content")
        figure = soup.find("figure")
        if figure:
            img = figure.find("img")
            if img and img.get("src"):
                return img.get("src")
        return None

    def extract_media(self, episode_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (mp3_url, transcript_text, image_url) from an episode page."""
        resp = self.session.get(episode_url, timeout=20)
        # Force UTF-8 to avoid mojibake on accented characters
        resp.encoding = resp.apparent_encoding or "utf-8"
        resp.raise_for_status()
        html = resp.text
        mp3_match = self.MP3_REGEX.search(html)
        mp3_url = mp3_match.group(0) if mp3_match else None
        transcript = self.extract_transcript(html)
        image_url = self.extract_image_url(html)
        return mp3_url, transcript, image_url

    def safe_slug_from_url(self, url: str) -> str:
        """Make a filesystem-safe slug from the last path segment."""
        tail = url.rstrip("/").split("/")[-1]
        tail = unquote(tail)
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", tail).strip("-")
        return slug or "episode"

    def download_file(self, url: str, dest: pathlib.Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"[SKIP] {dest.name} (exists)")
            return
        with self.session.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        print(f"[SAVED] {dest.name}")

    def process_episode(self, date: datetime, episode_url: str, download: bool = True) -> pathlib.Path:
        """
        Scrapes and downloads episode data.
        Returns the path to the episode directory.
        """
        slug = self.safe_slug_from_url(episode_url)
        folder = config.DATA_DIR / f"{date.strftime('%Y-%m-%d')}-{slug}"
        folder.mkdir(parents=True, exist_ok=True)

        mp3_url, transcript, image_url = self.extract_media(episode_url)
        
        if not mp3_url:
            print(f"[WARN] No mp3 found for {episode_url}")
        else:
            if download:
                mp3_dest = folder / pathlib.Path(mp3_url).name
                self.download_file(mp3_url, mp3_dest)

        if not transcript:
            print(f"[WARN] No transcript found for {episode_url}")
        else:
            (folder / "transcript.txt").write_text(transcript, encoding="utf-8")

        if image_url and download:
            image_dest = folder / "image.jpg"
            try:
                self.download_file(image_url, image_dest)
            except requests.RequestException as err:
                print(f"[WARN] Failed to download image for {episode_url}: {err}")

        # Metadata file
        metadata = folder / "episode.txt"
        lines = [
            f"url: {episode_url}",
            f"mp3: {mp3_url or ''}",
            f"transcript: {'transcript.txt' if transcript else ''}",
            f"image: {image_url or ''}",
        ]
        metadata.write_text("\n".join(lines), encoding="utf-8")
        
        return folder
