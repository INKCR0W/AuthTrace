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

前端本地联调默认允许：

- `http://localhost:5173`
- `http://127.0.0.1:5173`

如需调整，请修改 `.env` 中的 `AUTHTRACE_CORS_ALLOWED_ORIGINS`，使用英文逗号分隔。

健康检查：

- `GET /health`
- `GET /api/v1/health`

自动扫描配置：

- `AUTHTRACE_SCHEDULER_ENABLED=true` 时，服务启动后会按固定间隔自动触发 `/api/v1/sync/auth-files`
- `AUTHTRACE_SCHEDULER_INTERVAL_MINUTES` 用于控制扫描间隔，默认 `15`
- 若未配置完整管理端地址或 token，自动扫描不会启动，扫描任务页会显示阻塞原因

管理端请求稳定性配置：

- `AUTHTRACE_MANAGEMENT_REQUEST_RETRIES` 控制 `refresh-config`、`auth-files` 和 `api-call` 的额外重试次数，默认 `2`
- `AUTHTRACE_MANAGEMENT_RETRY_BACKOFF_SECONDS` 控制重试退避基线秒数，默认 `1`，第 N 次重试等待 `N * 基线秒数`
- 仅 `429`、`5xx` 和网络传输异常会触发自动重试，其他 `4xx` 仍按单次失败处理

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
- `POST /api/v1/sync/auth-files` 现在会执行“刷新配置 -> 同步 auth-files -> 探测 eligible 账号 usage -> 写入快照 -> 更新当前态”
- 浏览器前端联调需要配置 `AUTHTRACE_CORS_ALLOWED_ORIGINS`
