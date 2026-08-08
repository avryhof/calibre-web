# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
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

import re

# ISBNs in the wild are usually preceded by the literal word "ISBN", with any
# combination of whitespace, colons or dashes between the word and the number.
# The number itself may contain separating dashes or spaces in any position.
_ISBN_CANDIDATE_RE = re.compile(
    r"(?<![0-9Xx])(?:ISBN(?:[- ]1[03])?[\s:.-]*)?([0-9][0-9\s-]{8,17}[0-9Xx])(?![0-9Xx])",
    re.IGNORECASE,
)

_ISBN10_RE = re.compile(r"^\d{9}[0-9Xx]$")
_ISBN13_RE = re.compile(r"^\d{13}$")


def normalize_isbn(value):
    """Compact an ISBN candidate to plain digits with an uppercase check digit."""
    if not value:
        return ""
    return re.sub(r"[\s-]+", "", str(value)).upper()


def is_valid_isbn(value):
    """Validate the ISBN-10 or ISBN-13 check digit of a candidate value."""
    digits = normalize_isbn(value)
    if not digits:
        return False
    if len(digits) == 10:
        return _isbn10_checksum(digits)
    if len(digits) == 13:
        return _isbn13_checksum(digits)
    return False


def extract_isbns(text):
    """Return every valid ISBN found in `text`, de-duplicated, in order of appearance."""
    if not text:
        return []
    found = []
    seen = set()
    for match in _ISBN_CANDIDATE_RE.finditer(text):
        candidate = normalize_isbn(match.group(1))
        if is_valid_isbn(candidate) and candidate not in seen:
            seen.add(candidate)
            found.append(candidate)
    return found


def isbn_from_term(term):
    """Extract the first valid ISBN embedded anywhere in a search term, or None."""
    if not term:
        return None
    isbns = extract_isbns(str(term))
    return isbns[0] if isbns else None


def preferred_isbn(values):
    """Pick the most useful ISBN from a list: prefer a valid ISBN-13, then ISBN-10."""
    valid = [v for v in values if is_valid_isbn(v)]
    if not valid:
        return None
    for v in valid:
        if len(normalize_isbn(v)) == 13:
            return normalize_isbn(v)
    return normalize_isbn(valid[0])


def _isbn10_checksum(digits):
    total = 0
    for i, char in enumerate(digits):
        value = 10 if char == "X" else int(char)
        total += value * (10 - i)
    return total % 11 == 0


def _isbn13_checksum(digits):
    total = 0
    for i, char in enumerate(digits):
        total += int(char) * (1 if i % 2 == 0 else 3)
    return total % 10 == 0
