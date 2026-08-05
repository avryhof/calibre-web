# -*- coding: utf-8 -*-

#  Book shop: search free / public-domain ebooks across external catalogs.
#  The results are fetched from the FastAPI endpoint mounted under /api and
#  rendered by bookshop/index.html. Providers live in cps/bookshop_provider/.

from flask import Blueprint, request

from flask_babel import gettext as _
from .cw_login import current_user
from . import config
from .render_template import render_title_template
from .services.Bookshop import get_providers
from .usermanagement import user_login_required


bookshop = Blueprint("bookshop", __name__)


@bookshop.route("/bookshop")
@user_login_required
def index():
    providers = get_providers()
    script_root = request.script_root.rstrip("/")
    allow_upload = bool(config.config_uploading and current_user.role_upload())
    return render_title_template(
        "bookshop/index.html",
        title=_("Book Shop"),
        page="bookshop",
        providers=providers,
        api_base=(script_root or "") + "/api",
        allow_upload=allow_upload,
    )
