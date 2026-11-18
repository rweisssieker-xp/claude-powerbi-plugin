param([string]$RoleName = 'Sales Region Access', [string]$TableName, [string]$FilterExpression, [string]$OutputPath, [switch]$Json)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$filterLines = @($FilterExpression.Trim() -split "`r?`n")
$lines = @(("role {0}" -f (ConvertTo-PbiTmdlName $RoleName)), "`tmodelPermission: read", '')
if ($filterLines.Count -eq 1) {
    $lines += ("`ttablePermission {0} = {1}" -f (ConvertTo-PbiTmdlName $TableName), $filterLines[0])
}
else {
    $lines += ("`ttablePermission {0} =" -f (ConvertTo-PbiTmdlName $TableName))
    $lines += @($filterLines | ForEach-Object { "`t`t`t" + $_.TrimEnd() })
}
$tmdl = $lines -join "`n"
$result = [pscustomobject]@{ schema = 'codex.powerbi.rlsRoleDraft.v1'; objectType = 'RLSRole'; roleName = $RoleName; tableName = $TableName; filterExpression = $FilterExpression; tmdl = $tmdl; validation = 'Validate with View As Role in Power BI Desktop and service workspace security settings. Live check: connection string with ;Roles=<role>.' }
if ($Json) { $text = $result | ConvertTo-Json -Depth 6; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }
$result
