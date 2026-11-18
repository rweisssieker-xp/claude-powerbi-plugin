param(
    [string]$Path = ".",
    [string]$RolesPath,
    [string]$Server,
    [string]$OutputPath,
    [switch]$Json,
    [switch]$CheckLive
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $Path).Path
$files = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue)

function Get-RelativePath {
    param([string]$BasePath, [string]$TargetPath)
    try {
        return [System.IO.Path]::GetRelativePath($BasePath, $TargetPath)
    }
    catch {
        return $TargetPath.Substring($BasePath.Length).TrimStart('\', '/')
    }
}

function Escape-DaxString {
    param([string]$Value)
    return ($Value -replace '"', '""')
}

function Escape-DaxIdentifierPart {
    param([string]$Value)
    return ($Value -replace ']', ']]')
}

function New-RoleTest {
    param(
        [string]$RoleName,
        [string]$TableName,
        [string]$FilterExpression,
        [string[]]$AllowedValues,
        [string[]]$DeniedValues,
        [string]$Source,
        [string]$SourcePath
    )

    $safeRole = Escape-DaxString $RoleName
    $safeTable = ($TableName -replace "'", "''")
    $status = if ($CheckLive) { 'NeedsLiveValidation' } else { 'Draft' }
    $risk = if (@($DeniedValues).Count -gt 0) { 'Medium' } elseif ([string]::IsNullOrWhiteSpace($FilterExpression)) { 'High' } else { 'Low' }
    $expectedPolicy = if (@($AllowedValues).Count -gt 0 -or @($DeniedValues).Count -gt 0) {
        [pscustomobject]@{
            allowedValues = @($AllowedValues)
            deniedValues = @($DeniedValues)
            note = 'Validate that live query results only include allowed values for this role.'
        }
    }
    else {
        [pscustomobject]@{
            filterExpression = $FilterExpression
            note = 'Policy inferred from TMDL/model metadata; confirm expected allowed and denied slices before release.'
        }
    }

    [pscustomobject]@{
        roleName = $RoleName
        tableName = $TableName
        source = $Source
        sourcePath = $SourcePath
        filterExpression = $FilterExpression
        daxTestQueryDrafts = @(
            ('EVALUATE ROW("role", "{0}", "visibleRows", CALCULATE(COUNTROWS(''{1}'')))' -f $safeRole, $safeTable),
            ('EVALUATE TOPN(50, SUMMARIZE(''{0}'', ''{0}''[{1}]))' -f $safeTable, (Escape-DaxIdentifierPart 'RLS validation column'))
        )
        expectedPolicy = $expectedPolicy
        leakageRisk = $risk
        status = $status
        releaseGateImpact = if ($risk -eq 'High') { 'Block release until RLS policy is specified and live validation passes.' } elseif ($CheckLive) { 'Require live Desktop/XMLA validation before publish.' } else { 'Draft test plan; no release block without live evidence.' }
    }
}

$roleTests = New-Object System.Collections.Generic.List[object]
$signals = New-Object System.Collections.Generic.List[object]

if (-not $RolesPath) {
    $candidateRolesPath = Join-Path $root 'rls-roles.json'
    if (Test-Path -LiteralPath $candidateRolesPath) { $RolesPath = $candidateRolesPath }
}

if ($RolesPath -and (Test-Path -LiteralPath $RolesPath)) {
    $rolesDoc = Get-Content -Raw -LiteralPath $RolesPath | ConvertFrom-Json
    $roles = if ($rolesDoc.PSObject.Properties.Name -contains 'roles') { @($rolesDoc.roles) } else { @($rolesDoc) }
    foreach ($role in $roles) {
        $roleName = if ($role.name) { [string]$role.name } elseif ($role.roleName) { [string]$role.roleName } else { 'Unnamed role' }
        $tableName = if ($role.table) { [string]$role.table } elseif ($role.tableName) { [string]$role.tableName } else { 'UnknownTable' }
        $filterExpression = if ($role.filterExpression) { [string]$role.filterExpression } elseif ($role.filter) { [string]$role.filter } else { $null }
        $allowed = if ($role.PSObject.Properties.Name -contains 'allowedValues') { @($role.allowedValues) } else { @() }
        $denied = if ($role.PSObject.Properties.Name -contains 'deniedValues') { @($role.deniedValues) } else { @() }
        $roleTests.Add((New-RoleTest -RoleName $roleName -TableName $tableName -FilterExpression $filterExpression -AllowedValues $allowed -DeniedValues $denied -Source 'RolesPath' -SourcePath $RolesPath))
    }
    $signals.Add([pscustomobject]@{ type = 'RolesMatrix'; path = $RolesPath; detail = ('Loaded {0} role matrix entries.' -f @($roles).Count) })
}
else {
    # Real TMDL (Power BI Desktop export):
    #   role 'Name'
    #       modelPermission: read
    #       tablePermission Account = [Account] = "01 Revenue"
    # The filter can also continue on deeper-indented lines or sit in a ``` block.
    $tmdlFiles = @($files | Where-Object { $_.Extension -eq '.tmdl' -and $_.FullName -notmatch '[\\/]\.pbip-apply[\\/]' })
    foreach ($file in $tmdlFiles) {
        $lines = (Get-Content -Raw -LiteralPath $file.FullName) -split "`r?`n"
        $relative = Get-RelativePath -BasePath $root -TargetPath $file.FullName
        $currentRole = $null
        $roleIndent = -1
        $roleHasPermission = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            $expanded = $line -replace "`t", '    '
            $indent = $expanded.Length - $expanded.TrimStart().Length
            if ($line -match "^\s*role\s+(?<role>'(?:[^']|'')+'|[^\s=]+)\s*$") {
                if ($currentRole -and -not $roleHasPermission) {
                    $roleTests.Add((New-RoleTest -RoleName $currentRole -TableName '(no table permission)' -FilterExpression $null -AllowedValues @() -DeniedValues @() -Source 'TMDL' -SourcePath $relative))
                }
                $currentRole = $Matches.role.Trim()
                if ($currentRole.StartsWith("'")) { $currentRole = $currentRole.Substring(1, $currentRole.Length - 2).Replace("''", "'") }
                $roleIndent = $indent
                $roleHasPermission = $false
                $signals.Add([pscustomobject]@{ type = 'TMDLRole'; path = $relative; detail = ('Found role {0}.' -f $currentRole) })
                continue
            }
            if (-not $currentRole) { continue }
            if ($line.Trim() -and $indent -le $roleIndent) { $currentRole = $null; continue }
            if ($line -match "^\s*tablePermission\s+(?<table>'(?:[^']|'')+'|[^\s=]+)\s*=\s*(?<expr>.*)$") {
                $table = $Matches.table.Trim()
                if ($table.StartsWith("'")) { $table = $table.Substring(1, $table.Length - 2).Replace("''", "'") }
                $exprLines = New-Object System.Collections.Generic.List[string]
                if ($Matches.expr.Trim()) { $exprLines.Add($Matches.expr.Trim()) }
                for ($j = $i + 1; $j -lt $lines.Count; $j++) {
                    $next = $lines[$j]
                    if (-not $next.Trim()) { continue }
                    $nextExpanded = $next -replace "`t", '    '
                    if (($nextExpanded.Length - $nextExpanded.TrimStart().Length) -le $indent) { break }
                    if ($next.Trim() -match '^(annotation\s|[A-Za-z][A-Za-z0-9]*:(\s|$))') { break }
                    $exprLines.Add($next.Trim())
                    $i = $j
                }
                $expr = (($exprLines -join ' ').Trim().Trim('`').Trim())
                $roleHasPermission = $true
                $roleTests.Add((New-RoleTest -RoleName $currentRole -TableName $table -FilterExpression $expr -AllowedValues @() -DeniedValues @() -Source 'TMDL' -SourcePath $relative))
            }
        }
        if ($currentRole -and -not $roleHasPermission) {
            $roleTests.Add((New-RoleTest -RoleName $currentRole -TableName '(no table permission)' -FilterExpression $null -AllowedValues @() -DeniedValues @() -Source 'TMDL' -SourcePath $relative))
        }
    }

    $summaryFiles = @($files | Where-Object { $_.Name -match '(model|summary|catalog).*\.(json|md|txt)$' })
    foreach ($file in $summaryFiles) {
        $text = Get-Content -Raw -LiteralPath $file.FullName
        if ($text -match '(?i)\b(RLS|row[- ]level security|role)\b') {
            $relative = Get-RelativePath -BasePath $root -TargetPath $file.FullName
            $signals.Add([pscustomobject]@{ type = 'ModelSummaryRlsSignal'; path = $relative; detail = 'RLS or role text found in model summary-like artifact.' })
        }
    }
}

