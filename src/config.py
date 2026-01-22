import os
import pathlib
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # LingQ Settings
    LINGQ_API_TOKEN: Optional[str] = os.getenv("LINGQ_API_TOKEN")
    LINGQ_API_ROOT: str = "https://www.lingq.com/api/v3"
    LINGQ_LANGUAGE_CODE: str = "fr"
    # Default Course: "Journal en français facile 2026"
    # Use 'or' to handle both None (missing) and "" (empty string)
    LINGQ_COURSE_ID: int = int(os.getenv("LINGQ_COURSE_ID") or "2570591")
    
    # Default Lesson Settings
    LINGQ_DEFAULT_TAGS: List[str] = None
    LINGQ_DEFAULT_SHELVES: List[str] = None

    def __post_init__(self):
        if self.LINGQ_DEFAULT_TAGS is None:
            self.LINGQ_DEFAULT_TAGS = ["news", "rfi", "JFF"]
        if self.LINGQ_DEFAULT_SHELVES is None:
             self.LINGQ_DEFAULT_SHELVES = ["news"]

    # Scraper Settings
    RFI_BASE_URL: str = "https://francaisfacile.rfi.fr/fr/podcasts/journal-en-fran%C3%A7ais-facile/"
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

    # Paths
    BASE_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent
    DATA_DIR: pathlib.Path = BASE_DIR / "data"

    def validate(self):
        if not self.LINGQ_API_TOKEN:
            raise ValueError("LINGQ_API_TOKEN environment variable is not set.")

config = Config()
