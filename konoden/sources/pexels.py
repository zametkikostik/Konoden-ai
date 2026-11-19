from __future__ import annotations

import requests

from .base import Candidate, SourceError, SourceProvider


class PexelsProvider(SourceProvider):
    name = "pexels"
    API = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, *, min_width: int, limit: int = 10) -> list[Candidate]:
        r = requests.get(
            self.API,
            headers={"Authorization": self.api_key},
            params={"query": query, "per_page": limit, "orientation": "landscape"},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise SourceError(f"Pexels {r.status_code}: {r.text[:300]}")
        out: list[Candidate] = []
        for v in r.json().get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
            if not files:
                continue
            enough = [f for f in files if f["width"] >= min_width]
            f = min(enough, key=lambda x: x["width"]) if enough else max(files, key=lambda x: x["width"])
            out.append(
                Candidate(
                    provider=self.name,
                    id=str(v["id"]),
                    download_url=f["link"],
                    page_url=v.get("url", ""),
                    width=int(f["width"]),
                    height=int(f.get("height") or 0),
                    duration=float(v.get("duration") or 0),
                    author=(v.get("user") or {}).get("name", ""),
                )
            )
        return out
