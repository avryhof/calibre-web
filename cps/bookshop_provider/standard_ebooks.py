# -*- coding: utf-8 -*-

#  Standard Ebooks book shop provider.
#  Standard Ebooks does not expose a searchable JSON or OPDS endpoint, so the
#  server-rendered search page is parsed. Download links follow the site's
#  interstitial redirect pattern (`?source=download` serves the raw file).

import requests
from lxml import html

from cps import logger
from cps.services.Bookshop import BookshopProvider, BookshopRecord

log = logger.create()


class StandardEbooks(BookshopProvider):
    __name__ = "Standard Ebooks"
    __id__ = "standard_ebooks"
    DESCRIPTION = "Beautiful, expertly produced public-domain ebooks."
    HOMEPAGE = "https://standardebooks.org/"
    DOWNLOAD_HOSTS = ("standardebooks.org",)
    SEARCH_URL = "https://standardebooks.org/ebooks"
    SITE_URL = "https://standardebooks.org"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 "
            "(Calibre-Web Book Shop)"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    FORMATS = ("epub", "azw3", "kepub.epub")

    def search(self, query: str, limit: int = 12, search_type: str = "title"):
        # Standard Ebooks' search page has no field-specific query, so the terms
        # are passed through unchanged for both title and author searches.
        val = []
        try:
            results = requests.get(
                self.SEARCH_URL,
                params={"query": query.strip()},
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            results.raise_for_status()
        except Exception as e:
            log.warning("Standard Ebooks search failed: %s", e)
            return val

        try:
            root = html.fromstring(results.content)
        except Exception as e:
            log.warning("Standard Ebooks response could not be parsed: %s", e)
            return val

        items = root.xpath("//ol[contains(@class, 'ebooks-list')]/li")
        for item in items:
            if len(val) >= limit:
                break
            record = self._parse_item(item)
            if record:
                val.append(record)
        return val

    def _parse_item(self, item):
        path = item.get("about") or ""
        if not path:
            return None
        title_els = item.xpath(".//span[@property='schema:name']")
        title = title_els[0].text_content().strip() if title_els else path.rsplit("/", 1)[-1]
        author = ""
        author_els = item.xpath(
            "p[contains(@class, 'author')]/.//span[@property='schema:name']"
        )
        if author_els:
            author = author_els[0].text_content().strip()
        cover = ""
        img = item.xpath(".//img")
        if img:
            src = img[0].get("src") or ""
            cover = self.SITE_URL + src.replace("@2x", "")

        # Path layout: /ebooks/<author-slug>/<title-slug>
        parts = path.strip("/").split("/")
        download = {}
        if len(parts) >= 2:
            author_slug = parts[-2]
            title_slug = parts[-1]
            base = "{}{}/downloads/{}_{}".format(
                self.SITE_URL, path, author_slug, title_slug
            )
            for ext in self.FORMATS:
                label = ext.upper()
                if ext == "kepub.epub":
                    label = "KEPUB"
                download[label] = base + "." + ext + "?source=download"

        return BookshopRecord(
            id=path,
            title=title,
            authors=[author] if author else [],
            url=self.SITE_URL + path,
            source=self.source_info(),
            cover=cover,
            formats=download,
            identifiers={"standard_ebooks": path},
        )
