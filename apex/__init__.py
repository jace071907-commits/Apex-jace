"""APEX application factory."""
import logging
import secrets

from flask import Flask, g, render_template, request, session

from . import dates, pends, programs, reviews, users
from .config import ROOT_DIR, Config
from .navigation import nav_for, tabs_for
from .rbac import can, is_associate
from .security import csrf_token, verify_csrf
from .supabase import SupabaseError

log = logging.getLogger("apex")

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def create_app():
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__, static_folder=str(ROOT_DIR / "public" / "static"), static_url_path="/static")
    app.config.from_object(Config)

    missing = Config.missing()
    if missing:
        log.warning("Missing environment variables: %s", ", ".join(missing))
    if not Config.SECRET_KEY:
        if Config.IS_PRODUCTION:
            raise RuntimeError("APEX_SECRET_KEY must be set in production.")
        app.config["SECRET_KEY"] = secrets.token_urlsafe(48)

    from .routes import auth_bp, di_admin_bp, di_bp, main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(di_bp)
    app.register_blueprint(di_admin_bp)
    app.jinja_env.globals.update(fmt_date=dates.display, fmt_datetime=dates.display_datetime, today=dates.today)

    app.before_request(verify_csrf)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if Config.IS_PRODUCTION:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.endpoint and request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def inject():
        role = getattr(g, "role", None)
        program = session.get("program") if role else None
        user_row = getattr(g, "user_row", None)
        in_di = user_row is not None and program == "di"
        return {
            "csrf_token": csrf_token,
            "nav_items": nav_for(role, program) if role else [],
            "module_tabs": tabs_for(program, role),
            "module_blueprints": ("di", "dia"),
            "current_program": programs.BY_KEY.get(program),
            "current_role": role,
            "current_profile": getattr(g, "profile", []),
            "profile_map": getattr(g, "profile_map", {}),
            "portal": getattr(g, "portal", None),
            "prefs": session.get("prefs") if role else None,
            "unacknowledged": pends.unacknowledged_count(users.domain_of(user_row))
            if in_di and is_associate(role) else 0,
            "review_queue": _queue_count() if in_di and can(role, "dia.pend_reports") else 0,
        }

    def _queue_count():
        try:
            return reviews.queue_count()
        except SupabaseError as exc:
            log.warning("Review queue count unavailable: %s", exc)
            return 0

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def error_page(err):
        code = getattr(err, "code", 500) or 500
        titles = {400: "Bad Request", 403: "Access Denied", 404: "Page Not Found", 500: "Something Went Wrong"}
        messages = {
            403: "Your role does not have permission to view this page.",
            404: "The page you are looking for does not exist.",
            500: "An unexpected error occurred. Please try again.",
        }
        message = getattr(err, "description", None) if code == 400 else messages.get(code)
        return render_template("error.html", code=code, title=titles.get(code, "Error"), message=message), code

    return app
