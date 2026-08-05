# -*- coding: utf-8 -*-

#  Internet Archive book shop provider.
#  Uses the public advancedsearch API plus per-item metadata for download files:
#    https://archive.org/advancedsearch.php
#    https://archive.org/metadata/<identifier>

import concurrent.futures
from urllib.parse import quote

import requests

from cps import logger
from cps.services.Bookshop import BookshopProvider, BookshopRecord

log = logger.create()


class InternetArchive(BookshopProvider):
    __name__ = "Internet Archive"
    __id__ = "internet_archive"
    DESCRIPTION = "Millions of digitized books and texts."
    HOMEPAGE = "https://archive.org/"
    DOWNLOAD_HOSTS = ("archive.org", "archive.org.br")
    SEARCH_URL = "https://archive.org/advancedsearch.php"
    METADATA_URL = "https://archive.org/metadata/{}"
    DETAIL_URL = "https://archive.org/details/{}"
    DOWNLOAD_URL = "https://archive.org/download/{}/{}"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 "
            "(Calibre-Web Book Shop)"
        ),
        "Accept": "application/json",
    }

    ALLOWED_FORMATS = {
        "EPUB": "EPUB",
        "Text PDF": "PDF",
        "PDF": "PDF",
        "DjVuTXT": "TXT",
        "Text": "TXT",
        "MOBI": "MOBI",
        "Kindle": "MOBI",
        "AZW3": "AZW3",
        "DjVu": "DJVU",
    }
    FORMAT_ORDER = ("EPUB", "PDF", "MOBI", "AZW3", "TXT", "DJVU")
    MAX_ENRICH = 8

    @staticmethod
    def _clean_query(query: str) -> str:
        # Keep Solr queries simple: drop characters that would break the query.
        return " ".join(c for c in query.strip().split() if c)

    def search(self, query: str, limit: int = 12, search_type: str = "title"):
        val = []
        if self.is_isbn(query) and search_type == "title":
            query = "identifier:{}".format(self.clean_isbn(query))
        terms = self._clean_query(query)
        if search_type == "author":
            solr_query = (
                "author:({terms}) "
                "AND mediatype:texts AND -access-restricted-item:true"
            ).format(terms=terms)
        else:
            solr_query = (
                "(title:({terms}) OR {terms}) "
                "AND mediatype:texts AND -access-restricted-item:true"
            ).format(terms=terms)
        try:
            results = requests.get(
                self.SEARCH_URL,
                params={
                    "q": solr_query,
                    "fl[]": ["identifier", "title", "creator", "description", "downloads"],
                    "rows": limit,
                    "page": 1,
                    "output": "json",
                    "sort[]": "downloads desc",
                },
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            results.raise_for_status()
        except Exception as e:
            log.warning("Internet Archive search failed: %s", e)
            return val

        docs = results.json().get("response", {}).get("docs", [])
        for doc in docs[:limit]:
            identifier = doc.get("identifier", "")
            if not identifier:
                continue
            creators = doc.get("creator")
            authors = [creators] if isinstance(creators, str) else (creators or [])
            description = doc.get("description", "") or ""
            record = BookshopRecord(
                id=identifier,
                title=doc.get("title") or identifier,
                authors=authors,
                url=self.DETAIL_URL.format(identifier),
                source=self.source_info(),
                cover="https://archive.org/services/img/{}".format(identifier),
                description=description[:600],
                identifiers={"internet_archive": identifier},
            )
            val.append(record)

        self._enrich_downloads(val)
        return val

    def _enrich_downloads(self, records):
        targets = records[: self.MAX_ENRICH]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(6, len(targets) or 1)
        ) as executor:
            futures = {executor.submit(self._fetch_files, record): record for record in targets}
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log.warning("Internet Archive enrichment failed: %s", e)

    def _fetch_files(self, record):
        try:
            resp = requests.get(self.METADATA_URL.format(record.id), timeout=self.TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            log.warning("Internet Archive metadata failed for %s: %s", record.id, e)
            return
        files = resp.json().get("files", [])
        ordered = {}
        for entry in files:
            if entry.get("access-restricted-item"):
                continue
            fmt = entry.get("format", "")
            label = self.ALLOWED_FORMATS.get(fmt)
            if not label or label in ordered:
                continue
            name = entry.get("name", "")
            if not name:
                continue
            ordered[label] = self.DOWNLOAD_URL.format(record.id, quote(name))
        record.formats = {}
        for label in self.FORMAT_ORDER:
            if label in ordered:
                record.formats[label] = ordered[label]
        for label, url in ordered.items():
            if label not in record.formats:
                record.formats[label] = url
