#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required: https://www.python.org/downloads/"
  exit 1
fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements.txt
if [ ! -f .form-local-secret ]; then
  python -c 'import secrets,pathlib;pathlib.Path(".form-local-secret").write_text(secrets.token_urlsafe(48))'
  chmod 600 .form-local-secret
fi
export FORM_SESSION_SECRET="$(cat .form-local-secret)"
export FORM_COOKIE_SECURE=false
export FORM_ENV=development
(sleep 2; open 'http://127.0.0.1:8000') &
echo "FORM is local to your computer at http://127.0.0.1:8000"
echo "Stop the local server with Control+C. Do not expose this development server to the internet."
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
