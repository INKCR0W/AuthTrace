[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$ProjectRoot,
    [int]$CommandTimeoutSeconds
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$commonScriptPath = Join-Path $PSScriptRoot "common.ps1"
. $commonScriptPath

$resolvedBackupFile = [System.IO.Path]::GetFullPath($BackupFile)
if (-not (Test-Path $resolvedBackupFile)) {
    throw "备份文件不存在：$resolvedBackupFile"
}

$containerBackupFile = "/tmp/authtrace-restore-$([System.Guid]::NewGuid().ToString('N')).sql"
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

    if ($PSCmdlet.ShouldProcess($resolvedBackupFile, "恢复 PostgreSQL 数据库")) {
        Invoke-DockerCommand `
            -ProjectRoot $ProjectRoot `
            -Arguments @("cp", $resolvedBackupFile, "$postgresContainerName`:$containerBackupFile") `
            -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null

        try {
            Invoke-DockerCommand `
                -ProjectRoot $ProjectRoot `
                -Arguments @("exec", $postgresContainerName, "sh", "-lc", "psql -v ON_ERROR_STOP=1 -U `"`$POSTGRES_USER`" `"`$POSTGRES_DB`" -f '$containerBackupFile'") `
                -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null
        }
        finally {
            Invoke-DockerCommand `
                -ProjectRoot $ProjectRoot `
                -Arguments @("exec", $postgresContainerName, "sh", "-lc", "rm -f '$containerBackupFile'") `
                -TimeoutSeconds $resolvedCommandTimeoutSeconds `
                -AllowNonZeroExit | Out-Null
        }

        Write-Host "恢复完成：$resolvedBackupFile"
    }
}
finally {
    Pop-Location
}
