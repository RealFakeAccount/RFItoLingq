import argparse
import sys
import pathlib
from datetime import datetime
from typing import Optional, Dict

from src.config import config
from src.scraper import RFIScraper
from src.lingq_api import LingQAPI
from src.utils import find_episodes, parse_episode_meta, find_mp3

def cmd_scrape(args):
    """Handle scrape command."""
    print(f"[INFO] Scraping with limit={args.limit}, pages={args.pages}")
    scraper = RFIScraper()
    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print("[ERROR] --since must be YYYY-MM-DD")
            sys.exit(1)
            
    episodes = scraper.fetch_listing(limit=args.limit, since=since_date, pages=args.pages)
    print(f"[INFO] Found {len(episodes)} episodes")
    
    for date, url in episodes:
        print(f"Processing {date.date()} -> {url}")
        scraper.process_episode(date, url)

def upload_single_episode(api: LingQAPI, episode_dir: pathlib.Path, existing_lessons: Dict[str, int]) -> bool:
    """Uploads a single episode directory to LingQ."""
    print(f"[PROCESS] {episode_dir.name}")
    transcript_file = episode_dir / "transcript.txt"
    if not transcript_file.exists():
        print(f"  [SKIP] No transcript.txt found")
        return False
    
    meta = parse_episode_meta(episode_dir)
    original_url = meta.get("url", "")
    text = transcript_file.read_text(encoding="utf-8").strip()
    
    # Title logic: "Journal en français facile YYYY-MM-DD"
    # Extract date from folder name: YYYY-MM-DD-slug
    date_part = episode_dir.name[:10]
    title = f"Journal en français facile {date_part}"
    
    if title in existing_lessons:
        print(f"  [SKIP] Lesson '{title}' already exists (ID: {existing_lessons[title]})")
        return True

    mp3_file = find_mp3(episode_dir)
    image_file = episode_dir / "image.jpg"
    if not image_file.exists():
        image_file = None
        
    status = "shared" if (mp3_file and image_file) else "private"
    
    # Dynamic tags
    year = date_part[:4]
    
    try:
        # Defaults are appended inside create_lesson now
        lesson = api.create_lesson(
            lang=config.LINGQ_LANGUAGE_CODE,
            title=title,
            text=text,
            collection_pk=config.LINGQ_COURSE_ID,
            status=status,
            level=3,
            tags=[year], 
            original_url=original_url,
            audio_file=mp3_file,
            external_audio=None,
            duration=None,
            image_file=image_file
        )
        
        lesson_id = lesson.get("id")
        print(f"  [SUCCESS] Lesson created: ID {lesson_id} ({status})")
        
        # Post-processing
        if lesson_id:
            # Prepare full list for update if needed (API often replaces)
            all_tags = list(set(config.LINGQ_DEFAULT_TAGS + [year]))
            
            api.update_lesson_metadata(
                config.LINGQ_LANGUAGE_CODE, 
                lesson_id, 
                shelves=config.LINGQ_DEFAULT_SHELVES, 
                tags=all_tags
            )
            if mp3_file:
                api.generate_audio_timestamps(config.LINGQ_LANGUAGE_CODE, lesson_id)
        return True
        
    except Exception as e:
        print(f"  [ERROR] Upload failed: {e}")
        return False

def cmd_upload(args):
    """Handle upload command."""
    api = LingQAPI() # Will raise if token missing
    
    all_episodes = find_episodes(config.DATA_DIR)
    
    # Filter if specific date requested
    if args.date:
        targets = [e for e in all_episodes if e.name.startswith(args.date)]
        if not targets:
            print(f"[WARN] No episodes found starting with {args.date}")
            return
    else:
        targets = all_episodes

    # Limit
    if args.limit:
        targets = targets[:args.limit]
        
    print(f"[INFO] Found {len(targets)} episodes to upload")
    
    # Check duplicates
    existing = api.get_collection_lessons(config.LINGQ_LANGUAGE_CODE, config.LINGQ_COURSE_ID)
    print(f"[INFO] Course has {len(existing)} existing lessons")

    success_count = 0
    for ep in targets:
        if upload_single_episode(api, ep, existing):
            success_count += 1
            
    print(f"[DONE] Uploaded {success_count}/{len(targets)}")

def cmd_sync(args):
    """Scrape then upload only today's/recent content."""
    # 1. Scrape
    print(">>> STEP 1: SCRAPING")
    cmd_scrape(args)
    
    # 2. Upload
    # Sync implies we want to upload what we just scraped or everything?
    # Usually a daily job wants to upload everything that isn't uploaded?
    # Simplest: Upload everything found (or limit to recent).
    print("\n>>> STEP 2: UPLOADING")
    # We pass args to upload, but we might want to override limit?
    # Let's just run upload for all.
    cmd_upload(args)

def main():
    parser = argparse.ArgumentParser(description="RFI to LingQ Automator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape episodes from RFI")
    p_scrape.add_argument("--limit", type=int, default=5, help="Max episodes to scrape")
    p_scrape.add_argument("--pages", type=int, default=3, help="Pagination depth")
    p_scrape.add_argument("--since", type=str, help="YYYY-MM-DD")
    
    # Upload
    p_upload = subparsers.add_parser("upload", help="Upload episodes to LingQ")
    p_upload.add_argument("--date", type=str, help="Specific date YYYY-MM-DD")
    p_upload.add_argument("--limit", type=int, default=0, help="Max to upload (0=all)")
    
    # Sync (Scrape + Upload)
    p_sync = subparsers.add_parser("sync", help="Scrape and Upload")
    p_sync.add_argument("--limit", type=int, default=5, help="Max episodes to scrape/upload")
    p_sync.add_argument("--pages", type=int, default=3)
    p_sync.add_argument("--since", type=str)
    p_sync.add_argument("--date", type=str, help="Filter upload date")

    args = parser.parse_args()
    
    # Validate config
    try:
        config.validate()
        # Create data dir
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # For verify-only runs (like CI building), strict token might block.
        # But here we need it.
        if args.command in ["upload", "sync"]:
            print(f"[FATAL] {e}")
            sys.exit(1)
        # Scrape theoretically doesn't need token, but config.validate checks it.
        # Let's make it soft warning if only scraping?
        if args.command == "scrape" and "LINGQ_API_TOKEN" in str(e):
             print(f"[WARN] {e} - Scraping allowed, but upload will fail.")
        else:
            print(f"[FATAL] {e}")
            sys.exit(1)

    if args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "upload":
        cmd_upload(args)
    elif args.command == "sync":
        cmd_sync(args)

if __name__ == "__main__":
    main()
