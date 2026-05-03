# AuthTrace

AuthTrace 是一个围绕 `Cliproxy/CLIProxy` 管理端构建的账号状态时序观测与 `401` 研究平台。当前代码已经覆盖采集、扫描、事件回放、研究页和容器化部署，首版目标是尽快稳定运行并持续积累真实样本。

## 仓库结构

- `backend/`：`FastAPI + SQLAlchemy + Alembic` 后端与调度服务
- `frontend/`：`Vue 3 + Vite + TypeScript` 前端页面
- `docker-compose.yml`：`postgres + backend + frontend` 一体化部署入口
- `scripts/`：数据库备份 / 恢复与堆栈重部署脚本
- `docs/`：需求、roadmap 和会话交接文档，仅用于本地协作，不应进入 git 提交

## 本地开发

后端本地开发说明见 [backend/README.md](backend/README.md)。如果只需要本地联调数据库：

```powershell
docker compose up -d postgres
cd backend
uv python install 3.14.4
uv sync --dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

前端本地开发：

```powershell
cd frontend
npm install
npm run dev
```

## 容器部署

1. 复制环境模板并填写真实配置。
2. 至少补齐 `AUTHTRACE_MANAGEMENT_BASE_URL` 和 `AUTHTRACE_MANAGEMENT_TOKEN`，否则自动扫描不会真正启动。
3. 启动整套服务。

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

默认入口：

- 前端：`http://127.0.0.1:8080`
- 同源 API 健康检查：`http://127.0.0.1:8080/api/v1/health`

默认部署形态下，只有前端端口绑定到宿主机本地回环地址 `127.0.0.1`；后端和数据库都不暴露宿主机端口，只允许编排内部网络访问。前端容器通过 `http://backend:8000` 调用后端，后端通过 `postgres:5432` 访问数据库。如需对局域网或反向代理开放前端入口，可显式调整 `.env` 中的 `AUTHTRACE_PUBLIC_HOST`。

## 关键环境变量

- `AUTHTRACE_MANAGEMENT_BASE_URL`：管理端地址
- `AUTHTRACE_MANAGEMENT_TOKEN`：管理端访问令牌
- `AUTHTRACE_SCHEDULER_ENABLED`：是否启用自动扫描
- `AUTHTRACE_SCHEDULER_INTERVAL_MINUTES`：扫描间隔分钟数
- `AUTHTRACE_PUBLIC_HOST`：前端宿主机监听地址，默认 `127.0.0.1`
- `AUTHTRACE_DOCKER_LOG_MAX_SIZE`：单个容器日志文件滚动阈值
- `AUTHTRACE_DOCKER_LOG_MAX_FILE`：容器日志保留份数
- `AUTHTRACE_BACKUP_DIR`：数据库备份输出目录
- `AUTHTRACE_DOCKER_COMMAND_TIMEOUT_SECONDS`：运维脚本里单条 Docker 命令的超时秒数，用于避免 Docker CLI 异常时长时间卡住

## 运维命令

查看服务状态：

```powershell
docker compose ps
```

查看最近日志：

```powershell
docker compose logs --tail=200 frontend backend postgres
```

执行数据库备份：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-postgres.ps1
```

如果宿主机 Docker 偶发卡住，可以临时缩短单条命令超时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-postgres.ps1 -CommandTimeoutSeconds 60
```

从备份恢复数据库：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-postgres.ps1 -BackupFile .\backups\authtrace-postgres-20260503-150000.sql
```

更新并重启整套服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\redeploy-stack.ps1
```

三个运维脚本都会优先读取根目录 `.env` 中的 `AUTHTRACE_DOCKER_COMMAND_TIMEOUT_SECONDS`，也支持通过 `-CommandTimeoutSeconds` 在单次执行时覆盖。

## 长期运行建议

- 上线前先在根目录 `.env` 中填写真实管理端配置，再执行一次 `docker compose up -d --build` 验证自动扫描是否正常入库。
- 至少保留一份最近数据库备份，建议在更新镜像或调整迁移前先执行一次备份。
- 当前 compose 已启用容器日志滚动，但应用日志仍主要通过 `docker compose logs` 查看；若后续要长期保留日志，建议再接宿主机日志采集或集中式日志系统。
- `docs/` 中的状态文档用于会话交接，不应加入暂存区或提交。
