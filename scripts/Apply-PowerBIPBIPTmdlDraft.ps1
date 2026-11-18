param(
    [Parameter(Mandatory=$true)][string]$PbipPath,
    [string]$ObjectName,
    [Parameter(Mandatory=$true)][string]$Tmdl,
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
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec @{ command = 'tmdl'; tmdl = $Tmdl } -Apply:$Apply
$result | Add-Member -NotePropertyName requestedObjectType -NotePropertyValue $ObjectType -Force
if ($ObjectName) { $result | Add-Member -NotePropertyName requestedObjectName -NotePropertyValue $ObjectName -Force }
if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
