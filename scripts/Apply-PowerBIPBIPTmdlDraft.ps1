param(
    [Parameter(Mandatory=$true)][string]$PbipPath,
    [string]$ObjectName,
    [Parameter(Mandatory=$true)][string]$Tmdl,
    [string]$TableName,
    [ValidateSet('Measure','CalculatedColumn','CalculatedTable','Relationship','RLSRole','Generic')]
    [string]$ObjectType = 'Generic',
    [switch]$Apply,
    [switch]$Json
)
# Writes a TMDL draft (from New-PowerBI*Draft.ps1) into the real <Name>.SemanticModel/definition of a PBIP project.
# Without -Apply: dry run (shows target file, action and block). With -Apply: backup of the definition folder,
# write, manifest entry in <project>/.pbip-apply. Undo: Undo-PowerBIPBIPApply.ps1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$spec = @{ command = 'tmdl'; tmdl = $Tmdl }
if ($TableName) { $spec.table = $TableName }
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec $spec -Apply:$Apply
$result | Add-Member -NotePropertyName requestedObjectType -NotePropertyValue $ObjectType -Force
if ($ObjectName) { $result | Add-Member -NotePropertyName requestedObjectName -NotePropertyValue $ObjectName -Force }
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
