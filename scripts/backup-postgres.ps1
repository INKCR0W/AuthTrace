[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ProjectRoot,
    [string]$OutputDirectory,
    [int]$CommandTimeoutSeconds,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$commonScriptPath = Join-Path $PSScriptRoot "common.ps1"
. $commonScriptPath

if (-not $OutputDirectory) {
    $configuredDirectory = Get-AuthTraceEnvValue -ProjectRoot $ProjectRoot -Key "AUTHTRACE_BACKUP_DIR"
    if ($configuredDirectory) {
        $OutputDirectory = if ([System.IO.Path]::IsPathRooted($configuredDirectory)) {
            $configuredDirectory
        }
        else {
            Join-Path $ProjectRoot $configuredDirectory
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
$postgresContainerName = "authtrace-postgres"
$resolvedCommandTimeoutSeconds = Resolve-AuthTraceCommandTimeoutSeconds -ProjectRoot $ProjectRoot -PreferredTimeoutSeconds $CommandTimeoutSeconds

Push-Location $ProjectRoot
try {
    if (-not (Test-AuthTraceContainerRunning -ProjectRoot $ProjectRoot -ContainerName $postgresContainerName -TimeoutSeconds $resolvedCommandTimeoutSeconds)) {
        throw "postgres 容器未运行，请先执行 docker compose up -d postgres 或启动整套服务"
    }

    Invoke-DockerCommand `
        -ProjectRoot $ProjectRoot `
        -Arguments @("exec", $postgresContainerName, "sh", "-lc", 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"') `
        -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null

    if ($PSCmdlet.ShouldProcess($backupFile, "创建 PostgreSQL 备份")) {
        if (-not (Test-Path $resolvedOutputDirectory)) {
            New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null
        }

        if ((Test-Path $backupFile) -and -not $Force) {
            throw "备份文件已存在：$backupFile"
        }

        try {
            Invoke-DockerCommand `
                -ProjectRoot $ProjectRoot `
                -Arguments @("exec", $postgresContainerName, "sh", "-lc", "pg_dump --clean --if-exists --no-owner --no-privileges -U `"`$POSTGRES_USER`" `"`$POSTGRES_DB`" -f '$containerBackupFile'") `
                -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null

            Invoke-DockerCommand `
                -ProjectRoot $ProjectRoot `
                -Arguments @("cp", "$postgresContainerName`:$containerBackupFile", $backupFile) `
                -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null
        }
        catch {
            if (Test-Path $backupFile) {
                Remove-Item -LiteralPath $backupFile -Force -ErrorAction SilentlyContinue
            }
            throw
        }
        finally {
            Invoke-DockerCommand `
                -ProjectRoot $ProjectRoot `
                -Arguments @("exec", $postgresContainerName, "sh", "-lc", "rm -f '$containerBackupFile'") `
                -TimeoutSeconds $resolvedCommandTimeoutSeconds `
                -AllowNonZeroExit | Out-Null
        }

        Write-Host "备份完成：$backupFile"
    }
}
finally {
    Pop-Location
}
