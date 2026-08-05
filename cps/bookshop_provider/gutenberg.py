# -*- coding: utf-8 -*-

#  Project Gutenberg book shop provider.
#  Uses the public Gutendex JSON API: https://gutendex.com/

import requests

from cps import logger
from cps.services.Bookshop import BookshopProvider, BookshopRecord

log = logger.create()


class Gutenberg(BookshopProvider):
    __name__ = "Project Gutenberg"
    __id__ = "gutenberg"
    DESCRIPTION = "Over 70,000 free public-domain ebooks."
    HOMEPAGE = "https://www.gutenberg.org/"
    DOWNLOAD_HOSTS = ("gutenberg.org", "www.gutenberg.org")
    SEARCH_URL = "https://gutendex.com/books"
    BOOK_URL = "https://www.gutenberg.org/ebooks/{}"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 "
            "(Calibre-Web Book Shop)"
        ),
        "Accept": "application/json",
    }

    # Normalized format label per MIME type (without parameters).
    FORMAT_LABELS = {
        "application/epub+zip": "EPUB",
        "application/x-mobipocket-ebook": "MOBI",
        "application/pdf": "PDF",
        "text/html": "HTML",
        "text/plain": "TXT",
    }
    FORMAT_ORDER = ("EPUB", "MOBI", "PDF", "HTML", "TXT")

    def search(self, query: str, limit: int = 12, search_type: str = "title"):
        val = []
        try:
            params = {"search": query.strip()}
            # Gutendex has no dedicated author field filter, but its `search`
            # parameter matches authors as well as titles. ISBN cleaning only
            # makes sense for title searches.
            if search_type == "title" and self.is_isbn(query):
                params["search"] = self.clean_isbn(query)
            results = requests.get(
                self.SEARCH_URL,
                params=params,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            results.raise_for_status()
        except Exception as e:
            log.warning("Gutendex search failed: %s", e)
            return val
        for book in results.json().get("results", [])[:limit]:
            val.append(self._parse_book(book))
        return val

    def _parse_book(self, book):
        formats = book.get("formats", {})
        download = self._pick_formats(formats)
        cover = formats.get("image/jpeg") or formats.get("image/jpg") or ""
        authors = [a.get("name", "") for a in book.get("authors", []) if a.get("name")]
        title = book.get("title", "")
        book_id = book.get("id")
        summaries = book.get("summaries") or []
        record = BookshopRecord(
            id=str(book_id),
            title=title,
            authors=authors,
            url=self.BOOK_URL.format(book_id),
            source=self.source_info(),
            cover=cover,
            description=summaries[0] if summaries else "",
            formats=download,
            languages=book.get("languages", []),
            identifiers={"gutenberg": str(book_id)} if book_id else {},
            tags=(book.get("subjects") or [])[:6],
        )
        return record

    @classmethod
    def _pick_formats(cls, formats):
        """Map Gutendex MIME keys to ordered, de-duplicated format labels."""
        available = {}
        for mime, url in formats.items():
            clean = mime.split(";", 1)[0].strip().lower()
            label = cls.FORMAT_LABELS.get(clean)
            if label and url and label not in available:
                available[label] = url
        ordered = {}
        for label in cls.FORMAT_ORDER:
            if label in available:
                ordered[label] = available[label]
        for label, url in available.items():
            if label not in ordered:
                ordered[label] = url
        return ordered
