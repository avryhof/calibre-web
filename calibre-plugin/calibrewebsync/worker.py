# -*- coding: utf-8 -*-

"""Worker action for the Calibre-Web Sync plugin.

Two-way sync engine:

* Push: local books whose metadata changed since the last push (newest-wins
  against the remote) are uploaded to Calibre-Web as files + metadata + cover.
* Pull: remote books that are missing locally are imported (files + cover +
  metadata); remote books newer than their local copy get their metadata,
  missing formats and cover applied.
* Delete (optional, off by default): books removed on one side are removed on
  the other.

Matching between the two sides is by the Calibre book UUID, which is stable
across both applications. Matching state is kept in the plugin preferences.
"""

import json
import mimetypes
import os
import ssl
import traceback
import urllib.request
import uuid as uuid_module
from datetime import datetime, timezone

from calibre.gui2.actions import InterfaceAction

try:
    from PyQt5.QtWidgets import QMessageBox, QDialog, QApplication
except ImportError:  # pragma: no cover
    from PyQt6.QtWidgets import QMessageBox, QDialog, QApplication

try:
    from calibre.ebooks.metadata.book.base import Metadata
except Exception:  # pragma: no cover
    Metadata = None

from calibre_plugins.calibrewebsync.config import prefs, ConfigDialog

DEFAULT_TIMEOUT = 120


def _iso(dt):
    if not dt:
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S+00:00').replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _epoch(dt):
    if not dt:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, status, detail):
        super().__init__("HTTP {}: {}".format(status, detail))
        self.status = status
        self.detail = detail


class _Client(object):
    def __init__(self, server_url, api_key, verify_ssl):
        self.base = server_url.rstrip('/')
        self.api_key = api_key
        self._context = None
        if not verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._context = ctx

    def _request(self, method, path, body=None, headers=None, timeout=DEFAULT_TIMEOUT):
        url = self.base + path
        req_headers = {'X-API-Key': self.api_key}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self._context) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                payload = json.loads(e.read().decode('utf-8', 'replace'))
                detail = payload.get('detail') or payload.get('message') or str(e)
            except Exception:
                detail = str(e)
            raise ApiError(e.code, detail)

    def get_json(self, path):
        status, body = self._request('GET', path)
        return json.loads(body.decode('utf-8', 'replace'))

    def get_bytes(self, path, timeout=DEFAULT_TIMEOUT):
        return self._request('GET', path, timeout=timeout)[1]

    def post_multipart(self, path, fields, files, timeout=DEFAULT_TIMEOUT):
        boundary = uuid_module.uuid4().hex
        crlf = b'\r\n'
        body = bytearray()
        for name, value in fields:
            body += b'--' + boundary.encode() + crlf
            body += b'Content-Disposition: form-data; name="%s"' % name.encode() + crlf + crlf
            body += str(value).encode('utf-8') + crlf
        for name, filename, data in files:
            body += b'--' + boundary.encode() + crlf
            body += b'Content-Disposition: form-data; name="%s"; filename="%s"' % (
                name.encode(), filename.encode()) + crlf
            ctype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            body += b'Content-Type: ' + ctype.encode() + crlf + crlf
            body += bytes(data) + crlf
        body += b'--' + boundary.encode() + b'--' + crlf
        headers = {'Content-Type': 'multipart/form-data; boundary=%s' % boundary}
        status, resp = self._request('POST', path, body=bytes(body), headers=headers,
                                     timeout=timeout)
        return json.loads(resp.decode('utf-8', 'replace'))

    def delete(self, path):
        return self._request('DELETE', path)


# ---------------------------------------------------------------------------
# Metadata serialization
# ---------------------------------------------------------------------------


def metadata_to_payload(m):
    return {
        'uuid': m.uuid or '',
        'title': m.title or '',
        'authors': list(m.authors or []),
        'series': m.series or '',
        'series_index': str(m.series_index or 1.0),
        'publisher': m.publisher or '',
        'pubdate': _iso(m.pubdate),
        'rating': float(m.rating) if m.rating else 0.0,
        'languages': list(m.languages or []),
        'comments': m.comments or '',
        'tags': list(m.tags or []),
        'identifiers': dict(m.identifiers or {}),
    }


