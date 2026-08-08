# -*- coding: utf-8 -*-

#  Sync API for the Calibre desktop plugin.
#
#  Endpoints are mounted under /api/sync and authenticated with an X-API-Key
#  header. Keys are managed by an admin in the Settings page and map to a
#  regular Calibre-Web user, so write/download/delete permissions follow the
#  owning user's roles.
#
#  The plugin and this API exchange Calibre book UUIDs, which are stable on
#  both sides, plus full standard metadata (title, authors, series, tags,
#  publisher, pubdate, rating, language, comments, identifiers) and the book
#  files and covers.

import json
import glob
import mimetypes
import os
import shutil
import uuid as uuid_module
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from starlette.requests import Request
from starlette.responses import Response

from . import api
from .. import calibre_db, config, logger, ub
from .. import db
from .. import helper
from ..constants import STABLE_VERSION, PHYSICAL_FORMAT
from ..editbooks import (
    edit_book_comments, edit_book_languages, edit_book_publisher, edit_book_ratings,
    edit_book_series, edit_book_series_index, edit_book_tags, handle_author_on_edit,
    handle_title_on_edit, modify_identifiers,
)
from ..file_helper import get_temp_dir

log = logger.create()

router = APIRouter(prefix="/sync", tags=["sync"])

API_VERSION = 1
MAX_FILE_BYTES = 1024 * 1024 * 1024  # 1 GiB per uploaded file
MAX_LIST_LIMIT = 1000
DEFAULT_LIST_LIMIT = 200


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def require_api_key(request: Request = None):
    raw_key = (request.headers.get("X-API-Key") or "").strip()
    user = ub.verify_api_key(raw_key) if raw_key else None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return user


def require_write_user(user=Depends(require_api_key)):
    if not (config.config_uploading and user.role_upload()):
        raise HTTPException(status_code=403, detail="Upload permission required")
    return user


def require_delete_user(user=Depends(require_api_key)):
    if not (config.config_uploading and user.role_delete_books()):
        raise HTTPException(status_code=403, detail="Delete permission required")
    return user


def require_download_user(user=Depends(require_api_key)):
    if not user.role_download():
        raise HTTPException(status_code=403, detail="Download permission required")
    return user


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SyncStatus(BaseModel):
    api_version: int
    app: str
    version: str
    library_books: int
    server_time: str


class SyncBook(BaseModel):
    id: int
    uuid: str = ""
    title: str
    title_sort: str = ""
    author_sort: str = ""
    authors: List[str] = []
    series: str = ""
    series_index: str = "1.0"
    publisher: str = ""
    pubdate: str = ""
    rating: float = 0.0
    languages: List[str] = []
    comments: str = ""
    tags: List[str] = []
    identifiers: dict = {}
    formats: List[str] = []
    has_cover: bool = False
    last_modified: str = ""
    timestamp: str = ""


class SyncBookList(BaseModel):
    total: int
    offset: int
    limit: int
    books: List[SyncBook]


class SyncWriteResult(BaseModel):
    book_id: int
    uuid: str
    matched: bool
    message: str


class ContentServerReport(BaseModel):
    url: str = ""
    online: bool = False
    library_name: str = ""


