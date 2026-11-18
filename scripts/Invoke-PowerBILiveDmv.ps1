param(
    [string]$Server,
    [string]$Query = 'SELECT * FROM $SYSTEM.DBSCHEMA_CATALOGS',
    [string]$AdomdClientPath,
    [switch]$NoFallback,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -eq 'Core' -and -not $NoFallback) {
    $argsList = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath
    )
    if ($Server) { $argsList += @('-Server', $Server) }
    if ($Query) { $argsList += @('-Query', $Query) }
    if ($AdomdClientPath) { $argsList += @('-AdomdClientPath', $AdomdClientPath) }
    if ($Json) { $argsList += '-Json' }
    $argsList += '-NoFallback'
    & powershell.exe @argsList
    exit $LASTEXITCODE
}

function Get-AdomdClientCandidates {
    # Prefer the client that ships with Power BI Desktop (classic installer or Microsoft Store edition):
    # it always matches the local engine and targets .NET Framework, so Windows PowerShell 5.1 can load it.
    $desktopBins = New-Object System.Collections.Generic.List[string]
    foreach ($root in @("$env:ProgramFiles\Microsoft Power BI Desktop\bin", "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin")) {
        if ($root) { $desktopBins.Add($root) }
    }
    if (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue) {
        $pkg = Get-AppxPackage -Name 'Microsoft.MicrosoftPowerBIDesktop' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pkg) { $desktopBins.Add((Join-Path $pkg.InstallLocation 'bin')) }
    }
    foreach ($bin in $desktopBins) {
        foreach ($name in @('Microsoft.PowerBI.AdomdClient.dll', 'Microsoft.AnalysisServices.AdomdClient.dll')) {
            Join-Path $bin $name
        }
    }
    'C:\Program Files\Microsoft.NET\ADOMD.NET\170\Microsoft.AnalysisServices.AdomdClient.dll'
    'C:\Program Files (x86)\Microsoft.NET\ADOMD.NET\170\Microsoft.AnalysisServices.AdomdClient.dll'
    'C:\Program Files\DAX Studio\bin\Microsoft.AnalysisServices.AdomdClient.dll'
    'C:\Program Files\Microsoft SQL Server Management Studio 21\Release\Common7\IDE\Microsoft.AnalysisServices.AdomdClient.dll'
    'C:\Program Files\Microsoft SQL Server Management Studio 22\Release\Common7\IDE\Microsoft.AnalysisServices.AdomdClient.dll'
}

function Find-AdomdClient {
    foreach ($candidate in Get-AdomdClientCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

function Import-AdomdClient {
    param([string]$PreferredPath)

    $tried = New-Object System.Collections.Generic.List[string]
    $paths = @()
    if ($PreferredPath) { $paths += $PreferredPath }
    $paths += @(Get-AdomdClientCandidates | Where-Object { Test-Path -LiteralPath $_ })
    foreach ($path in ($paths | Select-Object -Unique)) {
        try { Add-Type -Path $path -ErrorAction Stop } catch { $tried.Add("$path ($($_.Exception.GetType().Name))") }
        if ('Microsoft.AnalysisServices.AdomdClient.AdomdConnection' -as [type]) { return $path }
    }
    throw ('No loadable ADOMD.NET client found. Tried: ' + ($tried -join '; ') + '. Install ADOMD.NET (.NET Framework) or DAX Studio.')
}

if (-not $Server) {
    $liveScript = Join-Path $PSScriptRoot 'Get-PowerBIDesktopLiveConnection.ps1'
    $live = & $liveScript -Json | ConvertFrom-Json
    if ($live.preferredConnection -and $live.preferredConnection.ConnectionString) {
        $Server = $live.preferredConnection.ConnectionString
    }
}

if (-not $Server) {
    throw 'No live Power BI Desktop server found. Open a PBIX/PBIP in Power BI Desktop first, then retry.'
}

$AdomdClientPath = Import-AdomdClient -PreferredPath $AdomdClientPath

$connection = [Microsoft.AnalysisServices.AdomdClient.AdomdConnection]::new($Server)
$rows = New-Object System.Collections.Generic.List[object]
try {
    $connection.Open()
    $command = $connection.CreateCommand()
    $command.CommandText = $Query
    $reader = $command.ExecuteReader()
    try {
        while ($reader.Read()) {
            $row = [ordered]@{}
            for ($i = 0; $i -lt $reader.FieldCount; $i++) {
                $value = $reader.GetValue($i)
                if ($value -is [DBNull]) { $value = $null }
                $row[$reader.GetName($i)] = $value
            }
            $rows.Add([pscustomobject]$row)
        }
    }
    finally {
        $reader.Close()
    }
}
finally {
    $connection.Close()
}

$result = [pscustomobject]@{
    schema = 'codex.powerbi.liveDmv.v1'
    server = $Server
    query = $Query
    adomdClientPath = $AdomdClientPath
    rowCount = $rows.Count
    rows = @($rows.ToArray())
}

if ($Json) {
    $result | ConvertTo-Json -Depth 8
    return
}

$rows | Format-Table -AutoSize
