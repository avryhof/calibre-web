# -*- coding: utf-8 -*-

#  Book shop search endpoint.
#  Queries the configured bookshop providers concurrently and returns a unified
#  result list. The endpoint requires a valid Calibre-Web login session (the
#  same cookie used by the web UI) and is rate limited per client IP.

import os
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from typing import Dict, List
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from starlette.requests import Request

from . import api
from .. import logger, ub
from ..file_helper import get_temp_dir
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
_rate_window_add = defaultdict(deque)
RATE_LIMIT = 60
RATE_LIMIT_ADD = 10
RATE_PERIOD = 60.0


def rate_limit(request: Request, window=None, limit=RATE_LIMIT):
    if window is None:
        window = _rate_window
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    limit_window = window[key]
    while limit_window and limit_window[0] <= now - RATE_PERIOD:
        limit_window.popleft()
    if len(limit_window) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests")
    limit_window.append(now)


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
    search_type: str = Query("title", pattern="^(title|author)$",
                             description="Search against title or author"),
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
        return provider, provider.search(q, limit=per_provider, search_type=search_type) or []

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


# ---------------------------------------------------------------------------
# Add-to-library: import a free/public-domain ebook from a provider download.
# The download URL is re-validated against the provider's host allowlist
# (SSRF), the format against the upload whitelist, and the caller against the
# upload role. The file is saved to the temp dir and imported through the same
# uploader/create_book_on_upload path used by the regular upload form.
# ---------------------------------------------------------------------------

# Format label -> file extension for the download formats the providers expose.
FORMAT_EXTENSIONS = {
    "EPUB": ".epub",
    "KEPUB": ".kepub",
    "PDF": ".pdf",
    "MOBI": ".mobi",
    "AZW3": ".azw3",
    "TXT": ".txt",
    "HTML": ".html",
    "DJVU": ".djvu",
}
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
DOWNLOAD_TIMEOUT = (10, 120)


class AddBookRequest(BaseModel):
    provider: str = ""
    format: str = ""
    url: str = ""
    title: str = ""
    authors: List[str] = []
    description: str = ""


class AddBookResponse(BaseModel):
    book_id: int
    title: str
    url: str
    message: str


def _find_provider(provider_id):
    for provider in get_providers():
        if provider.__id__ == provider_id:
            return provider
    return None


def _host_allowed(url: str, hosts) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and parsed.netloc in hosts


