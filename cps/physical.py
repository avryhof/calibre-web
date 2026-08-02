# -*- coding: utf-8 -*-

#  Physical book collection management for Calibre-Web.
#  Physical books are stored in Calibre-Web's own user database, separate from the
#  ebook library. Books can be added by ISBN (with metadata lookup and barcode scanning)
#  and may optionally be linked to an existing digital edition in the ebook library.

import io
import mimetypes

from flask import Blueprint, request, redirect, url_for, flash, abort, send_file
from flask_babel import gettext as _
from sqlalchemy.exc import IntegrityError, InvalidRequestError, OperationalError
from sqlalchemy.sql.expression import or_

from . import config, constants, logger, ub
from . import calibre_db, db
from .helper import get_cover_bytes
from .pagination import Pagination
from .render_template import render_title_template
from .services.Metadata import Metadata
from .usermanagement import user_login_required


physical = Blueprint("physical", __name__)

log = logger.create()


def _clean_isbn(value):
    if not value:
        return ""
    if Metadata.is_isbn(value):
        return Metadata.clean_isbn(value)
    return value.replace("-", "").replace(" ", "")


def _apply_form(book):
    """Fill a PhysicalBook instance from request.form."""
    book.isbn = _clean_isbn(request.form.get("isbn", ""))
    book.title = request.form.get("title", "").strip()
    book.authors = request.form.get("authors", "").strip()
    book.publisher = request.form.get("publisher", "").strip()
    book.published_date = request.form.get("published_date", "").strip()
    book.format = request.form.get("format", "").strip()
    book.location = request.form.get("location", "").strip()
    book.notes = request.form.get("notes", "").strip()
    try:
        book.quantity = max(1, int(request.form.get("quantity", 1)))
    except (TypeError, ValueError):
        book.quantity = 1
    ebook_id = request.form.get("ebook_id", "").strip()
    book.ebook_id = int(ebook_id) if ebook_id.isdigit() else None
    _apply_cover(book)


def _apply_cover(book):
    file = request.files.get("cover")
    if file and file.filename:
        book.cover = file.read()
        book.cover_mime = file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg"
    else:
        cover_url = request.form.get("cover_url", "").strip()
        if cover_url.startswith(("http://", "https://")):
            data, mime = get_cover_bytes(cover_url)
            if data:
                book.cover = data
                book.cover_mime = mime or "image/jpeg"
            else:
                log.warning("Could not download physical book cover from %s", cover_url)


