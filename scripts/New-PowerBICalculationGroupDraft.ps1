param(
    [string]$GroupName = 'Time Intelligence',
    [string]$ColumnName = 'Time Calculation',
    [string]$DateColumn = "'Date'[Date]",
    [string]$BaseMeasure = 'Selected Measure',
    [int]$Precedence = 10,
    [string]$OutputPath,
    [switch]$Json
)
# Time-intelligence calculation group as valid TMDL (table with calculationGroup, name and Ordinal columns,
# calculationGroup partition). Apply with Apply-PowerBIPBIPCalculationGroup.ps1 (or pbi_apply.py calcgroup),
# which also sets discourageImplicitMeasures on the model.
$ErrorActionPreference = 'Stop'
$py = "CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR($DateColumn))"
$items = @(
    [pscustomobject]@{ name = 'Current'; expression = 'SELECTEDMEASURE()'; formatStringExpression = $null },
    [pscustomobject]@{ name = 'Prior Year'; expression = $py; formatStringExpression = $null },
    [pscustomobject]@{ name = 'YoY'; expression = "SELECTEDMEASURE() - $py"; formatStringExpression = $null },
    [pscustomobject]@{ name = 'YoY %'; expression = "DIVIDE(SELECTEDMEASURE() - $py, $py)"; formatStringExpression = '"0.0%"' },
    [pscustomobject]@{ name = 'YTD'; expression = "CALCULATE(SELECTEDMEASURE(), DATESYTD($DateColumn))"; formatStringExpression = $null }
)

function ConvertTo-TmdlName([string]$Name) {
    if ($Name -match '^[A-Za-z_][A-Za-z0-9_]*$') { return $Name }
    return "'" + $Name.Replace("'", "''") + "'"
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("table $(ConvertTo-TmdlName $GroupName)"); $lines.Add(''); $lines.Add("`tcalculationGroup"); $lines.Add("`t`tprecedence: $Precedence")
$ordinal = 0
foreach ($item in $items) {
    $lines.Add('')
    $lines.Add("`t`tcalculationItem $(ConvertTo-TmdlName $item.name) = $($item.expression)")
    # TMDL: properties (ordinal) before child objects (formatStringDefinition).
    $lines.Add("`t`t`tordinal: $ordinal")
    if ($item.formatStringExpression) { $lines.Add("`t`t`tformatStringDefinition = $($item.formatStringExpression)") }
    $ordinal++
}
foreach ($l in @('', "`tcolumn $(ConvertTo-TmdlName $ColumnName)", "`t`tdataType: string", "`t`tsummarizeBy: none", "`t`tsourceColumn: Name",
        "`t`tsortByColumn: Ordinal", '', "`t`tannotation SummarizationSetBy = Automatic", '', "`tcolumn Ordinal", "`t`tdataType: int64",
        "`t`tformatString: 0", "`t`tisHidden", "`t`tsummarizeBy: sum", "`t`tsourceColumn: Ordinal", '', "`t`tannotation SummarizationSetBy = Automatic",
        '', "`tpartition $(ConvertTo-TmdlName $GroupName) = calculationGroup", "`t`tmode: import")) { $lines.Add($l) }
$tmdl = ($lines -join "`n") + "`n"

$result = [pscustomobject]@{
    schema = 'codex.powerbi.calculationGroupDraft.v1'
    objectType = 'CalculationGroup'
    groupName = $GroupName
    columnName = $ColumnName
    dateColumn = $DateColumn
    baseMeasure = $BaseMeasure
    items = $items
    tmdl = $tmdl
    applyWith = "Apply-PowerBIPBIPCalculationGroup.ps1 -PbipPath <project> -GroupName '$GroupName' -DateColumn `"$DateColumn`" -Apply"
    safety = 'Draft only. The model needs a marked date table for the time-intelligence items; calculation groups set discourageImplicitMeasures.'
}
if ($Json) { $text = $result | ConvertTo-Json -Depth 8; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $tmdl -Encoding UTF8 }
$tmdl
