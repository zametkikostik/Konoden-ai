from __future__ import annotations

import requests

from .base import Candidate, SourceError, SourceProvider

_SIZES = ("large", "medium", "small", "tiny")


class PixabayProvider(SourceProvider):
    name = "pixabay"
    API = "https://pixabay.com/api/videos/"

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, *, min_width: int, limit: int = 10) -> list[Candidate]:
        r = requests.get(
            self.API,
            params={"key": self.api_key, "q": query[:100], "per_page": max(3, limit)},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise SourceError(f"Pixabay {r.status_code}: {r.text[:300]}")
        out: list[Candidate] = []
        for h in r.json().get("hits", []):
            files = [h["videos"][k] for k in _SIZES if (h.get("videos") or {}).get(k, {}).get("url")]
            if not files:
                continue
            enough = [f for f in files if f.get("width", 0) >= min_width]
            f = min(enough, key=lambda x: x["width"]) if enough else max(files, key=lambda x: x.get("width", 0))
            out.append(
                Candidate(
                    provider=self.name,
                    id=str(h["id"]),
                    download_url=f["url"],
                    page_url=h.get("pageURL", ""),
                    width=int(f.get("width") or 0),
                    height=int(f.get("height") or 0),
                    duration=float(h.get("duration") or 0),
                    author=h.get("user", ""),
                )
            )
        return out