class ContentServerStatusOut(BaseModel):
    url: str = ""
    online: bool = False
    library_name: str = ""
    last_seen: str = ""
    last_reported_by: str = ""


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _fmt(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _book_to_dict(book) -> dict:
    authors = [a.name for a in book.authors]
    tags = [t.name for t in book.tags]
    identifiers = {i.type: i.val for i in book.identifiers}
    languages = [l.lang_code for l in book.languages]
    series = book.series[0].name if book.series else ""
    publishers = [p.name for p in book.publishers]
    publisher = publishers[0] if publishers else ""
    rating = (book.ratings[0].rating / 2.0) if book.ratings else 0.0
    comments = book.comments[0].text if book.comments else ""
    formats = [d.format for d in book.data if d.format != PHYSICAL_FORMAT]
    return {
        "id": book.id,
        "uuid": book.uuid or "",
        "title": book.title or "",
        "title_sort": book.sort or "",
        "author_sort": book.author_sort or "",
        "authors": authors,
        "series": series,
        "series_index": str(book.series_index or "1.0"),
        "publisher": publisher,
        "pubdate": _fmt(book.pubdate),
        "rating": rating,
        "languages": languages,
        "comments": comments,
        "tags": tags,
        "identifiers": identifiers,
        "formats": formats,
        "has_cover": bool(book.has_cover),
        "last_modified": _fmt(book.last_modified),
        "timestamp": _fmt(book.timestamp),
    }


def _find_book_by_uuid(book_uuid):
    if not book_uuid:
        return None
    return calibre_db.session.query(db.Books).filter(db.Books.uuid == book_uuid).first()


def _find_book_by_identifiers(identifiers):
    isbn = (identifiers.get("isbn") or "").strip().lower()
    if not isbn:
        return None
    return (calibre_db.session.query(db.Books)
            .join(db.Identifiers)
            .filter(db.Identifiers.type == "isbn", db.Identifiers.val == isbn)
            .first())


def _allowed_format(extension) -> bool:
    fmt = extension.lower().lstrip(".")
    allowed = [e.strip().lower() for e in config.config_upload_formats.split(",")]
    return fmt in allowed or "" in allowed


def _app_context():
    from .. import app as flask_app
    return flask_app.app_context()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=SyncStatus)
