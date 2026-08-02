# -*- coding: utf-8 -*-

#  Physical book merging for Calibre-Web.
#  This module lets physical books (stored in Calibre-Web's own user database) appear
#  inside the regular ebook library views. Physical books are interleaved into the
#  existing result grids using evenly spaced insertion slots so that they stay visible
#  across every page while ebooks keep their SQL-side pagination.

import re
from collections import namedtuple
from datetime import datetime, timezone

from . import config, constants, db, ub
from .cw_login import current_user

PHYSICAL_PREFIX = "phys:"

# A physical entry mimics the (Books, is_archived, read_status) Row that the
# library templates expect, so `entry.Books.*` and `entry[2]` both work.
PhysicalEntryRow = namedtuple("PhysicalEntryRow", ["Books", "is_archived", "read_status"])


def is_physical_filter(book_id):
    return isinstance(book_id, str) and book_id.startswith(PHYSICAL_PREFIX)


def phys_id(kind, value):
    return PHYSICAL_PREFIX + kind + ":" + value


def parse_phys_filter(book_id):
    """Return (kind, value) if book_id is a physical entity filter, else None."""
    if not is_physical_filter(book_id):
        return None
    parts = book_id.split(":", 2)
    if len(parts) == 3:
        return parts[1], parts[2]
    return None


def all_physical_books():
    if current_user.is_anonymous:
        return []
    return ub.session.query(ub.PhysicalBook).all()


def _parse_pubdate(value):
    match = re.match(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", (value or "").strip())
    if match:
        return int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1)
    return 0, 0, 0


def physical_sort_key(order_name):
    order_name = order_name or "new"

    def key(book):
        timestamp = book.last_modified or datetime(1970, 1, 1, tzinfo=timezone.utc)
        title = (book.title or "").lower()
        author = (book.authors or "").lower()
        if order_name in ("abc", "zyx"):
            return (title, book.id)
        if order_name in ("authaz", "authza"):
            return (author, title)
        if order_name in ("pubnew", "pubold"):
            return (_parse_pubdate(book.published_date), title)
        if order_name in ("seriesasc", "seriesdesc"):
            return (book.series_index or 0.0, title)
        return (timestamp, book.id)

    return key


def physical_books_sorted(books, order_name):
    reverse = order_name in ("zyx", "authza", "pubold", "seriesdesc")
    return sorted(books, key=physical_sort_key(order_name), reverse=reverse)


def merge_pages(page, per_page, ebook_total, physical_books):
    """Compute the interleaved page for a merged ebook/physical result set.

    Returns a dict with:
      page_physical: list of (slot, PhysicalBook) on the current page
      ebook_offset:  offset of the ebook sub-query for this page
      ebook_limit:   how many ebooks to fetch for this page
      total:         merged result count
    """
    m = len(physical_books)
    if m == 0:
        return {"page_physical": [], "ebook_offset": (page - 1) * per_page,
                "ebook_limit": per_page, "total": ebook_total}
    total = ebook_total + m
    slots = [int((i + 1) * total / (m + 1)) for i in range(m)]
    page_start = (page - 1) * per_page
    page_end = page_start + per_page
    page_physical = [(slot, book) for slot, book in zip(slots, physical_books)
                     if page_start <= slot < page_end]
    before = sum(1 for s in slots if s < page_start)
    ebook_offset = max(0, page_start - before)
    ebook_limit = max(0, per_page - len(page_physical))
    ebook_limit = min(ebook_limit, max(0, ebook_total - ebook_offset))
    return {"page_physical": page_physical, "ebook_offset": ebook_offset,
            "ebook_limit": ebook_limit, "total": total}


def build_page(page, per_page, ebook_entries, merged):
    """Interleave ebook rows and physical entries into the page's display order."""
    page_physical = merged.get("page_physical")
    if not page_physical:
        return ebook_entries
    page_start = (page - 1) * per_page
    physical_by_slot = {slot: wrap_physical(book) for slot, book in page_physical}
    positions = sorted(physical_by_slot.keys())
    entries = []
    ebook_iter = iter(ebook_entries)
    idx = 0
    for pos in range(page_start, page_start + per_page):
        if idx < len(positions) and pos == positions[idx]:
            entries.append(physical_by_slot[positions[idx]])
            idx += 1
        else:
            try:
                entries.append(next(ebook_iter))
            except StopIteration:
                break
    return entries


class _SimpleEntity(object):
    def __init__(self, name, entity_id):
        self.name = name
        self.id = entity_id

    def replace(self, *args):
        return self.name.replace(*args)


class _SimpleRating(object):
    def __init__(self, rating):
        # calibre stores ratings 2-10 and templates divide by 2 for stars
        self.rating = rating * 2


class PhysicalBookView(object):
    """Adapter that lets a PhysicalBook be rendered by the regular library templates."""

    def __init__(self, book):
        self.book = book
        self.id = book.id
        self.title = book.title or ""
        self.name = self.title
        self.has_cover = 1 if book.cover else 0
        self.last_modified = book.last_modified or datetime.now(timezone.utc)
        self.is_physical = True
        self.location = book.location or ""
        self.quantity = book.quantity or 1

    @property
    def authors(self):
        authors = []
        for name in (self.book.authors or "").split(","):
            name = name.strip()
            if name:
                authors.append(_SimpleEntity(name, phys_id("author", name)))
        return authors

    @property
    def series(self):
        if not (self.book.series or "").strip():
            return []
        name = self.book.series.strip()
        return [_SimpleEntity(name, phys_id("series", name))]

    @property
    def series_index(self):
        return self.book.series_index or 0.0

    @property
    def ratings(self):
        if not (self.book.rating or 0) > 0:
            return []
        return [_SimpleRating(float(self.book.rating))]

    @property
    def data(self):
        return []


