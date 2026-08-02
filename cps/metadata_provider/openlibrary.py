# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2021 OzzieIsaacs
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.

# Open Library api document: https://openlibrary.org/developers/api
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

from cps import logger
from cps.isoLanguages import get_lang3, get_language_name
from cps.services.Metadata import MetaRecord, MetaSourceInfo, Metadata

log = logger.create()


class OpenLibrary(Metadata):
    __name__ = "Open Library"
    __id__ = "openlibrary"
    DESCRIPTION = "Open Library"
    META_URL = "https://openlibrary.org/"
    BOOK_URL = "https://openlibrary.org"
    SEARCH_URL = (
        "https://openlibrary.org/search.json?fields=key,title,author_name,"
        "first_publish_year,publisher,language,cover_i,isbn,id_google,"
        "id_goodreads,id_amazon&limit=20&q="
    )
    COVER_URL = "https://covers.openlibrary.org/b/id/{}-L.jpg"

    def search(
        self, query: str, generic_cover: str = "", locale: str = "en"
    ) -> Optional[List[MetaRecord]]:
        val = list()
        if self.active:
            if self.is_isbn(query):
                query = self.clean_isbn(query)
            else:
                title_tokens = list(self.get_title_tokens(query, strip_joiners=False))
                if title_tokens:
                    tokens = [quote(t.encode("utf-8")) for t in title_tokens]
                    query = "+".join(tokens)
            try:
                results = requests.get(OpenLibrary.SEARCH_URL + query)
                results.raise_for_status()
            except Exception as e:
                log.warning(e)
                return []
            for result in results.json().get("docs", []):
                val.append(
                    self._parse_search_result(
                        result=result, generic_cover=generic_cover, locale=locale
                    )
                )
        return val

    def _parse_search_result(
        self, result: Dict, generic_cover: str, locale: str
    ) -> MetaRecord:
        work_key = result.get("key", "")
        match = MetaRecord(
            id=work_key.split("/")[-1],
            title=result.get("title", ""),
            authors=result.get("author_name", []),
            url=OpenLibrary.BOOK_URL + work_key,
            source=MetaSourceInfo(
                id=self.__id__,
                description=OpenLibrary.DESCRIPTION,
                link=OpenLibrary.META_URL,
            ),
        )

        match.cover = self._parse_cover(result=result, generic_cover=generic_cover)
        match.languages = self._parse_languages(result=result, locale=locale)
        publishers = result.get("publisher", [])
        match.publisher = publishers[0] if publishers else ""
        first_publish_year = result.get("first_publish_year")
        match.publishedDate = (
            "{}-01-01".format(first_publish_year) if first_publish_year else ""
        )
        match.rating = 0
        match.series, match.series_index = "", 1

        match.identifiers = {"openlibrary": match.id}
        self._parse_isbn(result=result, match=match)
        self._parse_related_identifiers(result=result, match=match)
        return match

    @staticmethod
    def _parse_cover(result: Dict, generic_cover: str) -> str:
        cover_id = result.get("cover_i")
        if cover_id:
            return OpenLibrary.COVER_URL.format(cover_id)
        return generic_cover

    @staticmethod
    def _parse_languages(result: Dict, locale: str) -> List[str]:
        languages = list()
        for lang in result.get("language", []):
            try:
                language_name = get_language_name(locale, get_lang3(lang))
                if language_name != "Unknown":
                    languages.append(language_name)
            except Exception as e:
                log.warning(e)
        return languages

    @staticmethod
    def _parse_isbn(result: Dict, match: MetaRecord) -> MetaRecord:
        for isbn in result.get("isbn", []):
            isbn = isbn.replace("-", "")
            if isbn.isdigit() and len(isbn) in (10, 13):
                match.identifiers["isbn"] = isbn
                break
        return match

    @staticmethod
    def _parse_related_identifiers(result: Dict, match: MetaRecord) -> MetaRecord:
        for field in ("id_google", "id_goodreads", "id_amazon"):
            values = result.get(field, [])
            if values:
                match.identifiers[field.replace("id_", "")] = values[0]
        return match
