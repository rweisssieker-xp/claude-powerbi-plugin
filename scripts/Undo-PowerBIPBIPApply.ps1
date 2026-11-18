param([Parameter(Mandatory=$true)][string]$PbipPath, [string]$BackupId, [switch]$Apply, [switch]$Json)
# Restores the semantic model definition from a backup taken by the apply scripts (latest by default).
# Nothing is deleted: files added after the backup are moved to <project>/.pbip-apply/undone/. Dry run unless -Apply.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$spec = @{ command = 'undo' }
if ($BackupId) { $spec.backup = $BackupId }
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec $spec -Apply:$Apply
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
