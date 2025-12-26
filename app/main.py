import os
from typing import List

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .services.gemini_client import GeminiClient, GeminiResult
from .services.youtube_client import ThumbnailInfo, YouTubeClient


def get_youtube_client() -> YouTubeClient:
    api_key = os.getenv("YOUTUBE_API_KEY")
    return YouTubeClient(api_key=api_key)


def get_gemini_client() -> GeminiClient:
    api_key = os.getenv("GEMINI_API_KEY")
    return GeminiClient(api_key=api_key)


app = FastAPI(title="YouTube Thumbnail Assistant")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "thumbnails": None})


@app.post("/channel", response_class=HTMLResponse)
async def fetch_channel(
    request: Request,
    channel_url: str = Form(...),
    yt_client: YouTubeClient = Depends(get_youtube_client),
):
    try:
        thumbnails = await yt_client.fetch_thumbnails(channel_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Ошибка при обращении к YouTube API") from exc

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "thumbnails": thumbnails, "channel_url": channel_url},
    )


@app.post("/regenerate/{video_id}")
async def regenerate_thumbnail(
    request: Request,
    video_id: str,
    title: str = Form(...),
    description: str = Form(""),
    yt_client: YouTubeClient = Depends(get_youtube_client),
    gemini_client: GeminiClient = Depends(get_gemini_client),
):
    # Attempt to fetch existing thumbnail for additional context.
    original = await yt_client.fetch_single_thumbnail(video_id)

    gemini_result: GeminiResult = await gemini_client.propose_new_thumbnail(
        title=title,
        description=description,
        original_thumbnail=original.thumbnail_url if original else None,
    )

    # Optimistic redirect back to channel view with a flash-like message.
    thumbnails: List[ThumbnailInfo] = []
    if "channel_url" in request.query_params:
        try:
            thumbnails = await yt_client.fetch_thumbnails(request.query_params["channel_url"])
        except Exception:
            pass

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "thumbnails": thumbnails or None,
            "regenerated_for": video_id,
            "gemini_result": gemini_result,
            "channel_url": request.query_params.get("channel_url"),
        },
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
