---
name: powerbi-live-desktop
description: "Reviews the model that is open right now in Power BI Desktop on the user's Windows computer (read-only): live connection, model summary, DAX query checks, VertiPaq size, metadata governance, and a live fix backlog. Use when someone types /powerbi-live-desktop or asks to \"check my open Power BI Desktop file\" or \"prüf das geöffnete Modell in Power BI Desktop\"."
argument-hint: "[window title of the model, or empty for all open models]"
disable-model-invocation: true
---

# Live Power BI Desktop Review (read-only)

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-live-desktop/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

Live access runs on the user's Windows computer, never in the Linux workspace. Follow route 3 in `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md`.

1. **Prerequisites.** Confirm that Power BI Desktop is open with the model loaded, and find where the plugin folder is on Windows (default suggestion: `C:\temp\ClaudeWork\PowerbiPlugin\pbi-workbench`). Pick an output folder inside a connected folder, for example `C:\temp\ClaudeWork\PowerbiPlugin\out\live-<date>`.
2. **Easiest:** ask the user to double-click `scripts\Run-PowerBILiveReview.cmd` in the plugin folder, or do it with computer use if available and the user agrees (File Explorer allows double-click). Arguments: `[output folder] [window title]`. Without a title it reviews **every** open Desktop model into `<output>\<title>\` (live auto review, `vertipaq.md`, `metadata-governance.md`) and writes `index.md`, `summary.json` and `DONE.txt`. A small wrapper `.cmd` in a connected folder can pass the arguments, for example `call "<plugin>\scripts\Run-PowerBILiveReview.cmd" "C:\temp\out\live" "Finoryx"`.

   **Alternatively, give the user one block to paste into Windows PowerShell:**
   ```powershell
   cd <plugin folder>
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-PowerBILiveReviewAll.ps1 -OutputDirectory '<output folder>' [-Title '<window title>']
   ```
   `Resolve-PowerBILiveTarget.ps1 -Json` lists the open models with their window titles; every live script also takes `-Server 'Data Source=localhost:<port>'`, and `Resolve-PowerBILiveTarget.ps1` / `Get-PowerBIDesktopLiveConnection.ps1` take `-Title`.
   If computer use is available and the user agrees, run it yourself on their computer.
3. **Read the outputs** from the connected folder (start with `index.md`). If the connection status is `NoLiveTarget`, explain that Power BI Desktop must be open with a model loaded, and stop.
4. **Report:** live model summary, failing or suspicious measures (with live values where available), largest columns and tables by memory, metadata/governance gaps, and the live fix backlog in priority order. Label everything `live (Power BI Desktop, read-only)`.
5. **Optional:** offer specific DAX checks with `Invoke-PowerBILiveDaxQuery.ps1 -Query "EVALUATE …"`, and a comparison with the PBIP files via `Compare-PowerBILiveRepoModel.ps1`.

Never write to the live model, never refresh, sign in, or publish.
