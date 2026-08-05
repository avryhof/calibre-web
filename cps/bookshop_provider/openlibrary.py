# -*- coding: utf-8 -*-

#  Open Library book shop provider.
#  Uses the public search.json API. The Open Library search service is
#  occasionally overloaded, so this provider retries once and degrades to an
#  empty result list rather than failing the whole search.

import time

import requests

from cps import logger
from cps.services.Bookshop import BookshopProvider, BookshopRecord

log = logger.create()


class OpenLibrary(BookshopProvider):
    __name__ = "Open Library"
    __id__ = "openlibrary"
    DESCRIPTION = "The open library of the Internet Archive."
    HOMEPAGE = "https://openlibrary.org/"
    DOWNLOAD_HOSTS = ("openlibrary.org", "archive.org")
    SEARCH_URL = "https://openlibrary.org/search.json"
    BOOK_URL = "https://openlibrary.org"
    COVER_URL = "https://covers.openlibrary.org/b/id/{}-L.jpg"
    RETRIES = 0
    RETRY_DELAY = 1
    TIMEOUT = 15
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 "
            "(Calibre-Web Book Shop)"
        ),
        "Accept": "application/json",
    }

    def search(self, query: str, limit: int = 12, search_type: str = "title"):
        val = []
        params = {
            "fields": "key,title,author_name,first_publish_year,cover_i,isbn,subject",
            "limit": limit,
        }
        if search_type == "author":
            params["author"] = query.strip()
        else:
            params["q"] = query.strip()
        results = self._get(params)
        if results is None:
            return val
        for doc in results.get("docs", [])[:limit]:
            val.append(self._parse_doc(doc))
        return val

    def _get(self, params):
        for attempt in range(self.RETRIES + 1):
            try:
                resp = requests.get(
                    self.SEARCH_URL,
                    params=params,
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                log.warning("Open Library search attempt %s failed: %s", attempt + 1, e)
            except Exception as e:
                log.warning("Open Library search attempt %s error: %s", attempt + 1, e)
            if attempt < self.RETRIES:
                time.sleep(self.RETRY_DELAY)
        return None

    def _parse_doc(self, doc):
        work_key = doc.get("key", "")
        work_id = work_key.rsplit("/", 1)[-1] if work_key else ""
        cover_id = doc.get("cover_i")
        first_year = doc.get("first_publish_year")
        published = "{}-01-01".format(first_year) if first_year else ""
        return BookshopRecord(
            id=work_id,
            title=doc.get("title", ""),
            authors=doc.get("author_name", []),
            url=self.BOOK_URL + work_key if work_key else self.HOMEPAGE,
            source=self.source_info(),
            cover=self.COVER_URL.format(cover_id) if cover_id else "",
            description=published,
            languages=[],
            identifiers={"openlibrary": work_id} if work_id else {},
            tags=(doc.get("subject") or [])[:6],
        )