def status(user=Depends(require_api_key)):
    with _app_context():
        book_count = calibre_db.session.query(db.Books).count()
    return {
        "api_version": API_VERSION,
        "app": "Calibre-Web",
        "version": STABLE_VERSION,
        "library_books": book_count,
        "server_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.get("/content-server", response_model=ContentServerStatusOut)
def get_content_server(user=Depends(require_api_key)):
    with _app_context():
        row = ub.get_content_server_status()
    return {
        "url": row.url or "",
        "online": bool(row.online),
        "library_name": row.library_name or "",
        "last_seen": _fmt(row.last_seen),
        "last_reported_by": row.last_reported_by or "",
    }


@router.post("/content-server", response_model=ContentServerStatusOut)
def report_content_server(report: ContentServerReport, user=Depends(require_api_key)):
    with _app_context():
        row = ub.update_content_server_status(report.url, report.online,
                                              report.library_name,
                                              reported_by=getattr(user, "name", "?"))
    log.info("Sync API: content server reported by %s: %s online=%s",
             getattr(user, "name", "?"), report.url, report.online)
    return {
        "url": row.url or "",
        "online": bool(row.online),
        "library_name": row.library_name or "",
        "last_seen": _fmt(row.last_seen),
        "last_reported_by": row.last_reported_by or "",
    }


@router.get("/books", response_model=SyncBookList)
def list_books(
    since: str = Query(
        "", description="Only return books with last_modified >= this ISO timestamp"),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    user=Depends(require_api_key),
):
    with _app_context():
        query = calibre_db.session.query(db.Books)
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid 'since' timestamp")
            query = query.filter(db.Books.last_modified >= since_dt)
        total = query.count()
        books = query.order_by(db.Books.id.asc()).offset(offset).limit(limit).all()
        return SyncBookList(
            total=total,
            offset=offset,
            limit=limit,
            books=[_book_to_dict(b) for b in books],
        )


@router.get("/books/{book_id}/file")
def download_file(
    book_id: int,
    format: str = Query(..., min_length=1, max_length=10),
    user=Depends(require_download_user),
):
    fmt = format.upper()
    with _app_context():
        book = calibre_db.session.get(db.Books, book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")
        data = calibre_db.get_book_format(book_id, fmt)
        if data is None:
            raise HTTPException(status_code=404, detail="Format not available for this book")
        book_dir = os.path.join(config.get_book_path(), book.path)
        matches = [p for p in glob.glob(os.path.join(book_dir, data.name + ".*"))
                   if os.path.splitext(p)[1].lower().lstrip(".") == fmt.lower()]
        if not matches:
            raise HTTPException(status_code=404, detail="File not found on disk")
        path = matches[0]
        media_type = mimetypes.types_map.get("." + fmt.lower(), "application/octet-stream")
        filename = "{}.{}".format(book.title or "book", fmt)
        headers = {"Content-Disposition": "attachment; filename*=UTF-8''{}".format(
            helper.get_valid_filename(filename, replace_whitespace=False, force_unidecode=True))}
        return Response(content=open(path, "rb").read(), media_type=media_type, headers=headers)


@router.get("/books/{book_id}/cover")
def download_cover(
    book_id: int,
    user=Depends(require_api_key),
):
    with _app_context():
        book = calibre_db.session.get(db.Books, book_id)
        if book is None or not book.has_cover:
            raise HTTPException(status_code=404, detail="Book has no cover")
        path = os.path.join(config.get_book_path(), book.path, "cover.jpg")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Cover file not found on disk")
        return Response(content=open(path, "rb").read(), media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Upsert (create or update) and delete
# ---------------------------------------------------------------------------


class _FileUpload:
    """A saved upload: temp path plus derived format."""
    def __init__(self, path, fmt):
        self.path = path
        self.fmt = fmt


_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _save_upload(upload: UploadFile, allowed_extensions: Optional[set] = None) -> Optional[str]:
    extension = os.path.splitext(upload.filename or "")[1].lower()
    if allowed_extensions is None:
        if not _allowed_format(extension):
            raise HTTPException(status_code=400, detail="Format '{}' not allowed for upload".format(extension))
    elif extension not in allowed_extensions:
        raise HTTPException(status_code=400,
                            detail="Unsupported image format '{}' for cover".format(extension))
    tmp_path = os.path.join(get_temp_dir(), uuid_module.uuid4().hex + extension)
    total = 0
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = upload.file.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="Uploaded file too large")
                out.write(chunk)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
    return tmp_path


def _apply_metadata_update(book, metadata, modify_date):
    """Apply standard metadata from a sync payload to an existing book."""
    if metadata.get("title"):
        modify_date |= handle_title_on_edit(book, metadata["title"])
    if "authors" in metadata and metadata["authors"]:
        _, author_change = handle_author_on_edit(book, " & ".join(metadata["authors"]))
        modify_date |= author_change
    series = metadata.get("series")
    if series is not None:
        modify_date |= edit_book_series(series, book)
        modify_date |= edit_book_series_index(str(metadata.get("series_index", "1.0")), book)
    if metadata.get("publisher") is not None:
        modify_date |= edit_book_publisher(metadata.get("publisher", ""), book)
    if metadata.get("comments") is not None:
        modify_date |= edit_book_comments(metadata.get("comments", ""), book)
    if metadata.get("rating") is not None:
        rating = float(metadata.get("rating") or 0)
        modify_date |= edit_book_ratings({"rating": str(rating) if rating > 0 else ""}, book)
    if metadata.get("languages"):
        invalid = []
        modify_date |= edit_book_languages(",".join(metadata["languages"]), book,
                                           upload_mode=True, invalid=invalid)
    if metadata.get("tags") is not None:
        modify_date |= edit_book_tags(",".join(metadata["tags"]), book)
    if "identifiers" in metadata and isinstance(metadata["identifiers"], dict):
        identifier_list = [db.Identifiers(str(val), str(type_key), book.id)
                           for type_key, val in metadata["identifiers"].items()]
        modification, _ = modify_identifiers(identifier_list, book.identifiers, calibre_db.session)
        modify_date |= modification
    if metadata.get("pubdate"):
        try:
            pubdate = datetime.strptime(str(metadata["pubdate"])[:10], "%Y-%m-%d")
            if book.pubdate != pubdate:
                book.pubdate = pubdate
                modify_date = True
        except ValueError:
            pass
    if metadata.get("uuid") and not book.uuid:
        book.uuid = metadata["uuid"]
    return modify_date


def _store_extra_formats(book, title_dir, extra_files):
    """Copy additional uploaded formats into the book folder and register them."""
    if not extra_files or config.config_use_google_drive:
        return
    dest_dir = os.path.join(config.get_book_path(), book.path)
    os.makedirs(dest_dir, exist_ok=True)
    existing = {d.format for d in book.data}
    for extra in extra_files:
        fmt = extra.fmt.upper().lstrip(".")
        if fmt in existing:
            continue
        dest = os.path.join(dest_dir, title_dir + "." + fmt)
        shutil.copy2(extra.path, dest)
        book.data.append(db.Data(book, fmt, os.path.getsize(dest), title_dir))
        existing.add(fmt)


@router.post("/books", response_model=SyncWriteResult)
def upsert_book(
    metadata: str = Form(..., description="JSON object with book metadata"),
    files: List[UploadFile] = File(None, description="One or more book files"),
    cover: UploadFile = File(None, description="Optional cover image"),
    user=Depends(require_write_user),
):
    from .. import app as flask_app
    from ..binary_helper import SUPPORTED_UNRAR_BINARIES, resolve_binary_path
    from ..editbooks import create_book_on_upload, move_coverfile
    from .. import uploader

    try:
        payload = json.loads(metadata)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Metadata is not valid JSON")

    if not payload or not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Metadata must be a JSON object")

    book_uuid = (payload.get("uuid") or "").strip()
    identifiers = payload.get("identifiers") or {}
    title = (payload.get("title") or "").strip()

    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    saved_files = []
    cover_path = None
    try:
        try:
            for f in files or []:
                if f and f.filename:
                    saved_files.append(_FileUpload(_save_upload(f), os.path.splitext(f.filename)[1]))
        except HTTPException:
            raise
        if cover and cover.filename:
            cover_path = _save_upload(cover, _COVER_EXTENSIONS)

        matched_book = None
        with flask_app.test_request_context():
            try:
                calibre_db.create_functions(config)
                matched_book = _find_book_by_uuid(book_uuid) if book_uuid else None
                if matched_book is None:
                    matched_book = _find_book_by_identifiers(identifiers)
                if matched_book is not None:
                    # ---- update path -------------------------------------------------
                    db_book = matched_book
                    modify_date = _apply_metadata_update(db_book, payload, False)
                    title_dir = helper.get_valid_filename(db_book.title, chars=96)
                    _store_extra_formats(db_book, title_dir, saved_files)
                    if cover_path:
                        dest = os.path.join(config.get_book_path(), db_book.path)
                        os.makedirs(dest, exist_ok=True)
                        shutil.copy2(cover_path, os.path.join(dest, "cover.jpg"))
                        db_book.has_cover = 1
                    if modify_date:
                        calibre_db.set_metadata_dirty(db_book.id)
                    calibre_db.session.commit()
                    if cover_path:
                        helper.add_book_to_thumbnail_cache(db_book.id)
                    log.info("Sync API: user %s updated '%s' (book id %s)",
                             getattr(user, "name", "?"), db_book.title, db_book.id)
                    return SyncWriteResult(book_id=db_book.id, uuid=db_book.uuid or "",
                                           matched=True, message="Book updated")
                # ---- create path ----------------------------------------------------
                if not saved_files:
                    raise HTTPException(status_code=400, detail="At least one book file is required")
                first = saved_files[0]
                rar_executable = resolve_binary_path(config.config_rarfile_location,
                                                     SUPPORTED_UNRAR_BINARIES)
                file_stem = os.path.splitext(os.path.basename(first.path))[0]
                meta = uploader.process(first.path, file_stem or "ebook", first.fmt, rar_executable)
                meta = meta._replace(
                    title=title,
                    series=payload.get("series") or meta.series,
                    series_id=str(payload.get("series_index") or meta.series_id or ""),
                    publisher=payload.get("publisher") if payload.get("publisher") is not None else meta.publisher,
                    pubdate=payload.get("pubdate") if payload.get("pubdate") else meta.pubdate,
                    tags=",".join(payload.get("tags") or []),
                    languages=",".join(payload.get("languages") or []) if payload.get("languages") else meta.languages,
                    identifiers=[(str(k), str(v)) for k, v in identifiers.items()],
                )
                if payload.get("authors"):
                    meta = meta._replace(author=" & ".join(payload["authors"]))
                if payload.get("comments") is not None:
                    meta = meta._replace(description=payload.get("comments", ""))
                if cover_path:
                    meta = meta._replace(cover=cover_path)

                modify_date = False
                db_book, input_authors, title_dir = create_book_on_upload(modify_date, meta)
                modify_date |= edit_book_comments(meta.description, db_book)
                if payload.get("rating") is not None:
                    rating = float(payload.get("rating") or 0)
                    modify_date |= edit_book_ratings({"rating": str(rating) if rating > 0 else ""}, db_book)
                if not db_book.uuid:
                    db_book.uuid = book_uuid or str(uuid_module.uuid4())

                book_id = db_book.id
                error = None
                if config.config_use_google_drive:
                    from .. import gdriveutils
                    helper.upload_new_file_gdrive(book_id, input_authors[0], db_book.title,
                                                  title_dir, meta.file_path, meta.extension.lower())
                    for file_format in db_book.data:
                        file_format.name = (helper.get_valid_filename(db_book.title, chars=42)
                                            + " - " + helper.get_valid_filename(input_authors[0], chars=42))
                else:
                    error = helper.update_dir_structure(book_id,
                                                        config.get_book_path(),
                                                        input_authors[0],
                                                        meta.file_path,
                                                        title_dir + meta.extension.lower())
                move_coverfile(meta, db_book)
                if error:
                    calibre_db.session.rollback()
                    raise HTTPException(status_code=500, detail=error)
                _store_extra_formats(db_book, title_dir, saved_files[1:])
                if modify_date:
                    calibre_db.set_metadata_dirty(book_id)
                calibre_db.session.commit()
                helper.add_book_to_thumbnail_cache(book_id)
                log.info("Sync API: user %s created '%s' (book id %s)",
                         getattr(user, "name", "?"), db_book.title, book_id)
                return SyncWriteResult(book_id=book_id, uuid=db_book.uuid or "",
                                       matched=False, message="Book created")
            except HTTPException:
                calibre_db.session.rollback()
                raise
            except (IntegrityError, OperationalError, StaleDataError) as e:
                calibre_db.session.rollback()
                log.error_or_exception("Sync API database error: %s", e)
                raise HTTPException(status_code=500, detail="Could not write the book to the library")
            except Exception as e:
                calibre_db.session.rollback()
                log.error_or_exception("Sync API upsert failed: %s", e)
                raise HTTPException(status_code=500,
                                    detail="Could not write the book to the library ({})".format(e))
    finally:
        for f in saved_files:
            if os.path.exists(f.path):
                try:
                    os.remove(f.path)
                except OSError:
                    pass
        if cover_path and os.path.exists(cover_path):
            try:
                os.remove(cover_path)
            except OSError:
                pass


@router.delete("/books/{book_id}", response_model=SyncWriteResult)
def delete_book(
    book_id: int,
    user=Depends(require_delete_user),
):
    from .. import app as flask_app
    from ..editbooks import delete_book_from_table

    with _app_context():
        book = calibre_db.session.get(db.Books, book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")
    with flask_app.test_request_context():
        try:
            calibre_db.create_functions(config)
            delete_book_from_table(book_id)
            log.info("Sync API: user %s deleted book id %s", getattr(user, "name", "?"), book_id)
            return SyncWriteResult(book_id=book_id, uuid=book.uuid or "",
                                   matched=False, message="Book deleted")
        except Exception as e:
            calibre_db.session.rollback()
            log.error_or_exception("Sync API delete failed: %s", e)
            raise HTTPException(status_code=500, detail="Could not delete the book")


api.include_router(router)
