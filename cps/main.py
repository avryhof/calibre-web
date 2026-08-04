# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2012-2022 OzzieIsaacs
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

import sys

from . import create_app, limiter, log
from .jinjia import jinjia
from flask import request


class ApiDispatcher(object):
    """Route /api/* requests to the FastAPI app (ASGI bridged to WSGI via a2wsgi)
    and everything else to Flask.

    A `script_name` attribute is exposed so that the custom session interface
    (ScriptNameSessionInterface) keeps working: it reads `app.wsgi_app.script_name`
    when setting the session cookie path."""

    def __init__(self, flask_app, fastapi_wsgi):
        self.flask_app = flask_app
        self.fastapi_wsgi = fastapi_wsgi
        self.prefix = "/api"

    @property
    def script_name(self):
        return getattr(self.flask_app, "script_name", "/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            return self.fastapi_wsgi(environ, start_response)
        return self.flask_app(environ, start_response)


def request_username():
    return request.authorization.username if request.authorization else ""


def main():
    app = create_app()

    from .web import web
    from .basic import basic
    from .opds import opds
    from .admin import admi
    from .gdrive import gdrive
    from .editbooks import editbook
    from .about import about
    from .search import search
    from .search_metadata import meta
    from .shelf import shelf
    from .physical import physical
    from .bookshop import bookshop
    from .tasks_status import tasks
    from .error_handler import init_errorhandler
    from .remotelogin import remotelogin
    try:
        from .kobo import kobo, get_kobo_activated
        from .kobo_auth import kobo_auth
        from flask_limiter.util import get_remote_address
        kobo_available = get_kobo_activated()
    except (ImportError, AttributeError):  # Catch also error for not installed flask-WTF (missing csrf decorator)
        kobo_available = False
        kobo = kobo_auth = get_remote_address = None

    try:
        from .oauth_bb import oauth
        oauth_available = True
    except ImportError:
        oauth_available = False
        oauth = None

    from . import web_server
    init_errorhandler()

    app.register_blueprint(search)
    app.register_blueprint(tasks)
    app.register_blueprint(web)
    app.register_blueprint(basic)
    limiter.limit("3/minute", key_func=request_username)(opds)
    app.register_blueprint(opds)
    app.register_blueprint(jinjia)
    app.register_blueprint(about)
    app.register_blueprint(shelf)
    app.register_blueprint(admi)
    app.register_blueprint(remotelogin)
    app.register_blueprint(meta)
    app.register_blueprint(gdrive)
    app.register_blueprint(editbook)
    app.register_blueprint(physical)
    app.register_blueprint(bookshop)
    if kobo_available:
        limiter.limit("3/minute", key_func=get_remote_address)(kobo)
        app.register_blueprint(kobo)
        app.register_blueprint(kobo_auth)
    if oauth_available:
        app.register_blueprint(oauth)

    # Mount the FastAPI endpoints under /api (schema browser at /api/docs).
    # The mount is optional: if FastAPI is not installed the rest of the app
    # still works, and the book shop page simply cannot fetch results.
    try:
        from a2wsgi import ASGIMiddleware
        from .api import api as fastapi_app
        app.wsgi_app = ApiDispatcher(app.wsgi_app, ASGIMiddleware(fastapi_app))
        log.info("FastAPI endpoints mounted under /api")
    except Exception as e:
        log.warning("FastAPI endpoints unavailable: %s", e)

    success = web_server.start()
    sys.exit(0 if success else 1)
