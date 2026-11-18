---
name: powerbi-change
description: "Writes a reviewed change into a Power BI project (PBIP/TMDL) with dry run, approval, zip backup and undo: add or replace a measure, calculated column, calculated table, relationship, RLS role, or Power Query expression, add a report page with KPI cards, or undo the last change. Use when someone types /powerbi-change or asks to \"add this measure to my PBIP\", \"apply the fix to the project\", \"undo the last model change\" or \"schreib die Measure ins Projekt\"."
argument-hint: "<PBIP project> <what to change, or 'undo'>"
disable-model-invocation: true
---

# Power BI Change (PBIP apply)

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-change/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_apply.py" …`.

Engine: `$PLUGIN_ROOT/scripts/python/pbi_apply.py` (stdlib Python). Reference: `$PLUGIN_ROOT/docs/pbip-apply-engine.md`.

1. **Find the project.** It must be a PBIP project (folder with `*.SemanticModel/definition` or a `.pbip` file). Never change PBIX/PBIT files: if only a PBIX exists, explain that the user must save it as a Power BI project first (File → Save as → `.pbip`). If the project is on the user's computer, work on it in the connected folder; suggest a copy for the first change.
2. **Understand the change.** Turn the request into one engine command per object: `measure`, `column`, `table`, `relationship`, `role`, `query`, `page` (a report page with one card per measure; needs a PBIR report), or `tmdl` (for a draft file; add `--table` when it holds only a measure or column). Check the table and column names against the model (`pbi_toolkit.py summary <PBIP>`). Write correct DAX; prefer `DIVIDE` over `/`, and give measures a format string and description.
3. **Dry run** (no `--apply`) and show the user, for each change: target file, action (insert / replace / skip) and the TMDL block. Say what depends on a replaced object (`pbi_toolkit.py dependencies <PBIP>`).
4. **Ask for approval.** Apply nothing until the user says yes in chat. Then re-run the same commands with `--apply` and report each backup id.
5. **Validate.** Re-run `pbi_toolkit.py review <PBIP> --out <folder>` and compare with before. Tell the user to close the project in Power BI Desktop and reopen the `.pbip` (Desktop validates TMDL on open) and to refresh if a calculated column or table was added. If Desktop is open afterwards, offer `/powerbi-live-desktop` or a DAX check to verify values live.
6. **Undo on request:** `pbi_apply.py undo <PBIP>` as a dry run (lists files to restore and to move aside), then `--apply` after approval. `pbi_apply.py history <PBIP>` lists all changes.

On Windows without Python, the same changes run through the PowerShell wrappers (`Apply-PowerBIPBIPMeasureDraft.ps1 … -Apply`, `Undo-PowerBIPBIPApply.ps1`); they call the same engine and need Python on the machine too.

Rules: one approval covers only the changes shown in that dry run. Never delete files: undo moves them to `.pbip-apply/undone/`. Never publish, refresh against a service, or sign in.
