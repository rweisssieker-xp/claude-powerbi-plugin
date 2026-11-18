# Changelog

## 3.4.0 - 2026-11-18

Every script was run against a real Power BI Desktop PBIP export (two tables, relationship, RLS role, calculated column and table, PBIR report with a custom visual). Fixes from that run:

- **RLS:** roles in Desktop TMDL syntax (`tablePermission <Table> = <filter>`) were not read, so every role was reported as "no policy evidence" and the release was blocked. A model without roles is now `NotApplicable` instead of `Blocked` with an invented role.
- **KPI catalog and best practices:** TMDL descriptions (`///`) are used as business definitions; owners can be set with `annotation Owner = <name>`. Governance gaps are reported once per rule with the affected measures, so the score no longer drops to 0 for documentation gaps alone. Measure names in eight reports were printed as raw PowerShell objects.
- **Report pages:** `Add-PowerBIPBIPReportPage.ps1` wrote a non-PBIR folder layout. It now uses the apply engine (`pbi_apply.py page`): a PBIR page with one card visual per measure, `pageOrder` updated, zip backup and undo (backups now include the report definition).
- **Apply engine:** `tmdl --table` (`Apply-PowerBIPBIPTmdlDraft.ps1 -TableName`) for drafts that hold only a measure or column; clear errors for missing parameters in the measure and column wrappers.
- **No writes outside the output:** the measure expectations template is no longer written into the reviewed project; review memory and the External Tools registration go to the user data folder (`%LOCALAPPDATA%\pbi-workbench`), not into the read-only plugin folder.
- **Fixed crashes:** `Compare-PowerBISemanticModel.ps1` and `Compare-PowerBINativeModel.ps1` failed when nothing changed.
- **Portability:** the AI forecast finds `python3`; live scripts and External Tools installers explain that they need Windows instead of failing on `powershell.exe`.
- **Custom visuals** in PBIP projects (`<Name>.Report/CustomVisuals`) are detected by the Python review.
- **CI:** GitHub Actions runs the Python tests, the PowerShell self-test, golden baselines and Pester on Linux (PowerShell 7) and Windows (Windows PowerShell 5.1). Pester failures now fail the test run. New Pester tests for the fixes; 31 Python tests, 64 Pester tests.

## 3.3.0 - 2026-11-18

- Real PBIP apply engine (`scripts/python/pbi_apply.py`): measures, calculated columns, calculated tables, relationships, RLS roles, shared Power Query expressions and TMDL drafts are written into the actual TMDL files. Dry run by default, zip backup and manifest per change, `undo` without deleting. Before, the `Apply-*` scripts only wrote draft files next to the model.
- The `Apply-PowerBIPBIP*.ps1` scripts now call the engine; the `New-PowerBI*Draft.ps1` scripts produce valid TMDL. New `Undo-PowerBIPBIPApply.ps1`.
- Verified on a PBIP exported from Power BI Desktop 2.159: six changes loaded in Desktop with the expected live values (measure, multi-line measure, column, calculated table, relationship, RLS role); undo restored the original byte for byte.
- Live review with several open Desktop files: `Invoke-PowerBILiveReviewAll.ps1` reviews every open model into its own folder (named after the window title); `-Title` picks one model. `Run-PowerBILiveReview.cmd [outdir] [title]` uses it. Verified with three open models.
- New slash command `/powerbi-change`.
- Rollback readiness reads the apply manifest; reviews skip `.pbip-apply`.
- 9 new Python tests for the apply engine (29 in total).
- Plugin renamed to `pbi-workbench` for the Claude directory (skill names unchanged). README lists everything the plugin runs, sends and fetches; `LICENSE` file added.

## 3.2.1 - 2026-11-17

- Skills work after installation: bundled files are addressed through `$PLUGIN_ROOT` (two levels above the skill folder). `${CLAUDE_PLUGIN_ROOT}` is only substituted in hooks and MCP configs, so the 3.1/3.2 commands pointed to an empty path once installed.
- Verified from a read-only install location: portfolio review, single PBIX with and without pbixray, model wizard, forecast engine, PowerShell scripts.
- A PBIX whose semantic model cannot be read now gets "Semantic model not inspected" (Medium, gate Warn) instead of a High finding and No-Go.

## 3.2.0 - 2026-11-17

- PBIX/PBIT review: report layer (PBIR and legacy layout) with the standard library, semantic model via optional `pbixray`.
- Portfolio review for folders of PBIX files.
- Report checks: broken visual field references, unused measures, embedded custom visuals, empty/dense pages; model checks: tables without relationships, column memory hotspots.
- Live fixes verified on Windows 11 with Power BI Desktop 2.159 (Store): TCP probe for endpoint detection, Desktop ADOMD client preferred, live measure values, real VertiPaq sizes, Store edition detection.
- False-positive fixes: filter aliases, date-table rule, KPI trust without measures.
- New `scripts/Run-PowerBILiveReview.cmd`.

## 3.1.0 (Claude port) - 2026-11-17

- Ported to Claude: `.claude-plugin/plugin.json`, `disable-model-invocation` instead of `agents/openai.yaml`, `${CLAUDE_PLUGIN_ROOT}` paths.
- New Python toolkit (`scripts/python/pbi_toolkit.py`) and Python model wizard (`scripts/python/pbi_model_wizard.py`); parity with PowerShell on the fixtures.
- New slash-command skills: powerbi-review, powerbi-kpi-trust, powerbi-release-gate, powerbi-forecast, powerbi-live-desktop.
- Fix: real TMDL measures (`measure 'Name' = ...`) are now detected by insight scan, metric catalog, and model summary.
- Fix: live target resolution no longer fails on non-Windows hosts.
- New fixtures: `examples/pbip-tmdl-model`, `examples/model-wizard-sources`; data source template added to `templates/`.
- External Tool renamed to "Claude Power BI Workbench".

