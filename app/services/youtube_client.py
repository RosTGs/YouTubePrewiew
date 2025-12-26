from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import httpx


@dataclass
class ThumbnailInfo:
    video_id: str
    title: str
    description: str
    thumbnail_url: str
    ctr_score: float


class YouTubeClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"

    async def fetch_thumbnails(self, channel_url: str) -> List[ThumbnailInfo]:
        channel_id = await self._resolve_channel_identifier(channel_url)
        if not channel_id:
            raise ValueError(
                "Не удалось определить ID канала. Укажите ссылку формата https://www.youtube.com/channel/<ID> или @username."
            )

        uploads_playlist = await self._get_uploads_playlist(channel_id)
        videos = await self._get_latest_videos(uploads_playlist)
        return [self._build_thumbnail_info(item) for item in videos]

    async def fetch_single_thumbnail(self, video_id: str) -> Optional[ThumbnailInfo]:
        if not self.api_key:
            return None

        url = f"{self.base_url}/videos"
        params = {"part": "snippet,statistics", "id": video_id, "key": self.api_key}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        items = data.get("items", [])
        if not items:
            return None
        return self._build_thumbnail_info(items[0])

    async def _resolve_channel_identifier(self, value: str) -> Optional[str]:
        channel_id = self._extract_channel_id(value)
        if channel_id:
            return channel_id

        handle = self._extract_handle(value)
        if handle:
            if not self.api_key:
                raise ValueError("Поиск по @username требует установленного YOUTUBE_API_KEY.")
            return await self._fetch_channel_id_by_handle(handle)

        return None

    def _extract_channel_id(self, url: str) -> Optional[str]:
        # Supports https://www.youtube.com/channel/<id> or direct channel id.
        match = re.search(r"(UC[\w-]{22})", url)
        if match:
            return match.group(1)
        if url.startswith("UC") and len(url) >= 24:
            return url
        return None

    def _extract_handle(self, value: str) -> Optional[str]:
        match = re.search(r"@([A-Za-z0-9._-]+)", value)
        if match:
            return match.group(1)
        if value.startswith("@"):  # fallback if regex failed but value clearly a handle
            return value.lstrip("@")
        return None

    async def _fetch_channel_id_by_handle(self, handle: str) -> Optional[str]:
        url = f"{self.base_url}/search"
        params = {
            "part": "snippet",
            "type": "channel",
            "q": f"@{handle}",
            "maxResults": 1,
            "key": self.api_key,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

        items = data.get("items", [])
        if not items:
            return None
        return items[0].get("id", {}).get("channelId")

    async def _get_uploads_playlist(self, channel_id: str) -> str:
        if not self.api_key:
            raise ValueError("Не задан YOUTUBE_API_KEY, YouTube Data API недоступен.")

        url = f"{self.base_url}/channels"
        params = {"part": "contentDetails", "id": channel_id, "key": self.api_key}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        items = data.get("items", [])
        if not items:
            raise ValueError("Канал не найден или недоступен.")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    async def _get_latest_videos(self, playlist_id: str, max_results: int = 12):
        url = f"{self.base_url}/playlistItems"
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": max_results,
            "key": self.api_key,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            playlist_data = response.json()

        video_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist_data.get("items", [])]
        if not video_ids:
            return []

        stats_url = f"{self.base_url}/videos"
        stats_params = {
            "part": "snippet,statistics",
            "id": ",".join(video_ids),
            "key": self.api_key,
        }
        async with httpx.AsyncClient() as client:
            stats_response = await client.get(stats_url, params=stats_params, timeout=10)
            stats_response.raise_for_status()
            stats_data = stats_response.json()

        return stats_data.get("items", [])

    def _build_thumbnail_info(self, item: dict) -> ThumbnailInfo:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})
        best_thumb = thumbnails.get("maxres") or thumbnails.get("standard") or thumbnails.get("high") or thumbnails.get("default")
        thumb_url = best_thumb.get("url") if best_thumb else ""

        views = float(stats.get("viewCount", 0))
        likes = float(stats.get("likeCount", 0))
        comments = float(stats.get("commentCount", 0))
        ctr_score = round(min(100, (likes + comments * 0.5) / max(views, 1) * 1200), 2)

        return ThumbnailInfo(
            video_id=item.get("id"),
            title=snippet.get("title", "Без названия"),
            description=snippet.get("description", ""),
            thumbnail_url=thumb_url,
            ctr_score=ctr_score,
        )
