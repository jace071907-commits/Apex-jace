"""Minimal Supabase client (PostgREST + GoTrue) built on `requests`.

All privileged calls use the secret key and run server-side only.
"""
import re

try:
    # Use the OS certificate store (required behind corporate TLS inspection; harmless on Vercel).
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import requests

from .config import Config

_TIMEOUT = 10


class SupabaseError(Exception):
    def __init__(self, status, message, code=None):
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.message = message
        self.code = code


class _Http(requests.Session):
    """Session that converts network failures (DNS, timeout, TLS) into SupabaseError."""

    def request(self, *args, **kwargs):
        try:
            return super().request(*args, **kwargs)
        except requests.RequestException as exc:
            raise SupabaseError(503, f"Network error: {exc.__class__.__name__}") from exc


_http = _Http()


def _key_headers(key):
    headers = {"apikey": key}
    # Legacy JWT keys (anon/service_role) must also be sent as a Bearer token.
    # New sb_publishable_/sb_secret_ keys are resolved by the gateway from `apikey`.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _raise_for(resp):
    if resp.ok:
        return
    try:
        body = resp.json()
    except ValueError:
        body = {}
    message = body.get("message") or body.get("msg") or body.get("error_description") or resp.text[:300]
    raise SupabaseError(resp.status_code, message, body.get("code") or body.get("error_code"))


def column(name):
    """Quote a column name for PostgREST query strings when it has spaces/special chars."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else f'"{name}"'


def eq(value):
    text = str(value)
    if re.search(r'[,.:()"\\\s]', text):
        text = '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"eq.{text}"


class Supabase:
    def __init__(self, url=None, publishable_key=None, secret_key=None):
        self.url = (url or Config.SUPABASE_URL).rstrip("/")
        self.publishable_key = publishable_key or Config.SUPABASE_PUBLISHABLE_KEY
        self.secret_key = secret_key or Config.SUPABASE_SECRET_KEY

    def _service(self, extra=None):
        if not self.secret_key:
            raise SupabaseError(500, "SUPABASE_SECRET_KEY is not configured.")
        return {**_key_headers(self.secret_key), **(extra or {})}

    def _rest(self, table):
        return f"{self.url}/rest/v1/{requests.utils.quote(table, safe='')}"

    # ---------------- PostgREST ----------------
    def select(self, table, params=None, limit=None):
        params = dict(params or {})
        params.setdefault("select", "*")
        if limit:
            params["limit"] = limit
        resp = _http.get(self._rest(table), params=params, headers=self._service(), timeout=_TIMEOUT)
        _raise_for(resp)
        return resp.json()

    def count(self, table, params=None):
        params = {"select": "*", **(params or {})}
        headers = self._service({"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
        resp = _http.get(self._rest(table), params=params, headers=headers, timeout=_TIMEOUT)
        _raise_for(resp)
        total = resp.headers.get("Content-Range", "*/0").split("/")[-1]
        return int(total) if total.isdigit() else 0

    def insert(self, table, values, on_conflict=None):
        """Insert (or upsert when `on_conflict` is given) and return the stored rows."""
        prefer = "return=representation" + (",resolution=merge-duplicates" if on_conflict else "")
        params = {"on_conflict": on_conflict} if on_conflict else None
        headers = self._service({"Prefer": prefer, "Content-Type": "application/json"})
        resp = _http.post(self._rest(table), params=params, json=values, headers=headers, timeout=_TIMEOUT)
        _raise_for(resp)
        return resp.json()

    def update(self, table, params, values):
        headers = self._service({"Prefer": "return=representation", "Content-Type": "application/json"})
        resp = _http.patch(self._rest(table), params=params, json=values, headers=headers, timeout=_TIMEOUT)
        _raise_for(resp)
        return resp.json()

    # ---------------- Supabase Auth (GoTrue) ----------------
    def sign_in(self, email, password):
        """Return the session payload on success, None for bad credentials."""
        resp = _http.post(
            f"{self.url}/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
            headers=_key_headers(self.publishable_key),
            timeout=_TIMEOUT,
        )
        if resp.status_code in (400, 401, 422):
            return None
        _raise_for(resp)
        return resp.json()

    def admin_upsert_user(self, user_id, email, password, metadata=None):
        """Create the Auth user with a deterministic id, or update it if it already exists."""
        payload = {"email": email, "password": password, "email_confirm": True, "user_metadata": metadata or {}}
        resp = _http.put(
            f"{self.url}/auth/v1/admin/users/{user_id}", json=payload, headers=self._service(), timeout=_TIMEOUT
        )
        if resp.status_code == 404:
            resp = _http.post(
                f"{self.url}/auth/v1/admin/users",
                json={"id": user_id, **payload},
                headers=self._service(),
                timeout=_TIMEOUT,
            )
        _raise_for(resp)
        return resp.json()

    def admin_update_user(self, user_id, attributes):
        resp = _http.put(
            f"{self.url}/auth/v1/admin/users/{user_id}", json=attributes, headers=self._service(), timeout=_TIMEOUT
        )
        _raise_for(resp)
        return resp.json()


supabase = Supabase()
