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
}
