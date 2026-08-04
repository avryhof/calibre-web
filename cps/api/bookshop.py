# -*- coding: utf-8 -*-

#  Book shop search endpoint.
#  Queries the configured bookshop providers concurrently and returns a unified
#  result list. The endpoint requires a valid Calibre-Web login session (the
#  same cookie used by the web UI) and is rate limited per client IP.

import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.requests import Request

from . import api
from .. import logger, ub
from ..services.Bookshop import get_providers

log = logger.create()

router = APIRouter(prefix="/bookshop", tags=["bookshop"])

# ---------------------------------------------------------------------------
# Authentication: validate the Flask login session cookie
# ---------------------------------------------------------------------------


def _open_flask_session(request: Request):
    from .. import app as flask_app

    jar = SimpleCookie()
    jar.load(request.headers.get("cookie", ""))
    cookies = {key: morsel.value for key, morsel in jar.items()}
    cookie_shim = type("_CookieShim", (), {"cookies": cookies})()
    try:
        return flask_app.session_interface.open_session(flask_app, cookie_shim)
    except Exception as e:
        log.warning("Could not decode session cookie for API request: %s", e)
        return None


def require_user(request: Request):
    session = _open_flask_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = session.get("_user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = ub.session.get(ub.User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Lightweight in-memory rate limiter (per client IP)
# ---------------------------------------------------------------------------

_rate_window = defaultdict(deque)
RATE_LIMIT = 60
RATE_PERIOD = 60.0


def rate_limit(request: Request):
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _rate_window[key]
    while window and window[0] <= now - RATE_PERIOD:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests")
    window.append(now)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class BookshopSource(BaseModel):
    id: str
    name: str
    description: str
    homepage: str


class BookshopItem(BaseModel):
    id: str
    title: str
    authors: List[str] = []
    url: str = ""
    source: BookshopSource
    cover: str = ""
    description: str = ""
    formats: Dict[str, str] = {}
    languages: List[str] = []
    tags: List[str] = []


class BookshopResponse(BaseModel):
    query: str
    providers: List[str]
    results: List[BookshopItem]


@api.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@router.get("/search", response_model=BookshopResponse)
def search(
    q: str = Query(..., min_length=1, max_length=120, description="Search terms"),
    providers: str = Query(
        "",
        description="Comma-separated provider ids; empty selects all active providers",
    ),
    limit: int = Query(12, ge=1, le=30),
    request: Request = None,
    user=Depends(require_user),
):
    # `user` is required so the auth dependency runs; its value is intentionally unused.
    rate_limit(request)
    requested = {p.strip() for p in providers.split(",") if p.strip()} if providers else set()
    selected = [
        provider for provider in get_providers()
        if not requested or provider.__id__ in requested
    ]
    if not selected:
        return BookshopResponse(query=q, providers=[], results=[])
    per_provider = max(1, limit // len(selected))
    gathered = []

    def _run(provider):
        return provider, provider.search(q, limit=per_provider) or []

    # Every provider runs concurrently, and each is wall-clock bounded so a
    # hung upstream (e.g. DNS or a half-open connection that ignores the
    # requests timeout) can never stall the whole search.
    search_timeout = 10.0
    executor = ThreadPoolExecutor(max_workers=len(selected))
    try:
        futures = {executor.submit(_run, provider): provider for provider in selected}
        for future, provider in futures.items():
            try:
                provider_, items = future.result(timeout=search_timeout)
                gathered.append((provider_, items))
            except TimeoutError:
                log.warning("Book shop provider %s timed out after %.0fs", provider.__id__, search_timeout)
            except Exception as e:
                log.warning("Book shop provider %s failed: %s", provider.__id__, e)
    finally:
        executor.shutdown(wait=False)

    gathered.sort(key=lambda pair: pair[0].__id__)
    merged = []
    for _, items in gathered:
        for item in items:
            if len(merged) >= limit:
                break
            merged.append(item)
        if len(merged) >= limit:
            break

    return BookshopResponse(
        query=q,
        providers=[p.__id__ for p, _ in gathered],
        results=[BookshopItem(**item.to_dict()) for item in merged],
    )


api.include_router(router)