## v3.0.0 - 2026-06-04

### Added

- Added advanced release USP workflows: evidence graph, DAX change risk classifier, semantic contract test, freshness/lineage gate, executive trust brief, KPI drift watchlist, RLS trust review, UX regression scanner, and migration readiness.
- Added `-IncludeAdvancedUspQa` to release candidate packs so advanced release USP evidence can be generated as part of the local release package.
- Added separated portfolio governance, compliance QA, and operations QA workflows with `-IncludePortfolioGovernanceQa`, `-IncludeComplianceQa`, and `-IncludeOperationsQa`.
- Added Fabric Live Read-Only + Snapshot Intelligence workflows with access plans, GET-only REST guardrails, workspace/tenant snapshots, 25 Fabric USP scripts, and release candidate pack switches for Fabric portfolio, deployment, operations, governance, and executive QA.
- Added analytical release QA workflows: `Test-PowerBIAnalysisMethodology.ps1`, `New-PowerBIMetricChangeDiagnosis.ps1`, and `New-PowerBIAnalyticalReleaseReport.ps1`.
- Added `-IncludeAnalyticalQa` to release candidate packs so methodology validation, metric diagnosis, and stakeholder-ready analytical reports can be included in release evidence.

### Verification

- `Invoke-Pester .\tests\pester\PowerBIPlugin.Tests.ps1` passed.
- `Test-PowerBIDocumentationCoverage.ps1` passed.
- `Test-PowerBIPlugin.ps1` passed.
- `plugin.json` parse check passed.

## v2.1.0 - 2026-05-20

### Added

- Added local Business Process Data Quality packs for Order-to-Cash, Procure-to-Pay, Record-to-Report, Hire-to-Retire, Plan-to-Produce, Forecast-to-Deliver, Service-to-Cash, Issue-to-Resolution, Lead-to-Opportunity, and Quote-to-Order.
- Added `Invoke-PowerBIBusinessProcessDataQuality.ps1`, `New-PowerBIProcessDataMapping.ps1`, and `New-PowerBIBusinessProcessDQPack.ps1` for local Power BI metadata plus CSV/JSON export validation.
- Added process rule packs, sample ERP-style CSV fixtures, process DQ smoke tests, focused Pester coverage, and dedicated documentation.

### Changed

- Kept Business Process Data Quality separate from the 39-artifact Max AI Review while allowing release candidate packs to include process DQ summary evidence with `-IncludeBusinessProcessDQ`.
- Updated plugin metadata, README positioning, script catalog, value proposition, workflow docs, testing docs, and skill guidance for the new process DQ layer.

### Verification

- `Test-PowerBIDocumentationCoverage.ps1` passed.
- `Test-PowerBIPlugin.ps1` passed.
- `Run-PowerBITests.ps1` passed.
- `BusinessProcessDQ.Tests.ps1` passed.
- PSScriptAnalyzer passed with no script errors.
- Generated/local output patterns are ignored and not staged.

## v2.0.0 - 2026-05-20

### Added

- Expanded the Power BI Desktop plugin into a 38-USP AI Power BI Workbench.
- Added eighteen AI workflows:
  - Agentic Remediation Prioritization
  - Business Outcome Simulation
  - Semantic Layer Autopilot
  - AI Governance Evidence Pack
  - Human Override Learning
  - Cross-Report KPI Conflict Detection
  - Executive Narrative Quality Agent
  - Autonomous Power BI QA Lab
  - PBIP Change Impact Gate
  - Semantic Test Fixture Generator
  - KPI Owner Sign-off Workflow
  - Refresh Blast-Radius Analyzer
  - Sensitive Data Exposure Map
  - Capacity Mitigation Planner
  - Report Retirement Advisor
  - Live Validation Evidence Recorder
  - Semantic Contract Drift Monitor
  - RLS Persona Coverage Matrix
- Extended Max AI Review to produce 39 local artifacts across the 38-USP workflow set.
- Added deterministic local PowerShell scripts for the new AI workflows with JSON and Markdown/default output behavior.
- Added documentation for the expanded USP map, workflows, script catalog entries, Max AI artifacts, and value proposition.
- Added test coverage for new script presence, JSON schemas, sample-model execution, Max AI artifact generation, and documentation coverage.

### Changed

- Updated plugin positioning to a 38-USP AI Power BI Workbench.
- Updated plugin metadata, default prompts, README positioning, and capability descriptions.
- Kept the execution model local-first: no hidden service calls, no PBIX mutation, no implicit publish, and no hidden writes.
- Tightened `.gitignore` so generated local review, live, forecast, incident, QA, and release outputs stay out of Git.

### Removed

- Removed generated local Power BI artifacts, live-model outputs, forecast extracts, incident reports, backup dumps, and local helper scripts from Git tracking.
- Removed Python cache artifacts from Git tracking.

### Verification

- `Test-PowerBIDocumentationCoverage.ps1` passed.
- `Test-PowerBIPlugin.ps1` passed.
- `Run-PowerBITests.ps1` passed.
- PSScriptAnalyzer passed with no script errors.
- Generated/local output patterns are ignored and not staged.

## v1.0.0

- Initial public plugin release baseline.
