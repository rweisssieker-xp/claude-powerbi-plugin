param([string]$Path = ".", [string]$OutputPath, [switch]$Json)
$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scan = & (Join-Path $scriptRoot 'Invoke-PowerBIInsightScan.ps1') -Path $Path -Json | ConvertFrom-Json
$structure = & (Join-Path $scriptRoot 'Get-PowerBIPBIPStructure.ps1') -Path $Path -Json | ConvertFrom-Json
$catalog = & (Join-Path $scriptRoot 'New-PowerBIMetricCatalog.ps1') -Path $Path -Json | ConvertFrom-Json
$testPlan = & (Join-Path $scriptRoot 'New-PowerBIMeasureTestPlan.ps1') -Path $Path -Json | ConvertFrom-Json
$risky = @($catalog.metrics | Where-Object { @($_.risks).Count -gt 0 }).Count
$metricTotal = [math]::Max(1, @($catalog.metrics).Count)
$undefined = @($catalog.metrics | Where-Object { $_.businessDefinition -match 'TODO' }).Count
$noOwner = @($catalog.metrics | Where-Object { $_.owner -match 'TODO' }).Count
# Shares instead of per-measure deductions, so the size of the model does not decide the score.
$scores = [ordered]@{
    DaxQuality = [int][math]::Round([math]::Max(0, 100 - (100 * $risky / $metricTotal)))
    MetadataQuality = [int][math]::Round([math]::Max(0, 100 - (70 * $undefined / $metricTotal) - (30 * $noOwner / $metricTotal)))
    PbipReadiness = [int]$structure.score
    PerformanceRisk = [math]::Max(0, 100 - ($scan.riskScore * 5))
    # Designed tests per measure (3 expected). Generated drafts, not executed tests: run them with Invoke-PowerBISemanticTestRunner.ps1.
    TestPlanCoverage = [math]::Min(100, [int](($testPlan.testCount / [math]::Max(1, $catalog.metricCount * 3)) * 100))
}
$overall = [int](($scores.Values | Measure-Object -Average).Average)
$result = [pscustomobject]@{ schema = 'codex.powerbi.modelGovernanceScorecard.v1'; root = $catalog.root; generated = (Get-Date).ToString('s'); overallScore = $overall; scores = $scores; recommendation = $(if ($overall -ge 80) { 'Release candidate after business sign-off.' } elseif ($overall -ge 60) { 'Address high-priority findings before release.' } else { 'Stabilize model before publishing.' }) }
if ($Json) { $text = $result | ConvertTo-Json -Depth 6; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }
$md = @('# Power BI Model Governance Scorecard', '', "Overall score: **$overall**", '', '## Scores') + @($scores.GetEnumerator() | ForEach-Object { "- $($_.Key): $($_.Value)" }) + @('', "Recommendation: $($result.recommendation)", '', 'TestPlanCoverage counts designed test drafts; it does not show that tests have run. Run Invoke-PowerBISemanticTestRunner.ps1 against the open model for executed results.')
$content = ($md -join [Environment]::NewLine) + [Environment]::NewLine
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8 }
$content

