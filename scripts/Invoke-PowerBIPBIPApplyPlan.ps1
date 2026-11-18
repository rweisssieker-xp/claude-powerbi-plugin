param([string]$PbipPath, [string]$OutputPath, [switch]$Json)
$ErrorActionPreference = 'Stop'
$root = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PbipPath)
$artifacts = @()
$applyManifest = Join-Path $root '.pbip-apply/manifest.json'
if (Test-Path -LiteralPath $applyManifest) {
    try {
        $artifacts += @((Get-Content -Raw -LiteralPath $applyManifest | ConvertFrom-Json).changes | Where-Object { $_.objectType -ne 'Undo' } | ForEach-Object {
            [pscustomobject]@{ objectName = $_.objectName; objectType = $_.objectType; path = (Join-Path $root $_.file); applied = $_.at; action = $_.action; backupId = $_.id }
        })
    } catch {}
}
$draftManifest = Join-Path $root 'SemanticModel/drafts/draft-manifest.json'
if (Test-Path -LiteralPath $draftManifest) {
    try { $artifacts += @((Get-Content -Raw -LiteralPath $draftManifest | ConvertFrom-Json).artifacts) } catch {}
}
$queryRoot = Join-Path $root 'SemanticModel/queries'
if (Test-Path -LiteralPath $queryRoot) {
    $artifacts += @(Get-ChildItem -LiteralPath $queryRoot -File -Filter *.pq | ForEach-Object { [pscustomobject]@{ objectName = $_.BaseName; objectType = 'PowerQuery'; path = $_.FullName; applied = $null } })
}
$reportPages = Join-Path $root 'Report/pages'
if (Test-Path -LiteralPath $reportPages) {
    $artifacts += @(Get-ChildItem -LiteralPath $reportPages -Recurse -File -Filter page.json | ForEach-Object { [pscustomobject]@{ objectName = Split-Path -Leaf (Split-Path -Parent $_.FullName); objectType = 'ReportPage'; path = $_.FullName; applied = $null } })
}
$result = [pscustomobject]@{ schema = 'codex.powerbi.pbipApplyPlan.v1'; pbipPath = $root; generated = (Get-Date).ToString('s'); artifactCount = @($artifacts).Count; artifacts = @($artifacts); validationSteps = @('Close and reopen the .pbip in Power BI Desktop (it validates TMDL on open).', 'Refresh calculated objects when Desktop asks.', 'Run generated DAX tests or Test-PowerBILiveMeasures.ps1.', 'Run Trust Release Gate.', 'Rollback if needed: Undo-PowerBIPBIPApply.ps1 -PbipPath <project> -Apply.') }
if ($Json) { $text = $result | ConvertTo-Json -Depth 8; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }
$result

