$pluginRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')
$scriptsPath = Join-Path $pluginRoot 'scripts'
$pbipPath = Join-Path $pluginRoot 'examples/pbip-tmdl-model'

# Regression tests for findings from a run of every script against a real Power BI Desktop PBIP export.
Describe 'Scripts on a real PBIP/TMDL export' {
    It 'reads RLS roles in Desktop TMDL syntax (tablePermission <Table> = <filter>)' {
        $rls = & (Join-Path $scriptsPath 'Test-PowerBIRlsLeakage.ps1') -Path $pbipPath -Json | ConvertFrom-Json
        @($rls.roleTests).Count | Should Be 1
        $rls.roleTests[0].roleName | Should Be 'Region Manager'
        $rls.roleTests[0].tableName | Should Be 'Customer'
        $rls.roleTests[0].filterExpression | Should Be 'Customer[IsActive] = TRUE()'
        $rls.roleTests[0].leakageRisk | Should Be 'Low'
        $trust = & (Join-Path $scriptsPath 'New-PowerBIRlsTrustReview.ps1') -Path $pbipPath -Json | ConvertFrom-Json
        $trust.status | Should Be 'Passed'
    }

    It 'treats a model without roles as not applicable instead of blocking it' {
        $trust = & (Join-Path $scriptsPath 'New-PowerBIRlsTrustReview.ps1') -Path (Join-Path $pluginRoot 'examples/sample-model') -Json | ConvertFrom-Json
        $trust.status | Should Be 'NotApplicable'
        $trust.highRiskCount | Should Be 0
    }

    It 'uses TMDL descriptions as business definitions' {
        $catalog = & (Join-Path $scriptsPath 'New-PowerBIMetricCatalog.ps1') -Path $pbipPath -Json | ConvertFrom-Json
        $total = @($catalog.metrics | Where-Object { $_.name -eq 'Total Sales' })[0]
        $total.businessDefinition | Should Be 'Net invoiced revenue after discounts, in EUR.'
    }

    It 'reports governance gaps once per rule and renders measure names' {
        $markdown = & (Join-Path $scriptsPath 'Test-PowerBIModelBestPractices.ps1') -Path $pbipPath | Out-String
        $markdown | Should Not Match '\$\(@\{'
        $result = & (Join-Path $scriptsPath 'Test-PowerBIModelBestPractices.ps1') -Path $pbipPath -Json | ConvertFrom-Json
        @($result.findings | Where-Object { $_.message -like 'Metric owner is missing*' }).Count | Should BeLessThan 2
        $result.score | Should BeGreaterThan 50
    }

    It 'compares two identical models without failing' {
        $diff = & (Join-Path $scriptsPath 'Compare-PowerBISemanticModel.ps1') -BeforePath $pbipPath -AfterPath $pbipPath -Json | ConvertFrom-Json
        $diff.changeCount | Should Be 0
    }

    It 'does not write measure expectations into the reviewed project' {
        $out = Join-Path $pluginRoot 'tmp/pester-expectations'
        New-Item -ItemType Directory -Force -Path $out | Out-Null
        & (Join-Path $scriptsPath 'Test-PowerBIMeasureExpectations.ps1') -Path $pbipPath -OutputPath (Join-Path $out 'result.md') | Out-Null
        Test-Path -LiteralPath (Join-Path $pbipPath 'measure-expectations.json') | Should Be $false
        Test-Path -LiteralPath (Join-Path $out 'measure-expectations.template.json') | Should Be $true
    }

    It 'returns an empty findings list (not null) for a clean model, so plans get no empty items' {
        $clean = Join-Path $pluginRoot 'tmp/pester-clean-model/Clean.SemanticModel/definition/tables'
        New-Item -ItemType Directory -Force -Path $clean | Out-Null
        Set-Content -LiteralPath (Join-Path $clean 'Sales.tmdl') -Encoding UTF8 -Value "table Sales`n`n`t/// Revenue.`n`tmeasure Revenue = SUM(Sales[Amount])`n`t`tformatString: #,0`n"
        $root = Join-Path $pluginRoot 'tmp/pester-clean-model'
        $scanJson = & (Join-Path $scriptsPath 'Invoke-PowerBIInsightScan.ps1') -Path $root -Json
        $scanJson | Should Not Match '"Findings":\s*null'
        $plan = & (Join-Path $scriptsPath 'New-PowerBIRefactorPlan.ps1') -Path $root -Json | ConvertFrom-Json
        @($plan.items | Where-Object { -not $_.Title }).Count | Should Be 0
    }

    It 'flags only camelCase names as technical in Copilot readiness' {
        $result = & (Join-Path $scriptsPath 'Test-PowerBICopilotReadiness.ps1') -Path $pbipPath -Json | ConvertFrom-Json
        @($result.findings | Where-Object { $_.type -eq 'Technical measure name' -and $_.source -eq 'Total Sales' }).Count | Should Be 0
    }

    It 'renders top risks as text in the executive trust brief' {
        $markdown = & (Join-Path $scriptsPath 'New-PowerBIExecutiveTrustBrief.ps1') -Path $pbipPath | Out-String
        $markdown | Should Not Match 'System\.Object\[\]'
    }

    It 'does not treat a Warn trust gate or Strong PBIP readiness as blocking service findings' {
        $scan = & (Join-Path $scriptsPath 'New-PowerBIServiceScanner.ps1') -Path $pbipPath -Json | ConvertFrom-Json
        @($scan.findings | Where-Object { $_.title -like 'PBIP readiness is Strong*' }).Count | Should Be 0
        @($scan.findings | Where-Object { $_.title -eq 'Trust gate is Warn' -and $_.severity -eq 'High' }).Count | Should Be 0
    }

    It 'writes the time-intelligence calculation group draft through the apply engine' {
        $proj = Join-Path $pluginRoot 'tmp/pester-calcgroup'
        if (Test-Path -LiteralPath $proj) { Remove-Item -Recurse -Force -LiteralPath $proj }
        Copy-Item -Recurse -LiteralPath $pbipPath -Destination $proj
        $draft = & (Join-Path $scriptsPath 'New-PowerBICalculationGroupDraft.ps1') -Json | ConvertFrom-Json
        @($draft.items).Count | Should Be 5
        $draft.tmdl | Should Match "partition 'Time Intelligence' = calculationGroup"
        $result = & (Join-Path $scriptsPath 'Apply-PowerBIPBIPCalculationGroup.ps1') -PbipPath $proj -Apply -Json | ConvertFrom-Json
        $result.applied | Should Be $true
        $written = Get-Content -Raw -LiteralPath $result.targetFullPath
        $written.Replace("`r`n", "`n") | Should Be $draft.tmdl
        (Get-Content -Raw -LiteralPath (Join-Path $proj 'Sales.SemanticModel/definition/model.tmdl')) | Should Match 'discourageImplicitMeasures'
    }
}
