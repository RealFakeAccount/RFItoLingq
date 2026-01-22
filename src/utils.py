import pathlib
from typing import List, Dict, Optional

def find_episodes(data_dir: pathlib.Path) -> List[pathlib.Path]:
    """Find all transcript.txt files in data directory."""
    episodes = []
    if not data_dir.exists():
        return []
    for dir_path in sorted(data_dir.iterdir()):
        if dir_path.is_dir():
            transcript = dir_path / "transcript.txt"
            episode_meta = dir_path / "episode.txt"
            if transcript.exists() and episode_meta.exists():
                episodes.append(dir_path)
    return episodes

def parse_episode_meta(episode_dir: pathlib.Path) -> Dict[str, str]:
    """Parse episode.txt to get url and mp3."""
    meta = {}
    episode_file = episode_dir / "episode.txt"
    if not episode_file.exists():
        return meta
    for line in episode_file.read_text(encoding="utf-8").split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta

def find_mp3(episode_dir: pathlib.Path) -> Optional[pathlib.Path]:
    """Find the MP3 file in episode directory."""
    for file in episode_dir.iterdir():
        if file.suffix.lower() == ".mp3":
            return file
    return None