def wrap_physical(book):
    return PhysicalEntryRow(Books=PhysicalBookView(book), is_archived=False, read_status=False)


def _split_values(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def physical_by_author(books, name):
    name_l = name.lower()
    return [b for b in books if name_l in [a.lower() for a in _split_values(b.authors)]]


def physical_by_category(books, name):
    name_l = name.lower()
    return [b for b in books if name_l in [c.lower() for c in _split_values(b.categories)]]


def physical_by_series(books, name):
    name_l = name.lower()
    return [b for b in books if (b.series or "").strip().lower() == name_l]


def physical_by_publisher(books, name):
    name_l = name.lower()
    return [b for b in books if (b.publisher or "").strip().lower() == name_l]


def physical_by_rating(books, stars):
    return [b for b in books if round(b.rating or 0) == int(stars)]


def physical_by_format(books, fmt):
    fmt_l = fmt.lower()
    return [b for b in books if (b.format or "").strip().lower() == fmt_l]


def physical_no_value(books, kind):
    if kind == "category":
        return [b for b in books if not _split_values(b.categories)]
    if kind == "series":
        return [b for b in books if not (b.series or "").strip()]
    if kind == "publisher":
        return [b for b in books if not (b.publisher or "").strip()]
    if kind == "format":
        return [b for b in books if not (b.format or "").strip()]
    if kind == "rating":
        return [b for b in books if not (b.rating or 0) > 0]
    return []


def physical_filter_books(books, kind, value):
    if kind == "author":
        return physical_by_author(books, value)
    if kind == "category":
        return physical_by_category(books, value)
    if kind == "series":
        return physical_by_series(books, value)
    if kind == "publisher":
        return physical_by_publisher(books, value)
    if kind == "rating":
        return physical_by_rating(books, value)
    if kind == "format":
        return physical_by_format(books, value)
    return []


def ebook_filter_for_physical(kind, value):
    """SQL filter selecting ebooks whose entity matches the given physical entity name."""
    value_l = value.lower()
    if kind == "author":
        return db.Books.authors.any(db.func.lower(db.Authors.name) == value_l)
    if kind == "category":
        return db.Books.tags.any(db.func.lower(db.Tags.name) == value_l)
    if kind == "series":
        return db.Books.series.any(db.func.lower(db.Series.name) == value_l)
    if kind == "publisher":
        return db.Books.publishers.any(db.func.lower(db.Publishers.name) == value_l)
    if kind == "rating":
        try:
            return db.Books.ratings.any(db.Ratings.rating == int(value) * 2)
        except ValueError:
            return None
    if kind == "format":
        return db.Books.data.any(db.Data.format == value.upper())
    return None


def physical_books_matching_search(term):
    term = (term or "").strip().lower()
    if not term:
        return []
    result = []
    for book in all_physical_books():
        haystack = " ".join([book.title or "", book.authors or "", book.publisher or "",
                             book.isbn or "", book.categories or "", book.series or "",
                             book.location or "", book.notes or ""]).lower()
        if term in haystack:
            result.append(book)
    return result


def physical_entities(books, kind):
    """Build [(db.Category(entity), count)] for the browse lists from physical books."""
    result = {}
    for book in books:
        if kind == "author":
            values = _split_values(book.authors)
        elif kind == "category":
            values = _split_values(book.categories)
        elif kind == "series":
            values = [book.series.strip()] if (book.series or "").strip() else []
        elif kind == "publisher":
            values = [book.publisher.strip()] if (book.publisher or "").strip() else []
        elif kind == "rating":
            values = [str(int(round(book.rating or 0)))] if (book.rating or 0) > 0 else []
        elif kind == "format":
            values = [book.format.strip()] if (book.format or "").strip() else []
        else:
            values = []
        for value in values:
            if value not in result:
                result[value] = 0
            result[value] += 1
    entities = []
    for name, count in result.items():
        entity_id = phys_id(kind, name)
        rating = None
        if kind == "rating":
            try:
                # db.Ratings uses a 2-10 scale; keep the physical entries comparable
                rating = int(name) * 2
            except ValueError:
                rating = None
        entities.append([db.Category(name, entity_id, rating), count])
    return entities


def merged_pagination(merged, page, per_page):
    from .pagination import Pagination
    return Pagination(page, per_page, merged["total"])


def fill_indexpage_merged(page, per_page, physical_books, order_name, fill_fn):
    """Merge physical books into a calibre fill_indexpage result.

    fill_fn(offset, limit, total_count) must return (entries, random, pagination)
    and may reuse a precomputed total_count to avoid a second COUNT query.
    """
    _, random, pagination = fill_fn(0, 0, None)
    merged = merge_pages(page, per_page, pagination.total_count, physical_books)
    entries, _, _ = fill_fn(merged["ebook_offset"], merged["ebook_limit"], pagination.total_count)
    entries = build_page(page, per_page, entries, merged)
    return entries, random, merged_pagination(merged, page, per_page)
