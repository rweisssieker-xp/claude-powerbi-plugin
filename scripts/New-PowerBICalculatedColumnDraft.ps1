param(
    [Parameter(Mandatory=$true)][string]$TableName,
    [Parameter(Mandatory=$true)][string]$ColumnName,
    [Parameter(Mandatory=$true)][string]$Expression,
    [ValidateSet('string','int64','double','decimal','boolean','dateTime')][string]$DataType = 'string',
    [string]$Description = '',
    [string]$OutputPath,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PowerBIPBIPApply.Shared.ps1')

$tmdl = New-Object System.Collections.Generic.List[string]
$tmdl.Add(('table {0}' -f (ConvertTo-PbiTmdlName $TableName)))
if ($Description) { foreach ($line in ($Description -split "`r?`n")) { $tmdl.Add(("`t/// {0}" -f $line)) } }
$exprLines = @($Expression.Trim() -split "`r?`n")
if ($exprLines.Count -eq 1) {
    $tmdl.Add(("`tcolumn {0} = {1}" -f (ConvertTo-PbiTmdlName $ColumnName), $exprLines[0]))
}
else {
    $tmdl.Add(("`tcolumn {0} =" -f (ConvertTo-PbiTmdlName $ColumnName)))
    foreach ($line in $exprLines) { $tmdl.Add(("`t`t`t{0}" -f $line.TrimEnd())) }
}
$tmdl.Add(("`t`tdataType: {0}" -f $DataType))
$tmdl.Add("`t`tsummarizeBy: none")

$md = New-Object System.Collections.Generic.List[string]
$md.Add('# Power BI Calculated Column Draft')
$md.Add('')
$md.Add(('Target table: `{0}`' -f $TableName))
$md.Add(('Column: `{0}`' -f $ColumnName))
$md.Add('')
$md.Add('Best practice: prefer Power Query or source-system columns when the value is row-level and static. Use calculated columns only when model-time DAX semantics are required.')
$md.Add('')
$md.Add('## TMDL Draft')
$md.Add('')
$md.Add('```tmdl')
$md.AddRange($tmdl)
$md.Add('```')
$md.Add('')
$md.Add('Apply: Apply-PowerBIPBIPCalculatedColumnDraft.ps1 (dry run first, then -Apply). Rollback: Undo-PowerBIPBIPApply.ps1.')

$content = ($md -join [Environment]::NewLine) + [Environment]::NewLine
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8 }

$result = [pscustomobject]@{
    schema = 'codex.powerbi.calculatedColumnDraft.v1'
    objectType = 'CalculatedColumn'
    tableName = $TableName
    columnName = $ColumnName
    expression = $Expression
    dataType = $DataType
    tmdl = ($tmdl -join "`n")
    outputPath = $OutputPath
    safety = 'Draft only. Prefer Power Query/source columns unless a DAX calculated column is explicitly justified.'
}

if ($Json) { $result | ConvertTo-Json -Depth 6; return }
$result