@physical.route("/physical")
@physical.route("/physical/page/<int:page>")
@user_login_required
def books(page=1):
    query = request.args.get("query", "").strip()
    per_page = config.config_books_per_page
    q = ub.session.query(ub.PhysicalBook)
    if query:
        like = "%" + query + "%"
        q = q.filter(or_(ub.PhysicalBook.title.ilike(like),
                         ub.PhysicalBook.authors.ilike(like),
                         ub.PhysicalBook.publisher.ilike(like),
                         ub.PhysicalBook.isbn.ilike(like)))
    total_count = q.count()
    entries = q.order_by(ub.PhysicalBook.last_modified.desc(),
                         ub.PhysicalBook.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    pagination = Pagination(page, per_page, total_count)
    return render_title_template('physical/index.html',
                                 entries=entries,
                                 pagination=pagination,
                                 query=query,
                                 title=_("Physical Books"),
                                 page="physical")


@physical.route("/physical/add", methods=["GET", "POST"])
@user_login_required
def add():
    if request.method == "POST":
        book = ub.PhysicalBook()
        _apply_form(book)
        if not book.title and not book.isbn:
            flash(_("Please provide at least a title or an ISBN"), category="error")
            return render_title_template('physical/add_edit.html', book=book, title=_("Add Physical Book"),
                                         page="physical")
        if book.isbn:
            existing = ub.session.query(ub.PhysicalBook).filter(ub.PhysicalBook.isbn == book.isbn).first()
            if existing:
                flash(_("A physical book with this ISBN already exists"), category="error")
                return redirect(url_for('physical.detail', physical_id=existing.id))
        try:
            ub.session.add(book)
            ub.session.commit()
        except (OperationalError, IntegrityError, InvalidRequestError) as e:
            ub.session.rollback()
            log.error_or_exception(e)
            flash(_("An unknown error occurred, please reload the page and try again"), category="error")
            return render_title_template('physical/add_edit.html', book=book, title=_("Add Physical Book"),
                                         page="physical")
        flash(_("Physical book added"))
        return redirect(url_for('physical.detail', physical_id=book.id))
    return render_title_template('physical/add_edit.html', book=None, title=_("Add Physical Book"), page="physical")


@physical.route("/physical/detail/<int:physical_id>")
@user_login_required
def detail(physical_id):
    book = ub.session.query(ub.PhysicalBook).filter(ub.PhysicalBook.id == physical_id).first()
    if not book:
        abort(404)
    ebook = None
    if book.ebook_id:
        ebook = calibre_db.session.query(db.Books).filter(db.Books.id == book.ebook_id).first()
    return render_title_template('physical/detail.html',
                                 book=book,
                                 ebook=ebook,
                                 title=book.title or _("Physical Book"),
                                 page="physical")


@physical.route("/physical/edit/<int:physical_id>", methods=["GET", "POST"])
@user_login_required
def edit(physical_id):
    book = ub.session.query(ub.PhysicalBook).filter(ub.PhysicalBook.id == physical_id).first()
    if not book:
        abort(404)
    if request.method == "POST":
        old_isbn = book.isbn
        _apply_form(book)
        if not book.title and not book.isbn:
            flash(_("Please provide at least a title or an ISBN"), category="error")
            return render_title_template('physical/add_edit.html', book=book, title=_("Edit Physical Book"),
                                         page="physical")
        if book.isbn and book.isbn != old_isbn:
            existing = ub.session.query(ub.PhysicalBook).filter(
                ub.PhysicalBook.isbn == book.isbn,
                ub.PhysicalBook.id != physical_id).first()
            if existing:
                flash(_("A physical book with this ISBN already exists"), category="error")
                return redirect(url_for('physical.detail', physical_id=existing.id))
        try:
            ub.session.commit()
        except (OperationalError, IntegrityError, InvalidRequestError) as e:
            ub.session.rollback()
            log.error_or_exception(e)
            flash(_("An unknown error occurred, please reload the page and try again"), category="error")
            return render_title_template('physical/add_edit.html', book=book, title=_("Edit Physical Book"),
                                         page="physical")
        flash(_("Physical book updated"))
        return redirect(url_for('physical.detail', physical_id=book.id))
    return render_title_template('physical/add_edit.html', book=book, title=_("Edit Physical Book"), page="physical")


@physical.route("/physical/delete/<int:physical_id>", methods=["POST"])
@user_login_required
def delete(physical_id):
    book = ub.session.query(ub.PhysicalBook).filter(ub.PhysicalBook.id == physical_id).first()
    if not book:
        abort(404)
    try:
        ub.session.delete(book)
        ub.session.commit()
    except (OperationalError, IntegrityError, InvalidRequestError) as e:
        ub.session.rollback()
        log.error_or_exception(e)
        flash(_("An unknown error occurred, please reload the page and try again"), category="error")
        return redirect(url_for('physical.detail', physical_id=physical_id))
    flash(_("Physical book deleted"))
    return redirect(url_for('physical.books'))


@physical.route("/physical/cover/<int:physical_id>")
@physical.route("/physical/cover/<int:physical_id>/<c>")
@user_login_required
def cover(physical_id, c=None):
    book = ub.session.query(ub.PhysicalBook).filter(ub.PhysicalBook.id == physical_id).first()
    if not book or not book.cover:
        return redirect(url_for('static', filename='generic_cover.jpg'))
    return send_file(io.BytesIO(book.cover), mimetype=book.cover_mime or 'image/jpeg')
