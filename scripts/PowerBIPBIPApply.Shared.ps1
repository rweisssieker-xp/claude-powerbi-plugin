# Shared helper for the PBIP apply scripts. Dot-source it: . (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
# All writes go through scripts/python/pbi_apply.py so Windows PowerShell, PowerShell 7 and Claude use one engine.

function Find-PbiPython {
    foreach ($candidate in @(@('python'), @('py', '-3'), @('python3'))) {
        $cmd = Get-Command $candidate[0] -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        # Skip the Microsoft Store alias that only opens the Store
        if ($cmd.Source -and $cmd.Source -match 'WindowsApps\\python') { continue }
        return $candidate
    }
    throw 'Python 3 was not found on PATH. The PBIP apply engine (and the AI forecast) need Python 3. Install it from python.org, then retry.'
}

function ConvertTo-PbiTmdlName {
    param([string]$Name)
    if ($Name -match '^[A-Za-z_][A-Za-z0-9_]*$') { return $Name }
    return "'" + $Name.Replace("'", "''") + "'"
}

function Invoke-PbiApply {
    param(
        [Parameter(Mandatory = $true)][string]$PbipPath,
        [Parameter(Mandatory = $true)][hashtable]$Spec,
        [switch]$Apply
    )
    $python = @(Find-PbiPython)
    $engine = Join-Path $PSScriptRoot 'python/pbi_apply.py'
    $specFile = Join-Path ([System.IO.Path]::GetTempPath()) ("pbi-apply-{0}.json" -f [guid]::NewGuid().ToString('N'))
    # JSON file instead of command-line arguments: Windows PowerShell 5.1 mangles embedded quotes in native arguments.
    [System.IO.File]::WriteAllText($specFile, ($Spec | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
    try {
        $arguments = @()
        if ($python.Count -gt 1) { $arguments += $python[1..($python.Count - 1)] }
        $arguments += @('-I', $engine, 'spec', $PbipPath, '--spec-file', $specFile)
        if ($Apply) { $arguments += '--apply' }
        $output = & $python[0] @arguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw ("pbi_apply.py failed: " + (($output | Out-String).Trim())) }
        $result = ($output | Out-String) | ConvertFrom-Json
        $root = $result.pbipPath
        if ($result.targetPath) { $result | Add-Member -NotePropertyName targetFullPath -NotePropertyValue (Join-Path $root $result.targetPath) -Force }
        if ($result.backupId) { $result | Add-Member -NotePropertyName backupPath -NotePropertyValue (Join-Path $root ".pbip-apply/backups/$($result.backupId).zip") -Force }
        return $result
    }
    finally {
        Remove-Item -LiteralPath $specFile -ErrorAction SilentlyContinue
    }
}
