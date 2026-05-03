[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ProjectRoot,
    [int]$CommandTimeoutSeconds,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$commonScriptPath = Join-Path $PSScriptRoot "common.ps1"
. $commonScriptPath

$resolvedCommandTimeoutSeconds = Resolve-AuthTraceCommandTimeoutSeconds -ProjectRoot $ProjectRoot -PreferredTimeoutSeconds $CommandTimeoutSeconds

Push-Location $ProjectRoot
try {
    if ($PSCmdlet.ShouldProcess($ProjectRoot, "校验 compose 配置")) {
        Invoke-DockerComposeCommand `
            -ProjectRoot $ProjectRoot `
            -Arguments @("config") `
            -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null
    }

    if (-not $SkipBuild) {
        if ($PSCmdlet.ShouldProcess($ProjectRoot, "构建并重启 AuthTrace 服务")) {
            Invoke-DockerComposeCommand `
                -ProjectRoot $ProjectRoot `
                -Arguments @("up", "-d", "--build", "--remove-orphans") `
                -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null
        }
    }
    elseif ($PSCmdlet.ShouldProcess($ProjectRoot, "重启 AuthTrace 服务")) {
        Invoke-DockerComposeCommand `
            -ProjectRoot $ProjectRoot `
            -Arguments @("up", "-d", "--remove-orphans") `
            -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null
    }

    if ($PSCmdlet.ShouldProcess($ProjectRoot, "查看 compose 服务状态")) {
        Invoke-DockerCommand `
            -ProjectRoot $ProjectRoot `
            -Arguments @("ps", "-a", "--filter", "name=authtrace-", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}") `
            -TimeoutSeconds $resolvedCommandTimeoutSeconds | Out-Null
    }
}
finally {
    Pop-Location
}
