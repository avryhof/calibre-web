# Calibre-Web Sync (Calibre desktop plugin)

Two-way sync between a Calibre desktop library and a Calibre-Web server.

* **Push** — books added or edited in Calibre desktop (files, full standard
  metadata and cover) are uploaded to Calibre-Web. Calibre-Web creates a new
  book or updates the matching one.
* **Pull** — books that exist on Calibre-Web but not locally are imported
  (files, cover, metadata); books that are newer on Calibre-Web get their
  metadata, missing formats and cover applied.
* **Deletions** (optional, off by default) — a book removed on one side is
  removed on the other.
* Conflicts resolve by newest `last_modified` wins.

## Requirements

* Calibre 5.0 or newer (the plugin targets Qt5/PyQt5).
* Calibre-Web with the sync API available (`/api/sync`) and FastAPI mounted
  under `/api`.
* An API key created in Calibre-Web: **Settings → API Keys → Generate API Key**.
  Assign it to a user with at least upload (to push) and download (to pull)
  permissions.

## Install

1. Build the plugin zip:

   ```bash
   ./calibre-plugin/build_plugin.sh
   ```

2. In Calibre: **Preferences → Plugins → Load plugin from file**, then pick
   `calibre-plugin/calibrewebsync.zip`. Restart Calibre.
3. Click the **Calibre-Web Sync** toolbar button (or **Preferences → Plugins →
   Customize plugin**) and enter the server URL and API key. Enable/disable
   push, pull and delete propagation as desired.
4. Click **Calibre-Web Sync** to run a sync. A summary dialog shows what
   happened.

## How matching works

Books are matched by the Calibre book UUID, which is stable in both the Calibre
library and Calibre-Web. New books are matched by UUID first and by ISBN
identifier as a fallback. Sync state (the last pushed/pulled modification time
per book) is stored in the plugin preferences, so only changed books are
transferred after the first run.

## API

The plugin talks to the Calibre-Web FastAPI router `cps/api/sync.py`
(`GET /api/sync/status`, `GET /api/sync/books`, `GET /api/sync/books/{id}/file`,
`GET /api/sync/books/{id}/cover`, `POST /api/sync/books`,
`DELETE /api/sync/books/{id}`), authenticated with an `X-API-Key` header.

## Notes and limitations

* The first sync transfers the whole library; later syncs are incremental.
* A book edited twice within the same second locally may not be detected as
  changed (change detection has 1s resolution).
* With Google Drive storage configured on Calibre-Web, only the first format of
  a new upload is guaranteed to be stored (extra formats are skipped).
* Delete propagation only removes books on the opposite side that existed at
  the previous sync, and only when enabled.
