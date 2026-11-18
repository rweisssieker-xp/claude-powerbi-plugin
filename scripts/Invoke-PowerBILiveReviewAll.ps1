param([string]$OutputDirectory = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'PowerBI-Live-Review'), [string]$Title, [switch]$Json)
# Read-only live review of every model open in Power BI Desktop (or the one whose window title matches -Title).
# One sub-folder per model: environment, live auto review, VertiPaq, metadata governance.
$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
& (Join-Path $scriptRoot 'Test-PowerBIEnvironment.ps1') | Set-Content -LiteralPath (Join-Path $OutputDirectory 'environment.txt') -Encoding UTF8
$resolution = & (Join-Path $scriptRoot 'Resolve-PowerBILiveTarget.ps1') -Json | ConvertFrom-Json
$resolution | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'live-targets.json') -Encoding UTF8
$targets = @($resolution.candidates | Where-Object { $_.isListening -and $_.connectionString })
if ($Title) { $targets = @($targets | Where-Object { $_.title -like "*$Title*" }) }
$results = New-Object System.Collections.Generic.List[object]
foreach ($t in $targets) {
    $name = if ($t.title) { $t.title } else { "port-$($t.port)" }
    $safe = ($name -replace '[\\/:*?"<>|]', '_').Trim()
    $dir = Join-Path $OutputDirectory $safe
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $status = 'Reviewed'; $errors = @()
    try { & (Join-Path $scriptRoot 'Invoke-PowerBILiveAutoReview.ps1') -Server $t.connectionString -OutputDirectory (Join-Path $dir 'live-auto-review') | Out-Null } catch { $status = 'Partial'; $errors += "auto review: $($_.Exception.Message)" }
    try { & (Join-Path $scriptRoot 'Get-PowerBILiveVertiPaqAnalyzer.ps1') -Server $t.connectionString -OutputPath (Join-Path $dir 'vertipaq.md') | Out-Null } catch { $status = 'Partial'; $errors += "vertipaq: $($_.Exception.Message)" }
    try { & (Join-Path $scriptRoot 'Test-PowerBILiveMetadataGovernance.ps1') -Server $t.connectionString -OutputPath (Join-Path $dir 'metadata-governance.md') | Out-Null } catch { $status = 'Partial'; $errors += "governance: $($_.Exception.Message)" }
    $results.Add([pscustomobject]@{ model = $name; server = $t.connectionString; status = $status; folder = $dir; errors = $errors })
}
$summary = [pscustomobject]@{
    schema = 'claude.powerbi.liveReviewAll.v1'
    generated = (Get-Date).ToString('s')
    outputDirectory = $OutputDirectory
    modelCount = $results.Count
    models = @($results.ToArray())
    note = $(if ($results.Count -eq 0) { 'No open Power BI Desktop model found. Open a .pbix or .pbip in Power BI Desktop and run again.' } else { 'Read-only. Nothing was changed in Power BI Desktop.' })
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'summary.json') -Encoding UTF8
$md = @('# Power BI Live Review', '', "Models reviewed: $($results.Count)", '') + @($results | ForEach-Object { "- **$($_.model)** ($($_.server)): $($_.status) - [auto review]($([uri]::EscapeDataString((Split-Path -Leaf $_.folder)))/live-auto-review/README.md), [VertiPaq]($([uri]::EscapeDataString((Split-Path -Leaf $_.folder)))/vertipaq.md)" + $(if ($_.errors.Count) { ' - ' + ($_.errors -join '; ') } else { '' }) }) + @('', $summary.note)
($md -join [Environment]::NewLine) | Set-Content -LiteralPath (Join-Path $OutputDirectory 'index.md') -Encoding UTF8
if ($Json) { $summary | ConvertTo-Json -Depth 6; return }
$summary
