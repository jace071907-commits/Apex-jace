"""In-memory stand-in for the Supabase client, implementing the PostgREST filters APEX uses."""
import fnmatch
import itertools

from apex.supabase import Supabase

_RESERVED = {"select", "limit", "order", "offset", "on_conflict"}


def _unquote(text):
    return text[1:-1].replace('\\"', '"') if len(text) > 1 and text[0] == text[-1] == '"' else text


def _test(cell, expr):
    op, _, arg = expr.partition(".")
    if op == "not":
        return not _test(cell, arg)
    if op == "is":
        return {"null": cell is None, "false": cell is False, "true": cell is True}[arg]
    if op == "eq":
        return cell is not None and str(cell) == _unquote(arg)
    if op == "neq":  # SQL semantics: NULL is never "not equal"
        return cell is not None and str(cell) != _unquote(arg)
    if op == "ilike":
        return cell is not None and fnmatch.fnmatch(str(cell).lower(), arg.lower())
    if op in ("gte", "lte"):
        return cell is not None and (str(cell) >= arg if op == "gte" else str(cell) <= arg)
    raise ValueError(expr)


class FakeSupabase(Supabase):
    def __init__(self, tables):
        super().__init__("http://fake", "pub", "secret")
        self.tables = tables
        self.auth = {}
        self._ids = itertools.count(100)

    def _rows(self, table, params):
        rows = self.tables.setdefault(table, [])
        for key, expr in (params or {}).items():
            if key in _RESERVED:
                continue
            if key == "or":
                conds = [c.partition(".") for c in expr.strip("()").split(",")]
                rows = [r for r in rows if any(_test(r.get(col), rest) for col, _, rest in conds)]
                continue
            col = _unquote(key)
            for e in expr if isinstance(expr, list) else [expr]:
                rows = [r for r in rows if _test(r.get(col), e)]
        return rows

    def select(self, table, params=None, limit=None):
        rows = [dict(r) for r in self._rows(table, params)]
        offset = int((params or {}).get("offset", 0))
        return rows[offset:offset + limit] if limit else rows[offset:]

    def count(self, table, params=None):
        return len(self._rows(table, params))

    def insert(self, table, values, on_conflict=None):
        rows = self.tables.setdefault(table, [])
        if on_conflict:
            existing = next((r for r in rows if r.get(on_conflict) == values.get(on_conflict)), None)
            if existing:
                existing.update(values)
                return [dict(existing)]
        row = {"id": next(self._ids), "ACKNOWLEDGED": False, **values} if table == "Pend" else dict(values)
        rows.append(row)
        return [dict(row)]

    def update(self, table, params, values):
        matched = self._rows(table, params)
        for r in matched:
            r.update(values)
        return [dict(r) for r in matched]

    def sign_in(self, email, password):
        return {"access_token": "t"} if self.auth.get(email, {}).get("password") == password else None

    def admin_upsert_user(self, user_id, email, password, metadata=None):
        self.auth[email] = {"id": user_id, "password": password, "meta": metadata}
        return self.auth[email]

    def admin_update_user(self, user_id, attributes):
        return {}
