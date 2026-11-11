"""Vercel serverless entry point. Vercel's Python runtime serves the WSGI `app`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apex import create_app  # noqa: E402

_ENTRY_PREFIXES = ("/api/index.py", "/api/index")


class _StripEntryPath:
    """If the platform forwards the function path (/api/index...) instead of the visitor's URL,
    strip it so Flask routes still match. A no-op when the original path is passed through."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        for prefix in _ENTRY_PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                environ["PATH_INFO"] = path[len(prefix):] or "/"
                break
        return self.wsgi_app(environ, start_response)


app = create_app()
app.wsgi_app = _StripEntryPath(app.wsgi_app)
