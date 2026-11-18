# Golden Baselines

Golden baselines protect the plugin from semantic regressions in parser, scanner, and graph behavior.

Run them locally:

```powershell
.\scripts\Test-PowerBIGoldenBaselines.ps1
```

Baseline definitions live in:

```text
.\rules\powerbi-golden-baselines.json
```

Each baseline points to an example model and asserts:

- metric count
- dependency edge count
- insight finding count
- minimum risk score
- required measure names

Add a new baseline by creating a compact example folder under `.\examples`, then adding a matching entry to `powerbi-golden-baselines.json`.
