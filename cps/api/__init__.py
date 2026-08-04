# -*- coding: utf-8 -*-

#  FastAPI application for Calibre-Web API endpoints.
#
#  The ASGI app is mounted into the Flask WSGI stack under the /api prefix
#  (see cps/main.py). The schema browser is available at /api/docs.

from fastapi import FastAPI

from .. import logger

log = logger.create()

api = FastAPI(
    title="Calibre-Web API",
    description=(
        "FastAPI endpoints for Calibre-Web. The book shop search queries free "
        "and public-domain ebook catalogs."
    ),
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@api.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


from . import bookshop  # noqa: E402,F401
