param(
    [Parameter(Mandatory=$true)][string]$TableName,
    [Parameter(Mandatory=$true)][string]$MeasureName,
    [Parameter(Mandatory=$true)][string]$Expression,
    [string]$Description = '',
    [string]$FormatString = '',
    [string]$DisplayFolder = '',
    [string]$OutputPath,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')

# TMDL as Power BI Desktop writes it: tabs, quoted names, /// descriptions, expression on the header line or indented below.
$tmdl = New-Object System.Collections.Generic.List[string]
$tmdl.Add(('table {0}' -f (ConvertTo-PbiTmdlName $TableName)))
if ($Description) { foreach ($line in ($Description -split "`r?`n")) { $tmdl.Add(("`t/// {0}" -f $line)) } }
$exprLines = @($Expression.Trim() -split "`r?`n")
if ($exprLines.Count -eq 1) {
    $tmdl.Add(("`tmeasure {0} = {1}" -f (ConvertTo-PbiTmdlName $MeasureName), $exprLines[0]))
}
else {
    $tmdl.Add(("`tmeasure {0} =" -f (ConvertTo-PbiTmdlName $MeasureName)))
    foreach ($line in $exprLines) { $tmdl.Add(("`t`t`t{0}" -f $line.TrimEnd())) }
}
if ($FormatString) { $tmdl.Add(("`t`tformatString: {0}" -f $FormatString)) }
if ($DisplayFolder) { $tmdl.Add(("`t`tdisplayFolder: {0}" -f $DisplayFolder)) }

$validationQueries = @(
    ('EVALUATE ROW("{0}", [{1}])' -f $MeasureName.Replace('"', '""'), $MeasureName.Replace(']', ']]')),
    ('EVALUATE ROW("IsBlank", ISBLANK([{0}]), "Value", [{0}])' -f $MeasureName.Replace(']', ']]'))
)

$md = New-Object System.Collections.Generic.List[string]
$md.Add('# Power BI Measure Draft')
$md.Add('')
$md.Add(('Target table: `{0}`' -f $TableName))
$md.Add(('Measure: `{0}`' -f $MeasureName))
$md.Add('')
$md.Add('## TMDL Draft')
$md.Add('')
$md.Add('```tmdl')
$md.AddRange($tmdl)
$md.Add('```')
$md.Add('')
$md.Add('## Validation Queries')
foreach ($query in $validationQueries) {
    $md.Add('')
    $md.Add('```DAX')
    $md.Add($query)
    $md.Add('```')
}
$md.Add('')
$md.Add('Apply: Apply-PowerBIPBIPMeasureDraft.ps1 -PbipPath <project> ... (dry run first, then -Apply). Rollback: Undo-PowerBIPBIPApply.ps1.')

$content = ($md -join [Environment]::NewLine) + [Environment]::NewLine
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8 }

$result = [pscustomobject]@{
    schema = 'codex.powerbi.measureDraft.v1'
    objectType = 'Measure'
    tableName = $TableName
    measureName = $MeasureName
    expression = $Expression
    tmdl = ($tmdl -join "`n")
    validationQueries = $validationQueries
    outputPath = $OutputPath
    safety = 'Draft only. Apply through PBIP/TMDL (Apply-PowerBIPBIPMeasureDraft.ps1, dry run first) after backup and validation.'
}

if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
