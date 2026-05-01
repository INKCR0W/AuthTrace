# AuthTrace Backend

## 本地启动

1. 启动数据库
2. 使用 `uv` 创建环境并安装依赖
3. 执行 Alembic 迁移
4. 启动 FastAPI

```powershell
docker compose up -d
cd backend
uv python install 3.14.4
uv sync --dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

健康检查：

- `GET /health`
- `GET /api/v1/health`

## 常用命令

```powershell
uv python install 3.14.4
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

说明：

- 默认使用项目内 `.venv`
- 依赖锁文件使用 `uv.lock`
- 项目默认 Python 版本为 `3.14.4`
