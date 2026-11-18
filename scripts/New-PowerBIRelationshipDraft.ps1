param([string]$FromTable, [string]$FromColumn, [string]$ToTable, [string]$ToColumn, [ValidateSet('manyToOne','oneToOne')][string]$Cardinality = 'manyToOne', [ValidateSet('oneDirection','bothDirections')][string]$CrossFilteringBehavior = 'oneDirection', [switch]$Inactive, [string]$OutputPath, [switch]$Json)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$name = [guid]::NewGuid().ToString()
$lines = @("relationship $name")
if ($Inactive) { $lines += "`tisActive: false" }
if ($CrossFilteringBehavior -eq 'bothDirections') { $lines += "`tcrossFilteringBehavior: bothDirections" }
if ($Cardinality -eq 'oneToOne') { $lines += "`ttoCardinality: one"; $lines += "`tfromCardinality: one" }
$lines += ("`tfromColumn: {0}.{1}" -f (ConvertTo-PbiTmdlName $FromTable), (ConvertTo-PbiTmdlName $FromColumn))
$lines += ("`ttoColumn: {0}.{1}" -f (ConvertTo-PbiTmdlName $ToTable), (ConvertTo-PbiTmdlName $ToColumn))
$tmdl = $lines -join "`n"
$result = [pscustomobject]@{ schema = 'codex.powerbi.relationshipDraft.v1'; objectType = 'Relationship'; relationshipName = $name; from = "$FromTable[$FromColumn]"; to = "$ToTable[$ToColumn]"; cardinality = $Cardinality; crossFilteringBehavior = $CrossFilteringBehavior; isActive = (-not $Inactive); tmdl = $tmdl; safety = 'Draft only. Validate ambiguity and filter direction before applying (Apply-PowerBIPBIPTmdlDraft.ps1 -ObjectType Relationship, dry run first).' }
if ($Json) { $text = $result | ConvertTo-Json -Depth 6; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }
$result
