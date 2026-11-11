# APEX — agent notes

- Stack: Python/Flask + Jinja templates, vanilla CSS/JS, Supabase (PostgREST + Auth via `requests`), Vercel. No Node.js.
- Venv: `.\.venv\Scripts\python` (Windows). Install: `.\.venv\Scripts\pip install -r requirements.txt`
- Tests: `.\.venv\Scripts\python -m unittest discover -s tests -t .` (uses `tests/fake_supabase.py`; patch list in `tests/base.py`
  — any new module that does `from .supabase import supabase` must be added to `PATCHED_MODULES`).
- DB validation: `.\.venv\Scripts\python scripts\validate_db.py` (needs `.env` with `SUPABASE_SECRET_KEY`)
- Schema changes: add a new numbered file under `supabase/migrations/`; the user runs it in the Supabase SQL Editor.
- Dev server: `$env:PORT=5055; .\.venv\Scripts\python run.py` → http://127.0.0.1:5055 (port 5000 is taken by another app).
  Killing the exec shell can orphan the python child process; check `Get-NetTCPConnection -LocalPort 5055` before restarting.
- Corporate network does TLS inspection: `truststore` (imported in `apex/supabase.py`) is required for HTTPS from Python.
- `.env` is git-ignored and not readable by the agent; config template is `.env.example`.
- The publishable key has no SELECT grant on `User`/`Pend`; all table access is server-side with the secret key.
- Static assets live in `public/static` (Vercel CDN); templates in `apex/templates`. Images are web-resized copies
  of the originals in the project root.
- CSP is strict (`'self'` only): no inline scripts, no `style=` attributes in markup (CSSOM `el.style` from JS is fine).
- PowerShell here-strings via exec can hang; prefer the write/edit tools for file content.
