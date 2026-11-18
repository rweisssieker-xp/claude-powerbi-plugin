param([string]$PbipPath, [string]$QueryName = 'NewQuery', [ValidateSet('DateTable','SqlTable','SharePointFile','Blank')] [string]$SourceKind = 'Blank', [switch]$Apply, [switch]$Json)
# Adds the query as a shared Power Query expression (definition/expressions.tmdl). It appears in Power Query as a
# connection-only query; load it as a table in Power BI Desktop when reviewed. Dry run unless -Apply.
$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptRoot 'PowerBIPBIPApply.Shared.ps1')
$draft = & (Join-Path $scriptRoot 'New-PowerBIPowerQueryDraft.ps1') -QueryName $QueryName -SourceKind $SourceKind -Json | ConvertFrom-Json
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec @{ command = 'query'; name = $QueryName; m = $draft.mCode } -Apply:$Apply
$result | Add-Member -NotePropertyName queryName -NotePropertyValue $QueryName -Force
$result | Add-Member -NotePropertyName sourceKind -NotePropertyValue $SourceKind -Force
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
