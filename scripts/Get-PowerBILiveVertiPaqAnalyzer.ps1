param([string]$Server, [string]$OutputPath, [int]$Top = 15, [switch]$Json)
$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dmv = Join-Path $scriptRoot 'Invoke-PowerBILiveDmv.ps1'

function Invoke-Dmv {
    param([string]$Query)
    $dmvArgs = @{ Query = $Query; Json = $true }
    if ($Server) { $dmvArgs.Server = $Server }
    (& $dmv @dmvArgs | ConvertFrom-Json).rows
}

# Metadata sections (unchanged contract)
$queries = [ordered]@{
    Tables = 'SELECT * FROM $SYSTEM.TMSCHEMA_TABLES'
    Columns = 'SELECT * FROM $SYSTEM.TMSCHEMA_COLUMNS'
    Relationships = 'SELECT * FROM $SYSTEM.TMSCHEMA_RELATIONSHIPS'
}
$sections = New-Object System.Collections.Generic.List[object]
foreach ($entry in $queries.GetEnumerator()) {
    try {
        $rows = @(Invoke-Dmv -Query $entry.Value)
        $sections.Add([pscustomobject]@{ name = $entry.Key; status = 'Read'; rowCount = $rows.Count; error = $null })
    } catch {
        $sections.Add([pscustomobject]@{ name = $entry.Key; status = 'Unavailable'; rowCount = 0; error = $_.Exception.Message })
    }
}

# Storage sizes: dictionary per column + data segments per column (VertiPaq Analyzer style)
$columns = @{}
$storageStatus = 'Read'
$storageError = $null
try {
    foreach ($row in @(Invoke-Dmv -Query 'SELECT DIMENSION_NAME, ATTRIBUTE_NAME, COLUMN_TYPE, DICTIONARY_SIZE FROM $SYSTEM.DISCOVER_STORAGE_TABLE_COLUMNS')) {
        if ($row.COLUMN_TYPE -ne 'BASIC_DATA') { continue }
        $key = "$($row.DIMENSION_NAME)|$($row.ATTRIBUTE_NAME)"
        if (-not $columns.ContainsKey($key)) { $columns[$key] = [pscustomobject]@{ table = $row.DIMENSION_NAME; column = $row.ATTRIBUTE_NAME; dictionaryBytes = [int64]0; dataBytes = [int64]0; rows = [int64]0 } }
        $columns[$key].dictionaryBytes += [int64]$row.DICTIONARY_SIZE
    }
    foreach ($row in @(Invoke-Dmv -Query 'SELECT DIMENSION_NAME, COLUMN_ID, USED_SIZE, RECORDS_COUNT FROM $SYSTEM.DISCOVER_STORAGE_TABLE_COLUMN_SEGMENTS')) {
        $columnId = [string]$row.COLUMN_ID
        if ($columnId -match '^(H\$|R\$|U\$)|^(POS_TO_ID|ID_TO_POS)\b|^RowNumber') { continue }  # hierarchies, relationships, internal row structures
        $name = $columnId -replace '\s*\(\d+\)\s*$', ''
        $key = "$($row.DIMENSION_NAME)|$name"
        if (-not $columns.ContainsKey($key)) { $columns[$key] = [pscustomobject]@{ table = $row.DIMENSION_NAME; column = $name; dictionaryBytes = [int64]0; dataBytes = [int64]0; rows = [int64]0 } }
        $columns[$key].dataBytes += [int64]$row.USED_SIZE
        $columns[$key].rows += [int64]$row.RECORDS_COUNT
    }
} catch {
    $storageStatus = 'Unavailable'
    $storageError = $_.Exception.Message
}
$sections.Add([pscustomobject]@{ name = 'Storage'; status = $storageStatus; rowCount = $columns.Count; error = $storageError })

$columnList = @($columns.Values | Where-Object { $_.column -notmatch '^RowNumber' } | ForEach-Object {
    $_ | Add-Member -NotePropertyName totalBytes -NotePropertyValue ($_.dictionaryBytes + $_.dataBytes) -PassThru
} | Sort-Object totalBytes -Descending)
$totalBytes = [int64](($columnList | Measure-Object -Property totalBytes -Sum).Sum)
$tables = @($columnList | Group-Object table | ForEach-Object {
    [pscustomobject]@{ table = $_.Name; columns = $_.Count; totalBytes = [int64](($_.Group | Measure-Object totalBytes -Sum).Sum) }
} | Sort-Object totalBytes -Descending)
foreach ($c in $columnList) { $c | Add-Member -NotePropertyName sharePct -NotePropertyValue $(if ($totalBytes) { [math]::Round(100.0 * $c.totalBytes / $totalBytes, 1) } else { 0 }) }

$result = [pscustomobject]@{
    schema = 'codex.powerbi.liveVertiPaqAnalyzer.v1'
    generated = (Get-Date).ToString('s')
    sectionCount = $sections.Count
    sections = @($sections.ToArray())
    totalBytes = $totalBytes
    tables = $tables
    topColumns = @($columnList | Select-Object -First $Top)
    note = 'Live DMVs through the Desktop XMLA endpoint (read-only). Sizes = dictionary + data segments per column; hierarchy and relationship structures excluded.'
}
if ($Json) { $text = $result | ConvertTo-Json -Depth 8; if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }; $text; return }

$md = New-Object System.Collections.Generic.List[string]
$md.Add('# Power BI Live VertiPaq Analysis')
$md.Add('')
$md.Add(('Total column storage: **{0:N0} bytes** ({1:N1} MB)' -f $totalBytes, ($totalBytes / 1MB)))
$md.Add('')
$md.Add('| Table | Columns | Bytes |')
$md.Add('| --- | --- | --- |')
foreach ($t in $tables) { $md.Add(('| {0} | {1} | {2:N0} |' -f $t.table, $t.columns, $t.totalBytes)) }
$md.Add('')
$md.Add('## Largest columns')
$md.Add('')
$md.Add('| Column | Dictionary | Data | Total | Share |')
$md.Add('| --- | --- | --- | --- | --- |')
foreach ($c in @($columnList | Select-Object -First $Top)) { $md.Add(('| {0}[{1}] | {2:N0} | {3:N0} | {4:N0} | {5} % |' -f $c.table, $c.column, $c.dictionaryBytes, $c.dataBytes, $c.totalBytes, $c.sharePct)) }
foreach ($s in $sections | Where-Object status -ne 'Read') { $md.Add(''); $md.Add(('> {0}: unavailable ({1})' -f $s.name, $s.error)) }
$content = ($md -join [Environment]::NewLine) + [Environment]::NewLine
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8 }
$content
