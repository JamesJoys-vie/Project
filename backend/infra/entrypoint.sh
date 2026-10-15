#!/bin/sh
set -e
# Apply DB migrations first if this service has any (alembic.ini present)
if [ -f alembic.ini ]; then
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
