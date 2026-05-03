#!/bin/sh
set -eu

python - <<'PY'
import os
import time

import psycopg

dsn = os.environ["AUTHTRACE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
attempts = int(os.getenv("AUTHTRACE_DB_WAIT_ATTEMPTS", "30"))
interval = float(os.getenv("AUTHTRACE_DB_WAIT_INTERVAL_SECONDS", "2"))
last_error = None

for attempt in range(1, attempts + 1):
    try:
        with psycopg.connect(dsn, connect_timeout=5):
            print(f"数据库连接成功，第 {attempt} 次尝试完成")
            break
    except Exception as exc:  # pragma: no cover
        last_error = exc
        print(f"等待数据库就绪（{attempt}/{attempts}）：{exc}")
        time.sleep(interval)
else:
    raise SystemExit(f"数据库在 {attempts} 次尝试后仍不可用：{last_error}")
PY

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