@router.post("/add", response_model=AddBookResponse)
def add_book(
    payload: AddBookRequest,
    request: Request = None,
    user=Depends(require_user),
):
    rate_limit(request, _rate_window_add, RATE_LIMIT_ADD)
    from .. import calibre_db, config, helper, uploader
    from ..binary_helper import SUPPORTED_UNRAR_BINARIES, resolve_binary_path
    from ..editbooks import create_book_on_upload, edit_book_comments, move_coverfile

    from markupsafe import Markup

    if not (config.config_uploading and user.role_upload()):
        raise HTTPException(status_code=403, detail="Upload permission required")
    provider = _find_provider(payload.provider)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if payload.format not in FORMAT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported format")
    extension = FORMAT_EXTENSIONS[payload.format]
    allowed_extensions = [e.strip().lower() for e in config.config_upload_formats.split(",")]
    if extension.lstrip(".").lower() not in allowed_extensions and "" not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Format not allowed for upload")
    if not _host_allowed(payload.url, provider.DOWNLOAD_HOSTS):
        raise HTTPException(status_code=400, detail="Download URL not allowed")

    tmp_path = os.path.join(get_temp_dir(), uuid.uuid4().hex + extension)
    downloaded_size = 0
    try:
        with requests.get(
            payload.url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers=getattr(provider, "HEADERS", None),
            allow_redirects=True,
        ) as resp:
            # Reject off-allowlist redirect targets as well.
            if resp.url and not _host_allowed(resp.url, provider.DOWNLOAD_HOSTS):
                log.warning("Book shop add rejected redirect to %s", urlparse(resp.url).netloc)
                raise HTTPException(status_code=400, detail="Download redirected to disallowed host")
            resp.raise_for_status()
            with open(tmp_path, "wb") as out:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    downloaded_size += len(chunk)
                    if downloaded_size > MAX_DOWNLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Download too large")
                    out.write(chunk)
    except HTTPException:
        raise
    except requests.RequestException as e:
        log.warning("Book shop add download failed for %s: %s", payload.provider, e)
        raise HTTPException(status_code=502, detail="Could not download the book file")
    except Exception as e:
        log.warning("Book shop add download error for %s: %s", payload.provider, e)
        raise HTTPException(status_code=502, detail="Could not download the book file")

    # The import chain runs against the Calibre-Web Flask stack (calibre_db
    # uses flask.g, uploader translates via flask_babel, and edit_book_comments
    # may flash). FastAPI runs outside the Flask request handling, so push an
    # app + request context for the library work; calibre_db's teardown closes
    # the per-request library connection when the context pops.
    from .. import app as flask_app

    try:
        with flask_app.test_request_context():
            try:
                calibre_db.create_functions(config)
                rar_executable = resolve_binary_path(config.config_rarfile_location,
                                                     SUPPORTED_UNRAR_BINARIES)
                file_stem = os.path.splitext(os.path.basename(urlparse(payload.url).path))[0]
                meta = uploader.process(tmp_path, file_stem or "ebook", extension, rar_executable)

                # Fall back to the catalog metadata when the file carries none
                # (uploader returns the filename/Unknown defaults in that case).
                catalog_title = payload.title.strip()
                catalog_authors = " & ".join(a for a in payload.authors if a.strip())
                if catalog_title and meta.title.lower() == (file_stem or "").lower():
                    meta = meta._replace(title=catalog_title)
                if catalog_authors and meta.author.lower() in ("unknown", ""):
                    meta = meta._replace(author=catalog_authors)
                if payload.description.strip() and not meta.description:
                    meta = meta._replace(description=payload.description.strip())

                modify_date = False
                db_book, input_authors, title_dir = create_book_on_upload(modify_date, meta)
                modify_date |= edit_book_comments(Markup(meta.description).unescape(), db_book)

                book_id = db_book.id
                title = db_book.title
                error = None
                if config.config_use_google_drive:
                    from .. import gdriveutils

                    helper.upload_new_file_gdrive(book_id,
                                                  input_authors[0],
                                                  title,
                                                  title_dir,
                                                  meta.file_path,
                                                  meta.extension.lower())
                    for file_format in db_book.data:
                        file_format.name = (helper.get_valid_filename(title, chars=42) + " - "
                                            + helper.get_valid_filename(input_authors[0], chars=42))
                else:
                    error = helper.update_dir_structure(book_id,
                                                        config.get_book_path(),
                                                        input_authors[0],
                                                        meta.file_path,
                                                        title_dir + meta.extension.lower())
                move_coverfile(meta, db_book)
                if modify_date:
                    calibre_db.set_metadata_dirty(book_id)
                calibre_db.session.commit()
                helper.add_book_to_thumbnail_cache(book_id)
                if error:
                    log.warning("Book shop add: %s", error)
            except (HTTPException, IntegrityError, OperationalError, StaleDataError) as e:
                calibre_db.session.rollback()
                log.error_or_exception("Book shop add database error: %s", e)
                raise HTTPException(status_code=500, detail="Could not add the book to the library")
            except Exception as e:
                calibre_db.session.rollback()
                log.warning("Book shop add failed for %s: %s", payload.provider, e)
                raise HTTPException(status_code=500, detail="Could not add the book to the library")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    log.info("Book shop add: user %s added '%s' (book id %s) from %s",
             getattr(user, "name", "?"), title, book_id, payload.provider)
    return AddBookResponse(book_id=book_id, title=title, url="/book/{}".format(book_id),
                           message="Book added to the library")


api.include_router(router)
