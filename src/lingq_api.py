import pathlib
import requests
from typing import Optional, List, Any, Dict

from .config import config

class LingQAPI:
    def __init__(self, token: Optional[str] = None):
        self.token = token or config.LINGQ_API_TOKEN
        if not self.token:
            raise ValueError("API Token required for LingQAPI")
        self.headers = {"Authorization": f"Token {self.token}"}

    def _normalize_collection_list(self, payload: Any) -> List[dict]:
        """Normalize v3 response which has 'data' array directly."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and "data" in payload:
            return payload.get("data", []) or []
        if isinstance(payload, dict) and "results" in payload:
            return payload.get("results", []) or []
        return []

    def get_collection_lessons(self, lang: str, collection_pk: int) -> Dict[str, int]:
        """
        Returns a dictionary {title: lesson_id} of all lessons in the course.
        Handles pagination.
        """
        url = f"{config.LINGQ_API_ROOT}/{lang}/collections/{collection_pk}/lessons/"
        mapping = {}
        page = 1
        while True:
            try:
                # API parameter for page is often `page`.
                resp = requests.get(url, headers=self.headers, params={"page": page, "page_size": 50}, timeout=30)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.json()
                results = self._normalize_collection_list(data)
                if not results:
                    break
                
                for lesson in results:
                    title = lesson.get("title")
                    pk = lesson.get("id") or lesson.get("pk")
                    if title and pk:
                        mapping[title] = pk
                
                if not data.get("next"):
                    break
                page += 1
            except Exception as e:
                print(f"[WARN] Error fetching lesson list page {page}: {e}")
                break
        return mapping

    def list_collections(self, lang: str) -> List[dict]:
        url = f"{config.LINGQ_API_ROOT}/{lang}/collections/"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return self._normalize_collection_list(resp.json())

    def find_collection_pk(self, title: str, lang: str) -> Optional[int]:
        for item in self.list_collections(lang):
            if isinstance(item, dict) and item.get("title") == title:
                return item.get("pk")
        return None

    def create_collection(self, title: str, lang: str, status: str = "private", level: int = 3, description: str = "") -> int:
        url = f"{config.LINGQ_API_ROOT}/{lang}/collections/"
        payload = {
            "title": title,
            "status": status,
            "level": level,
            "description": description,
        }
        resp = requests.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pk = data.get("id")
        print(f"[INFO] Created course '{title}' with id={pk}")
        return pk

    def ensure_collection(self, title: str, lang: str, status: str = "shared", level: int = 3) -> int:
        existing = self.find_collection_pk(title, lang)
        if existing:
            return existing
        return self.create_collection(title, lang, status=status, level=level, description="Auto-imported course")

    def generate_audio_timestamps(self, lang: str, lesson_id: int) -> bool:
        """Trigger audio timestamp generation for a lesson."""
        url = f"{config.LINGQ_API_ROOT}/{lang}/lessons/{lesson_id}/genaudio/"
        try:
            resp = requests.post(url, headers=self.headers, timeout=60)
            resp.raise_for_status()
            print(f"[INFO] Generated timestamps for lesson {lesson_id}")
            return True
        except requests.HTTPError as e:
            if resp.status_code == 409:
                print(f"[INFO] Timestamps already exist/in-progress for lesson {lesson_id}")
                return True
            print(f"[WARN] Failed to generate timestamps: {e}")
            return False

    def update_lesson_metadata(self, lang: str, lesson_id: int, shelves: List[str], tags: List[str]) -> bool:
        url = f"{config.LINGQ_API_ROOT}/{lang}/lessons/{lesson_id}/"
        payload = {
            "shelves": shelves,
            "tags": tags,
        }
        try:
            resp = requests.patch(
                url,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            print(f"[INFO] Updated metadata (tags={tags}) for lesson {lesson_id}")
            return True
        except Exception as e:
            print(f"[WARN] Failed to update metadata: {e}")
            return False

    def create_lesson(
        self,
        lang: str,
        title: str,
        text: str,
        collection_pk: Optional[int],
        status: str,
        level: Optional[int],
        tags: List[str],
        original_url: Optional[str],
        audio_file: Optional[pathlib.Path],
        external_audio: Optional[str],
        duration: Optional[int],
        image_file: Optional[pathlib.Path] = None,
    ) -> dict:
        url = f"{config.LINGQ_API_ROOT}/{lang}/lessons/"
        files = {}
        data: List[tuple] = [
            ("title", title),
            ("text", text),
            ("status", status),
            ("accent", "france_french"),
            ("language", lang),
        ]
        
        for shelf in config.LINGQ_DEFAULT_SHELVES:
            data.append(("shelves[]", shelf))
        
        if collection_pk:
            data.append(("collection", str(collection_pk)))
        if level is not None:
            data.append(("level", str(level)))
            
        for tag in tags:
            data.append(("tags[]", tag))
            
        # Ensure default tags
        for default_tag in config.LINGQ_DEFAULT_TAGS:
             # We can add duplicates if the API allows it, or check. 
             # Simpler to just check if it was already in 'tags'.
             if default_tag not in tags:
                 data.append(("tags[]", default_tag))

        if original_url:
            data.append(("original_url", original_url))
        if duration:
            data.append(("duration", str(duration)))

        if audio_file:
            files["audio"] = (audio_file.name, open(audio_file, "rb"), "audio/mpeg")
        elif external_audio:
            data.append(("external_audio", external_audio))
            
        if image_file:
            files["image"] = (image_file.name, open(image_file, "rb"), "image/jpeg")

        try:
            resp = requests.post(url, headers=self.headers, data=data, files=files or None, timeout=120)
            if resp.status_code >= 400:
                print(f"[ERROR] API {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()
        finally:
            # Files opened in create_lesson are closed by GC or context manager if we used one, 
            # strictly speaking we should close them but requests usually handles file objects fine.
            for file_obj in files.values():
                file_obj[1].close()

