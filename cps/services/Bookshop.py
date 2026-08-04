# -*- coding: utf-8 -*-

#  Book shop support for Calibre-Web.
#  Providers search external ebook catalogs (free / public-domain ebooks) and
#  return structured BookshopRecord results that can be rendered by the web UI
#  or consumed through the FastAPI endpoint.
#
#  New providers are added by dropping a module into cps/bookshop_provider/ that
#  defines a class subclassing BookshopProvider. Provider discovery is
#  filesystem-based and mirrors cps/metadata_provider.

import abc
import dataclasses
import importlib
import inspect
import os
from typing import Dict, List, Optional

from cps import constants, logger
from cps.services.Metadata import Metadata

log = logger.create()


@dataclasses.dataclass
class BookshopSourceInfo:
    id: str
    name: str
    description: str
    homepage: str


@dataclasses.dataclass
class BookshopRecord:
    id: str
    title: str
    authors: List[str]
    url: str
    source: BookshopSourceInfo
    cover: str = ""
    description: str = ""
    formats: Dict[str, str] = dataclasses.field(default_factory=dict)
    languages: List[str] = dataclasses.field(default_factory=list)
    identifiers: Dict[str, str] = dataclasses.field(default_factory=dict)
    tags: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "authors": self.authors,
            "url": self.url,
            "source": {
                "id": self.source.id,
                "name": self.source.name,
                "description": self.source.description,
                "homepage": self.source.homepage,
            },
            "cover": self.cover,
            "description": self.description,
            "formats": self.formats,
            "languages": self.languages,
            "identifiers": self.identifiers,
            "tags": self.tags,
        }


class BookshopProvider:
    __name__ = "Generic"
    __id__ = "generic"
    DESCRIPTION = ""
    HOMEPAGE = ""
    TIMEOUT = 20

    def __init__(self):
        self.active = True

    def set_status(self, state):
        self.active = state

    @abc.abstractmethod
    def search(self, query: str, limit: int = 12) -> List[BookshopRecord]:
        pass

    def source_info(self) -> BookshopSourceInfo:
        return BookshopSourceInfo(
            id=self.__id__,
            name=self.__name__,
            description=self.DESCRIPTION,
            homepage=self.HOMEPAGE,
        )

    @staticmethod
    def is_isbn(query: str) -> bool:
        return Metadata.is_isbn(query)

    @staticmethod
    def clean_isbn(query: str) -> str:
        return Metadata.clean_isbn(query)


def _provider_modules() -> List[str]:
    directory = os.path.join(constants.BASE_DIR, "cps", "bookshop_provider")
    modules = []
    if not os.path.isdir(directory):
        return modules
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".py") and filename != "__init__.py":
            modules.append("cps.bookshop_provider." + filename[:-3])
    return modules


def list_classes(modules: Optional[List[str]] = None) -> List[BookshopProvider]:
    classes = []
    for module_name in modules or _provider_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            log.warning("Could not import bookshop provider %s: %s", module_name, e)
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BookshopProvider) and obj is not BookshopProvider:
                try:
                    classes.append(obj())
                except Exception as e:
                    log.warning("Could not instantiate bookshop provider %s: %s", obj, e)
    return classes


def get_providers() -> List[BookshopProvider]:
    return [provider for provider in list_classes() if provider.active]
