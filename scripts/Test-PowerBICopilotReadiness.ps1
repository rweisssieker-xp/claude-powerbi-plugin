param([string]$Path = ".", [string]$OutputPath, [switch]$Json)
$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$catalog = & (Join-Path $scriptRoot 'New-PowerBIMetricCatalog.ps1') -Path $Path -Json | ConvertFrom-Json
# Case-sensitive: camelCase/PascalCase joins ("PreviousYear"), leading underscore, or an ID suffix.
$technical = @($catalog.metrics | Where-Object { $_.name -cmatch '^_|[a-z][A-Z]|ID$' })
# Copilot reads names and descriptions; an owner does not help it answer questions.
$todos = @($catalog.metrics | Where-Object { $_.businessDefinition -match 'TODO' })
$metricTotal = [math]::Max(1, @($catalog.metrics).Count)
# Score by share of affected measures, so the size of the model does not decide the result.
$score = [math]::Round([math]::Max(0, 100 - (40 * $technical.Count / $metricTotal) - (60 * $todos.Count / $metricTotal)))
$result = [pscustomobject]@{ schema = 'codex.powerbi.copilotReadiness.v1'; root = $catalog.root; generated = (Get-Date).ToString('s'); score = [int]$score; findingCount = $technical.Count + $todos.Count; findings = @(@($technical | ForEach-Object { [pscustomobject]@{ type = 'Technical measure name'; source = $_.name; recommendation = 'Use business-readable names or hide technical measures.' } }) + @($todos | ForEach-Object { [pscustomobject]@{ type = 'Missing semantic definition'; source = $_.name; recommendation = 'Add a description (TMDL: /// line above the measure) with business meaning and synonyms.' } })) }
if ($Json) { $text = $result | ConvertTo-Json -Depth 6; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }
$md = @('# Power BI Copilot Readiness', '', "Score: **$($result.score)**", '', '## Findings') + @($result.findings | ForEach-Object { "- $($_.type): ``$($_.source)`` - $($_.recommendation)" })
$content = ($md -join [Environment]::NewLine) + [Environment]::NewLine
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8 }
$content

