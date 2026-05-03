[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ProjectRoot,
    [string]$OutputDirectory,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

if (-not $OutputDirectory) {
    $envFilePath = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFilePath) {
        $backupLine = Select-String -Path $envFilePath -Pattern "^AUTHTRACE_BACKUP_DIR=(.+)$" | Select-Object -First 1
        if ($backupLine) {
            $configuredDirectory = $backupLine.Matches[0].Groups[1].Value.Trim().Trim('"')
            $OutputDirectory = if ([System.IO.Path]::IsPathRooted($configuredDirectory)) {
                $configuredDirectory
            }
            else {
                Join-Path $ProjectRoot $configuredDirectory
            }
        }
    }
}

if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $ProjectRoot "backups"
}

$resolvedOutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = Join-Path $resolvedOutputDirectory "authtrace-postgres-$timestamp.sql"
$containerBackupFile = "/tmp/authtrace-backup-$timestamp.sql"

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

    if ($PSCmdlet.ShouldProcess($backupFile, "创建 PostgreSQL 备份")) {
        if (-not (Test-Path $resolvedOutputDirectory)) {
            New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null
        }

        if ((Test-Path $backupFile) -and -not $Force) {
            throw "备份文件已存在：$backupFile"
        }

        try {
            & docker compose exec -T postgres sh -lc "pg_dump --clean --if-exists --no-owner --no-privileges -U `"`$POSTGRES_USER`" `"`$POSTGRES_DB`" -f '$containerBackupFile'"
            if ($LASTEXITCODE -ne 0) {
                throw "数据库备份失败"
            }

            & docker compose cp "postgres:$containerBackupFile" $backupFile
            if ($LASTEXITCODE -ne 0) {
                throw "备份文件复制到宿主机失败"
            }
        }
        catch {
            if (Test-Path $backupFile) {
                Remove-Item -LiteralPath $backupFile -Force -ErrorAction SilentlyContinue
            }
            throw
        }
        finally {
            & docker compose exec -T postgres sh -lc "rm -f '$containerBackupFile'" | Out-Null
        }

        Write-Host "备份完成：$backupFile"
    }
}
finally {
    Pop-Location
}
