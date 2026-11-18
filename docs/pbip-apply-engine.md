# PBIP Apply Engine

The apply engine writes reviewed changes into a real Power BI project (PBIP with TMDL). It never edits `.pbix` or `.pbit` files.

The engine is `scripts/python/pbi_apply.py` (Python 3, stdlib only). The PowerShell `Apply-*` scripts are thin wrappers around it (`PowerBIPBIPApply.Shared.ps1`), so both routes write byte-identical TMDL.

## Safety model

- **Dry run by default.** Without `--apply` (Python) or `-Apply` (PowerShell) the engine prints the target file, the action (`insert`, `replace` or `skip`) and the exact TMDL block, and writes nothing.
- **Backup before every write.** The whole `<Name>.SemanticModel/definition` folder is zipped to `<project>/.pbip-apply/backups/<id>.zip`. Backups are zip files, so reviews never read them as model files.
- **Manifest.** Each change is recorded in `<project>/.pbip-apply/manifest.json` (`changes` list: id, time, object, file, action).
- **Undo without deleting.** `undo` restores a backup. Files created by later changes are moved to `<project>/.pbip-apply/undone/<time>/`, never deleted.
- **Idempotent.** An existing measure, column or table of the same name is replaced in place. An identical relationship is skipped.
- Close the project in Power BI Desktop before applying, then reopen it: Desktop validates the TMDL on open.

## Commands

```bash
python3 -I scripts/python/pbi_apply.py measure      <PBIP> --table Sales --name "Average Sales" --expression "DIVIDE([Total Sales], COUNTROWS(Sales))" --format "#,0.00" --description "…" --folder Revenue [--apply]
python3 -I scripts/python/pbi_apply.py column       <PBIP> --table Sales --name "Is Big" --expression "Sales[Amount] > 1000" --data-type boolean [--apply]
python3 -I scripts/python/pbi_apply.py table        <PBIP> --name Regions --expression "DISTINCT(Customer[Region])" --column Region:string [--apply]
python3 -I scripts/python/pbi_apply.py relationship <PBIP> --from Sales.CustomerKey --to Customer.CustomerKey [--both-directions] [--inactive] [--one-to-one] [--apply]
python3 -I scripts/python/pbi_apply.py role         <PBIP> --name "EU only" --table Customer --filter 'Customer[Region] = "EU"' [--apply]
python3 -I scripts/python/pbi_apply.py query        <PBIP> --name DimDate --m-file DimDate.pq [--apply]
python3 -I scripts/python/pbi_apply.py tmdl         <PBIP> --tmdl-file draft.tmdl [--table Sales] [--apply]
python3 -I scripts/python/pbi_apply.py calcgroup    <PBIP> --name "Time Intelligence" --item "Current=SELECTEDMEASURE()" --item "Prior Year=CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('Date'[Date]))" [--item-format 'YoY %="0.0%"'] [--precedence 10] [--apply]
python3 -I scripts/python/pbi_apply.py page         <PBIP> --name "KPI Overview" --measure "Total Sales" --measure "Sales YoY %" [--apply]
python3 -I scripts/python/pbi_apply.py undo         <PBIP> [--backup <id>] [--apply]
python3 -I scripts/python/pbi_apply.py history      <PBIP>
```

`calcgroup` writes a calculation group table (items in display order, a name column sorted by a hidden Ordinal column, a `calculationGroup` partition) and sets `discourageImplicitMeasures` on the model, which Power BI requires for calculation groups. A TMDL draft that holds a calculation group (`tmdl`) gets the same model setting.

`page` adds a report page in PBIR format (`<Name>.Report/definition/pages`) with one card visual per measure and appends it to `pageOrder`. The backup then also holds the report definition, and `undo` restores both. A draft with only a measure or column needs `--table`.

`<PBIP>` is the project folder or the `.pbip` file. Column references accept `Table.Column`, `Table[Column]` and quoted names.

## PowerShell wrappers

```powershell
.\scripts\Apply-PowerBIPBIPMeasureDraft.ps1 -PbipPath .\MyReport -TableName Sales -MeasureName "Average Sales" `
  -Expression "DIVIDE([Total Sales], COUNTROWS('Sales'))" -FormatString "#,0.00" -Apply
.\scripts\Apply-PowerBIPBIPCalculatedColumnDraft.ps1 -PbipPath .\MyReport -TableName Sales -ColumnName "Sales Band" -Expression "…" -Apply
.\scripts\Apply-PowerBIPBIPPowerQueryDraft.ps1      -PbipPath .\MyReport -QueryName DimDate -SourceKind DateTable -Apply
.\scripts\Apply-PowerBIPBIPTmdlDraft.ps1            -PbipPath .\MyReport -Tmdl (Get-Content .\draft.tmdl -Raw) [-TableName Sales] -Apply
.\scripts\Apply-PowerBIPBIPCalculationGroup.ps1      -PbipPath .\MyReport -DateColumn "'Date'[Date]" -Apply   # time-intelligence set; or -Items 'Name=DAX',...
.\scripts\Add-PowerBIPBIPReportPage.ps1             -PbipPath .\MyReport -PageName 'KPI Overview' -Measures 'Total Sales','Sales YoY %' -Apply
.\scripts\Undo-PowerBIPBIPApply.ps1                 -PbipPath .\MyReport [-BackupId <id>] -Apply
.\scripts\Invoke-PowerBIPBIPApplyPlan.ps1           -PbipPath .\MyReport -OutputPath .\apply-plan.json
.\scripts\Test-PowerBIPBIPRollbackReadiness.ps1     -PbipPath .\MyReport
```

`New-PowerBIMeasureDraft.ps1`, `New-PowerBICalculatedColumnDraft.ps1`, `New-PowerBIRelationshipDraft.ps1` and `New-PowerBIRlsRoleDraft.ps1` produce valid TMDL drafts that `Apply-PowerBIPBIPTmdlDraft.ps1` (or `pbi_apply.py tmdl`) can apply. `PowerBIPBIPApply.Shared.ps1` finds Python (skipping the Windows Store alias) and passes each change as a JSON spec file, so quoting in DAX survives Windows PowerShell 5.1.

## Workflow

1. Review the model (`pbi_toolkit.py review`) and agree on the change.
2. Dry run and show the TMDL block.
3. Get approval, preferably on a copy of the project.
4. Apply.
5. Close and reopen the `.pbip` in Power BI Desktop; refresh calculated tables or columns if Desktop asks.
6. Verify live (`/powerbi-live-desktop`, `Invoke-PowerBILiveDaxQuery.ps1`) and re-run the review.
7. If anything is wrong: `undo`, then reopen.

## Verified

The engine was tested on a PBIP exported from Power BI Desktop 2.159 (Store edition):

- a measure with description and format, plus a multi-line measure;
- a calculated column, a calculated table, a relationship and an RLS role;
- every object loaded in Desktop and returned the expected values live;
- an undo restored the original files byte for byte;
- a report page added with `page` opened in Desktop with its card visuals showing the expected values.
