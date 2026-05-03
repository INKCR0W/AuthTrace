Set-StrictMode -Version Latest

function Get-AuthTraceEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    $envFilePath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envFilePath)) {
        return $null
    }

    $matchedLine = Select-String -Path $envFilePath -Pattern "^$([regex]::Escape($Key))=(.+)$" | Select-Object -First 1
    if (-not $matchedLine) {
        return $null
    }

    return $matchedLine.Matches[0].Groups[1].Value.Trim().Trim('"')
}

function Resolve-AuthTraceCommandTimeoutSeconds {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [int]$PreferredTimeoutSeconds
    )

    if ($PreferredTimeoutSeconds -gt 0) {
        return $PreferredTimeoutSeconds
    }

    $configuredTimeout = Get-AuthTraceEnvValue -ProjectRoot $ProjectRoot -Key "AUTHTRACE_DOCKER_COMMAND_TIMEOUT_SECONDS"
    if ($configuredTimeout) {
        $parsedTimeout = 0
        if ([int]::TryParse($configuredTimeout, [ref]$parsedTimeout) -and $parsedTimeout -gt 0) {
            return $parsedTimeout
        }
    }

    return 120
}

function Join-CommandText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    return ($FilePath, $ArgumentList) -join " "
}

function ConvertTo-ProcessArguments {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    $escapedArguments = foreach ($argument in $ArgumentList) {
        if ($argument -eq "") {
            '""'
            continue
        }

        if ($argument -notmatch '[\s"]') {
            $argument
            continue
        }

        $escaped = $argument -replace '(\\*)"', '$1$1\"'
        $escaped = $escaped -replace '(\\+)$', '$1$1'
        '"' + $escaped + '"'
    }

    return ($escapedArguments -join " ")
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [switch]$AllowNonZeroExit
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Arguments = ConvertTo-ProcessArguments -ArgumentList $ArgumentList

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $commandText = Join-CommandText -FilePath $FilePath -ArgumentList $ArgumentList

    try {
        if (-not $process.Start()) {
            throw "命令启动失败：$commandText"
        }

        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $process.Kill()
            }
            catch {
                # 进程已退出时忽略
            }

            throw "命令执行超时（${TimeoutSeconds}s）：$commandText"
        }

        $stdoutTask.Wait()
        $stderrTask.Wait()

        $result = [pscustomobject]@{
            CommandText = $commandText
            ExitCode    = $process.ExitCode
            StdOut      = $stdoutTask.Result
            StdErr      = $stderrTask.Result
        }

        if (-not $AllowNonZeroExit -and $result.ExitCode -ne 0) {
            $details = @()
            if ($result.StdOut) {
                $details += $result.StdOut.TrimEnd()
            }
            if ($result.StdErr) {
                $details += $result.StdErr.TrimEnd()
            }

            $message = "命令执行失败（退出码 $($result.ExitCode)）：$commandText"
            if ($details.Count -gt 0) {
                $message = "$message`n$($details -join [Environment]::NewLine)"
            }

            throw $message
        }

        return $result
    }
    finally {
        $process.Dispose()
    }
}

function Write-CommandStreams {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Result
    )

    if ($Result.StdOut) {
        Write-Host ($Result.StdOut.TrimEnd())
    }

    if ($Result.StdErr) {
        Write-Host ($Result.StdErr.TrimEnd())
    }
}

function Invoke-DockerComposeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [switch]$PassThru,
        [switch]$AllowNonZeroExit
    )

    $result = Invoke-ExternalCommand `
        -FilePath "docker" `
        -ArgumentList (@("compose") + $Arguments) `
        -WorkingDirectory $ProjectRoot `
        -TimeoutSeconds $TimeoutSeconds `
        -AllowNonZeroExit:$AllowNonZeroExit

    if (-not $PassThru) {
        Write-CommandStreams -Result $result
    }

    return $result
}

function Invoke-DockerCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [switch]$PassThru,
        [switch]$AllowNonZeroExit
    )

    $result = Invoke-ExternalCommand `
        -FilePath "docker" `
        -ArgumentList $Arguments `
        -WorkingDirectory $ProjectRoot `
        -TimeoutSeconds $TimeoutSeconds `
        -AllowNonZeroExit:$AllowNonZeroExit

    if (-not $PassThru) {
        Write-CommandStreams -Result $result
    }

    return $result
}

function Test-AuthTraceContainerRunning {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$ContainerName,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $result = Invoke-DockerCommand `
        -ProjectRoot $ProjectRoot `
        -Arguments @("inspect", "--format", "{{.State.Running}}", $ContainerName) `
        -TimeoutSeconds $TimeoutSeconds `
        -PassThru `
        -AllowNonZeroExit

    if ($result.ExitCode -ne 0) {
        return $false
    }

    return $result.StdOut.Trim().Equals("true", [System.StringComparison]::OrdinalIgnoreCase)
}