def payload_to_metadata(payload):
    if Metadata is None:
        raise RuntimeError('calibre Metadata import unavailable')
    try:
        rating = float(payload.get('rating') or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        series_index = float(payload.get('series_index') or 1.0)
    except (TypeError, ValueError):
        series_index = 1.0
    m = Metadata(
        title=payload.get('title') or 'Unknown',
        authors=list(payload.get('authors') or []),
        tags=list(payload.get('tags') or []),
        series=payload.get('series') or None,
        series_index=series_index,
        comments=payload.get('comments') or '',
        publisher=payload.get('publisher') or None,
        pubdate=_parse_iso(payload.get('pubdate')),
        rating=rating if rating > 0 else None,
        languages=list(payload.get('languages') or []),
        identifiers=dict(payload.get('identifiers') or {}),
    )
    if payload.get('uuid'):
        m.uuid = payload['uuid']
    return m


# ---------------------------------------------------------------------------
# The action
# ---------------------------------------------------------------------------


class CalibreWebSyncAction(InterfaceAction):
    name = 'Calibre-Web Sync'
    action_spec = ('Calibre-Web Sync', None,
                   'Sync the library with a Calibre-Web server', ())
    action_type = 'current'
    dont_add_to = None

    def do_user_clicked_gui(self, event_queue):
        """Runs in a background thread. Posts GUI work back via event_queue."""
        try:
            if not prefs.get('server_url') or not prefs.get('api_key'):
                event_queue.put(('_open_config', None))
                return
            event_queue.put(('_sync_progress', 'Starting sync...'))
            summary = self._do_sync()
        except Exception:
            event_queue.put(('_sync_finished', 'Sync failed:\n' + traceback.format_exc()))
        else:
            event_queue.put(('_sync_finished', summary))

    def _open_config(self, _unused):
        dlg = ConfigDialog(self.gui)
        if dlg.exec_() == QDialog.Accepted:
            dlg.save_settings()
            QMessageBox.information(
                self.gui, 'Calibre-Web Sync',
                'Settings saved. Click Calibre-Web Sync again to run the sync.')

    def _sync_finished(self, summary):
        QMessageBox.information(self.gui, 'Calibre-Web Sync', summary)

    def _sync_progress(self, text):
        QApplication.processEvents()

    # -- sync engine -------------------------------------------------------

    def _get_db(self):
        try:
            db = self.gui.current_db
        except Exception:
            db = None
        if db is None:
            db = self.gui.library_view.model().db
        return db

    def _do_sync(self):
        db = self._get_db()
        client = _Client(prefs['server_url'], prefs['api_key'], prefs.get('verify_ssl', True))
        state = prefs.get('state', {})
        last_push = state.get('last_push', {})      # uuid -> epoch of local mtime
        last_local_uuids = set(state.get('last_local_uuids', []))

        report = []
        remote_by_uuid = {}

        # Phase A: fetch the remote book list.
        remote_by_uuid, remote_total = self._fetch_remote(client)
        report.append('Remote library: {} books'.format(remote_total))
        remote_uuids = set(remote_by_uuid)

        # Phase B: push local changes.
        local_by_uuid = {}
        if prefs.get('push_changes', True):
            try:
                report.append(self._push_local(client, db, last_push, remote_by_uuid))
            except Exception as e:
                report.append('Push failed: {}'.format(e))
                report.append('Pull skipped to avoid overwriting unsynced local changes.')
                prefs['state'] = state
                return '\n'.join(report)
            local_by_uuid = self._collect_local(db)

        # Phase C: pull remote changes.
        if prefs.get('pull_changes', True):
            local_by_uuid = self._collect_local(db)
            try:
                report.append(self._pull_remote(client, db, last_push, remote_by_uuid,
                                                local_by_uuid))
            except Exception as e:
                report.append('Pull failed: {}'.format(e))

        # Phase D: optional delete propagation.
        if prefs.get('delete_removed', False):
            report.append(self._sync_deletions(client, db, last_push,
                                               last_local_uuids, remote_by_uuid))

        state['last_local_uuids'] = list(local_by_uuid)
        try:
            db.commit()
        except Exception:
            pass
        prefs['state'] = state
        report.append('Sync complete.')
        return '\n'.join(report)

    def _fetch_remote(self, client):
        remote_by_uuid = {}
        offset = 0
        limit = 200
        total = 0
        while True:
            payload = client.get_json('/api/sync/books?limit=%d&offset=%d' % (limit, offset))
            total = payload.get('total', 0)
            for book in payload.get('books', []):
                if book.get('uuid'):
                    remote_by_uuid[book['uuid']] = book
            offset += limit
            if offset >= total or not payload.get('books'):
                break
        return remote_by_uuid, total

    def _collect_local(self, db):
        local_by_uuid = {}
        for book_id in db.all_ids():
            try:
                m = db.get_metadata(book_id)
            except Exception:
                continue
            if m.uuid:
                local_by_uuid[m.uuid] = (book_id, m)
        return local_by_uuid

    def _push_local(self, client, db, last_push, remote_by_uuid):
        pushed = created = updated = 0
        for book_id in db.all_ids():
            try:
                m = db.get_metadata(book_id)
            except Exception:
                continue
            uuid = m.uuid or ''
            if not uuid:
                continue
            local_m = _epoch(m.last_modified)
            prev = last_push.get(uuid)
            if prev is not None and abs(local_m - prev) < 1.0:
                continue  # unchanged since last push
            remote = remote_by_uuid.get(uuid)
            if remote is not None and remote.get('last_modified'):
                remote_m = _epoch(_parse_iso(remote['last_modified']))
                if remote_m is not None and remote_m > local_m:
                    continue  # remote is newer; pull will handle it
            if not prefs.get('push_changes', True):
                continue
            result = self._upload_book(client, db, book_id, m)
            last_push[uuid] = local_m
            if result.get('matched'):
                updated += 1
            else:
                created += 1
            pushed += 1
        return 'Push: {} uploaded ({} new, {} updated)'.format(pushed, created, updated)

    def _upload_book(self, client, db, book_id, m):
        payload = metadata_to_payload(m)
        fields = [('metadata', json.dumps(payload))]
        files = []
        for fmt in db.formats(book_id):
            path = db.format_abspath(book_id, fmt)
            if path and os.path.isfile(path):
                with open(path, 'rb') as fh:
                    files.append(('files', '{}.{}'.format(m.uuid or book_id, fmt.lower()),
                                  fh.read()))
        if db.has_cover(book_id):
            cover_path = db.cover(book_id)
            if cover_path and os.path.isfile(cover_path):
                with open(cover_path, 'rb') as fh:
                    files.append(('cover', '{}.jpg'.format(m.uuid or book_id), fh.read()))
        return client.post_multipart('/api/sync/books', fields, files)

    def _pull_remote(self, client, db, last_push, remote_by_uuid, local_by_uuid):
        imported = updated = 0
        for uuid, rb in remote_by_uuid.items():
            remote_m = _parse_iso(rb.get('last_modified'))
            if remote_m is None:
                continue
            if uuid not in local_by_uuid:
                self._import_remote_book(client, db, rb)
                imported += 1
                last_push[uuid] = _epoch(remote_m)
                continue
            local_id, m = local_by_uuid[uuid]
            local_m_ep = _epoch(m.last_modified)
            if remote_m.timestamp() > local_m_ep + 1.0:
                self._apply_remote_metadata(client, db, local_id, rb)
                updated += 1
                last_push[uuid] = _epoch(remote_m)
        return 'Pull: {} imported, {} updated'.format(imported, updated)

    def _import_remote_book(self, client, db, rb):
        fmt_paths = []
        for fmt in rb.get('formats', []):
            data = client.get_bytes('/api/sync/books/{}/file?format={}'.format(rb['id'], fmt))
            fmt_paths.append(self._write_temp('{}.{}'.format(rb['id'], fmt.lower()), data))
        metadata = payload_to_metadata(rb)
        if not fmt_paths:
            raise RuntimeError('no formats on remote')
        book_id = db.import_book(metadata, fmt_paths)
        if rb.get('has_cover'):
            try:
                cover_data = client.get_bytes('/api/sync/books/{}/cover'.format(rb['id']))
                cover_path = self._write_temp('{}_cover.jpg'.format(rb['id']), cover_data)
                db.set_cover(book_id, cover_path)
            except ApiError:
                pass
        for path in fmt_paths:
            self._cleanup_temp(path)

    def _apply_remote_metadata(self, client, db, local_id, rb):
        metadata = payload_to_metadata(rb)
        db.set_metadata(local_id, metadata)
        local_formats = set(db.formats(local_id))
        for fmt in rb.get('formats', []):
            if fmt in local_formats:
                continue
            data = client.get_bytes('/api/sync/books/{}/file?format={}'.format(rb['id'], fmt))
            path = self._write_temp('{}.{}'.format(rb['id'], fmt.lower()), data)
            try:
                db.add_format(local_id, fmt, path)
            finally:
                self._cleanup_temp(path)
        if rb.get('has_cover') and not db.has_cover(local_id):
            try:
                cover_data = client.get_bytes('/api/sync/books/{}/cover'.format(rb['id']))
                cover_path = self._write_temp('{}_cover.jpg'.format(rb['id']), cover_data)
                db.set_cover(local_id, cover_path)
                self._cleanup_temp(cover_path)
            except ApiError:
                pass

    def _sync_deletions(self, client, db, last_push, last_local_uuids, remote_by_uuid):
        local_uuids = set()
        for book_id in db.all_ids():
            try:
                m = db.get_metadata(book_id)
            except Exception:
                continue
            if m.uuid:
                local_uuids.add(m.uuid)
        remote_uuids = set(remote_by_uuid)
        deleted_remote = deleted_local = 0
        for uuid in sorted(last_local_uuids):
            if uuid in local_uuids and uuid not in remote_uuids:
                # Removed on the server -> remove locally.
                local_id = None
                for book_id in db.all_ids():
                    try:
                        if db.get_metadata(book_id).uuid == uuid:
                            local_id = book_id
                            break
                    except Exception:
                        continue
                if local_id is not None:
                    try:
                        db.delete_book(local_id, perm=True)
                        deleted_local += 1
                    except Exception:
                        pass
            elif uuid not in local_uuids and uuid in remote_uuids:
                # Removed locally -> remove on the server.
                remote = remote_by_uuid[uuid]
                try:
                    client.delete('/api/sync/books/{}'.format(remote['id']))
                    deleted_remote += 1
                except Exception:
                    pass
        return 'Delete: {} removed locally, {} removed on server'.format(
            deleted_local, deleted_remote)

    # -- helpers -----------------------------------------------------------

    def _write_temp(self, name, data):
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.tmp', prefix='cwsync_')
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
        return path

    def _cleanup_temp(self, path):
        try:
            os.unlink(path)
        except OSError:
            pass
