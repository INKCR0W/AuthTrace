[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ProjectRoot,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

function Invoke-ComposeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') 执行失败，退出码：$LASTEXITCODE"
    }
}

Push-Location $ProjectRoot
try {
    if ($PSCmdlet.ShouldProcess($ProjectRoot, "校验 compose 配置")) {
        Invoke-ComposeCommand -Arguments @("config")
    }

    if (-not $SkipBuild) {
        if ($PSCmdlet.ShouldProcess($ProjectRoot, "构建并重启 AuthTrace 服务")) {
            Invoke-ComposeCommand -Arguments @("up", "-d", "--build", "--remove-orphans")
        }
    }
    elseif ($PSCmdlet.ShouldProcess($ProjectRoot, "重启 AuthTrace 服务")) {
        Invoke-ComposeCommand -Arguments @("up", "-d", "--remove-orphans")
    }

    if ($PSCmdlet.ShouldProcess($ProjectRoot, "查看 compose 服务状态")) {
        Invoke-ComposeCommand -Arguments @("ps")
    }
}
finally {
    Pop-Location
}