if ($roleTests.Count -eq 0) {
    # No roles in the model: nothing can leak through RLS. Record it instead of inventing a role.
    $signals.Add([pscustomobject]@{ type = 'NoRoles'; path = $root; detail = 'No RLS roles defined in the model. If data must be restricted per user, define roles first.' })
}

$highRisk = @($roleTests | Where-Object { $_.leakageRisk -eq 'High' }).Count
$needsLive = @($roleTests | Where-Object { $_.status -eq 'NeedsLiveValidation' }).Count
$liveValidationResults = New-Object System.Collections.Generic.List[object]
if ($CheckLive) {
    foreach ($test in @($roleTests)) {
        $query = @($test.daxTestQueryDrafts)[0]
        try {
            $live = & (Join-Path $PSScriptRoot 'Invoke-PowerBILiveDaxQuery.ps1') -Server $Server -Query $query -Json | ConvertFrom-Json
            $liveValidationResults.Add([pscustomobject]@{
                roleName = $test.roleName
                tableName = $test.tableName
                status = 'LiveQuerySucceeded'
                rowCount = $live.rowCount
                query = $query
            }) | Out-Null
            $test.status = 'LiveValidated'
        }
        catch {
            $liveValidationResults.Add([pscustomobject]@{
                roleName = $test.roleName
                tableName = $test.tableName
                status = 'LiveQueryUnavailable'
                error = $_.Exception.Message
                query = $query
            }) | Out-Null
        }
    }
}
$result = [pscustomobject]@{
    schema = 'codex.powerbi.rlsLeakage.v1'
    root = $root
    generated = (Get-Date).ToString('s')
    mode = if ($CheckLive) { 'LiveValidationRequested' } else { 'DraftOnly' }
    rolesPath = $RolesPath
    roleTestCount = $roleTests.Count
    highRiskCount = $highRisk
    signals = @($signals.ToArray())
    roleTests = @($roleTests.ToArray())
    liveValidationResults = @($liveValidationResults.ToArray())
    releaseGateImpact = if ($highRisk -gt 0) { 'Blocked until RLS expectations are specified and validated.' } elseif ($needsLive -gt 0) { 'Warn until live RLS validation evidence is attached.' } else { 'Draft RLS leakage checks generated; validate live before publish.' }
}

if ($Json) {
    $text = $result | ConvertTo-Json -Depth 10
    if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8 }
    $text
    return
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('# Power BI RLS Leakage Draft')
$lines.Add('')
$lines.Add(('Mode: **{0}**' -f $result.mode))
$lines.Add(('Role tests: {0}' -f $result.roleTestCount))
$lines.Add(('Release gate impact: {0}' -f $result.releaseGateImpact))
$lines.Add('')
$lines.Add('## Role Tests')
$lines.Add('')
foreach ($test in $result.roleTests) {
    $lines.Add(('### [{0}] {1}' -f $test.status, $test.roleName))
    $lines.Add(('- Source: {0}' -f $test.source))
    $lines.Add(('- Table: {0}' -f $test.tableName))
    $lines.Add(('- Leakage risk: {0}' -f $test.leakageRisk))
    $lines.Add(('- Release gate: {0}' -f $test.releaseGateImpact))
    $lines.Add('')
    foreach ($query in @($test.daxTestQueryDrafts)) {
        $lines.Add('```DAX')
        $lines.Add($query)
        $lines.Add('```')
    }
    $lines.Add('')
}
$content = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
if ($OutputPath) { Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8 }
$content
