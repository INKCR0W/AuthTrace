[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$resolvedBackupFile = [System.IO.Path]::GetFullPath($BackupFile)
if (-not (Test-Path $resolvedBackupFile)) {
    throw "备份文件不存在：$resolvedBackupFile"
}

$containerBackupFile = "/tmp/authtrace-restore-$([System.Guid]::NewGuid().ToString('N')).sql"

Push-Location $ProjectRoot
try {
    $runningServices = & docker compose ps --services --status running
    if ($LASTEXITCODE -ne 0) {
        throw "无法确认 compose 服务状态"
    }

    if ($runningServices -notcontains "postgres") {
        throw "postgres 服务未运行，请先执行 docker compose up -d postgres 或启动整套服务"
    }

    & docker compose exec -T postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
    if ($LASTEXITCODE -ne 0) {
        throw "postgres 尚未 ready，请稍后重试"
    }

    if ($PSCmdlet.ShouldProcess($resolvedBackupFile, "恢复 PostgreSQL 数据库")) {
        & docker compose cp $resolvedBackupFile "postgres:$containerBackupFile"
        if ($LASTEXITCODE -ne 0) {
            throw "备份文件复制到容器失败"
        }

        try {
            & docker compose exec -T postgres sh -lc "psql -v ON_ERROR_STOP=1 -U `"`$POSTGRES_USER`" `"`$POSTGRES_DB`" -f '$containerBackupFile'"
            if ($LASTEXITCODE -ne 0) {
                throw "数据库恢复失败"
            }
        }
        finally {
            & docker compose exec -T postgres sh -lc "rm -f '$containerBackupFile'" | Out-Null
        }

        Write-Host "恢复完成：$resolvedBackupFile"
    }
}
finally {
    Pop-Location
}
