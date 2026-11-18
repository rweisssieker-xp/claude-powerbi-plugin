param([string]$PbipPath, [string]$TableName, [string]$ColumnName, [string]$Expression, [ValidateSet('string','int64','double','decimal','boolean','dateTime')][string]$DataType = 'string', [string]$Description, [switch]$Apply, [switch]$Json)
# Inserts or replaces a calculated column in <Table>.tmdl of the PBIP project. Dry run unless -Apply.
$ErrorActionPreference = 'Stop'
$missing = @($(if (-not $PbipPath) { '-PbipPath' }), $(if (-not $TableName) { '-TableName' }), $(if (-not $ColumnName) { '-ColumnName' }), $(if (-not $Expression) { '-Expression' })) | Where-Object { $_ }
if ($missing) { throw ('Missing required parameter(s): ' + ($missing -join ', ') + '.') }
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$spec = @{ command = 'column'; table = $TableName; name = $ColumnName; expression = $Expression; data_type = $DataType }
if ($Description) { $spec.description = $Description }
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec $spec -Apply:$Apply
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
