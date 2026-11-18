# Authoring And Validation

> **Plugin folder:** `$PLUGIN_ROOT` below is the plugin folder, three levels above this file (`<plugin>/skills/powerbi-desktop/references/`). Set it at the start of every shell command: `PLUGIN_ROOT="$(cd "<folder of this file>/../../.." && pwd)"`.

Use PBIP/TMDL only. Do not write binary PBIX/PBIT files.

- `New-PowerBIMeasureDraft.ps1` and `New-PowerBICalculatedColumnDraft.ps1` create safe semantic-model drafts.
- `New-PowerBIPowerQueryDraft.ps1`, `New-PowerBIReportPageDraft.ps1`, and `New-PowerBIVisualDraft.ps1` create query or report drafts.
- The apply engine `scripts/python/pbi_apply.py` writes reviewed changes into a PBIP project: measure, calculated column, calculated table, relationship, RLS role, shared Power Query expression, or a TMDL draft. The `Apply-PowerBIPBIP*.ps1` scripts wrap it for Windows. Details: `$PLUGIN_ROOT/docs/pbip-apply-engine.md`.
- `Undo-PowerBIPBIPApply.ps1` (or `pbi_apply.py undo`) restores the last zip backup; `Invoke-PowerBIPBIPApplyPlan.ps1` and `pbi_apply.py history` list what was applied.

Apply workflow (always in this order):

1. Identify the PBIP project (folder or `.pbip`; never PBIX/PBIT) and the change. Prefer working on a copy of the project.
2. Dry run: `python3 -I "$PLUGIN_ROOT/scripts/python/pbi_apply.py" measure <PBIP> --table … --name … --expression …` (no `--apply`). Show the user the target file, the action (insert/replace/skip) and the TMDL block, and explain dependencies and rollback.
3. Only after the user approves: re-run with `--apply`. Report the backup id.
4. Tell the user to close the project in Power BI Desktop and reopen the `.pbip` (Desktop validates TMDL on open), and to refresh if calculated tables or columns were added.
5. Verify: re-run the review on the project, and if Desktop is open, check values live with `/powerbi-live-desktop` or `Invoke-PowerBILiveDaxQuery.ps1`.
6. If something is wrong: `pbi_apply.py undo <PBIP> --apply`, then reopen.

All scripts are in `$PLUGIN_ROOT/scripts/`. See [running scripts](running-scripts.md) for how to run them here.
