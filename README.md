# RFI Journal en français facile -> LingQ Automator

Automated tool to scrape "Journal en français facile" podcast from RFI and import lessons into LingQ.

## Features
- **Scraper**: Fetches latest episodes, transcripts, and audio from RFI website.
- **Uploader**: Creates lessons in LingQ, uploading text and MP3 audio.
- **Deduplication**: Checks LingQ course content to avoid uploading duplicate lessons.
- **CI/CD**: Includes GitHub Action for daily automated syncing.

## Setup

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` (if applicable) or set environment variables:
   - `LINGQ_API_TOKEN`: Your LingQ API v3 token.
   - `LINGQ_COURSE_ID`: The existing Course ID on LingQ where lessons should go (default behavior can be configured in `src/config.py`).

## Usage

The tool uses a unified entry point `main.py`.

### 1. Scrape only
Download episodes to local `data/` folder.
```bash
python main.py scrape --limit 5
```

### 2. Upload only
Upload local episodes to LingQ. Skips already uploaded lessons.
```bash
python main.py upload
```

### 3. Sync (Scrape + Upload)
Ideal for cron jobs.
```bash
python main.py sync --limit 5
```

## GitHub Actions
A workflow is provided in `.github/workflows/daily_sync.yml` to run the sync job daily at 20:00 UTC.
Ensure you add `LINGQ_API_TOKEN` to your repository Secrets and `LINGQ_COURSE_ID` to Variables (or code it in `src/config.py`).
