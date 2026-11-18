param(
    [Parameter(Mandatory=$true)][string]$PbipPath,
    [string]$GroupName = 'Time Intelligence',
    [string]$ColumnName,
    [string]$DateColumn = "'Date'[Date]",
    [string[]]$Items,
    [string[]]$ItemFormats,
    [int]$Precedence = 10,
    [switch]$Apply,
    [switch]$Json
)
# Writes a calculation group table into the PBIP semantic model and sets discourageImplicitMeasures.
# -Items 'Name=DAX' (SELECTEDMEASURE()) in display order; without -Items the time-intelligence set from
# New-PowerBICalculationGroupDraft.ps1 is used (Current, Prior Year, YoY, YoY %, YTD on -DateColumn).
# -ItemFormats 'Name="0.0%"' sets a format string expression. Without -Apply: dry run. Undo: Undo-PowerBIPBIPApply.ps1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
if (-not $Items) {
    $draft = & (Join-Path $PSScriptRoot 'New-PowerBICalculationGroupDraft.ps1') -GroupName $GroupName -DateColumn $DateColumn -Json | ConvertFrom-Json
    $Items = @($draft.items | ForEach-Object { '{0}={1}' -f $_.name, $_.expression })
    $ItemFormats = @($draft.items | Where-Object { $_.formatStringExpression } | ForEach-Object { '{0}={1}' -f $_.name, $_.formatStringExpression })
    if (-not $ColumnName) { $ColumnName = $draft.columnName }
}
$spec = @{ command = 'calcgroup'; name = $GroupName; item = @($Items); item_format = @($ItemFormats); precedence = $Precedence }
if ($ColumnName) { $spec.column_name = $ColumnName }
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec $spec -Apply:$Apply
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
