param([string]$PbipPath, [string]$TableName, [string]$MeasureName, [string]$Expression, [string]$FormatString, [string]$Description, [string]$DisplayFolder, [switch]$Apply, [switch]$Json)
# Inserts or replaces a measure in <Table>.tmdl of the PBIP project. Dry run unless -Apply. Undo: Undo-PowerBIPBIPApply.ps1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$spec = @{ command = 'measure'; table = $TableName; name = $MeasureName; expression = $Expression }
if ($FormatString) { $spec.format = $FormatString }
if ($Description) { $spec.description = $Description }
if ($DisplayFolder) { $spec.folder = $DisplayFolder }
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec $spec -Apply:$Apply
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
