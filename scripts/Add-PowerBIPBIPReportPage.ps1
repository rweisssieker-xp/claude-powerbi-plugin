param(
    [Parameter(Mandatory=$true)][string]$PbipPath,
    [string]$PageName = 'New Page',
    [string[]]$Measures = @(),
    [int]$Width = 1280,
    [int]$Height = 720,
    [switch]$Apply,
    [switch]$Json
)
# Adds a report page with one card visual per measure to the PBIR report of a PBIP project
# (<Name>.Report/definition/pages). Without -Apply: dry run. With -Apply: zip backup, write, manifest entry
# in <project>/.pbip-apply. Undo: Undo-PowerBIPBIPApply.ps1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')
$result = Invoke-PbiApply -PbipPath $PbipPath -Spec @{ command = 'page'; name = $PageName; measure = @($Measures); width = $Width; height = $Height } -Apply:$Apply
if ($Json) { $result | ConvertTo-Json -Depth 8; return }
$result
