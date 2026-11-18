---
name: powerbi-forecast
description: "Runs the plugin's AI sales forecast engine on exported Power BI data (customer/product/month rows with actuals, backlog, budget, and roll forecast), with backtest, model quality, top deltas, and a management summary, then hands off to the war room, rescue, goal-seeking, or agent-council skills. Use when someone types /powerbi-forecast or asks to \"forecast revenue from this export\" or \"Umsatz-Forecast rechnen\"."
argument-hint: "<rows.json or CSV export> [as-of date] [forecast year]"
disable-model-invocation: true
---

# Power BI AI Forecast

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-forecast/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

1. **Input.** Take the file from the arguments or the connected folders. The engine expects the JSON shape of `$PLUGIN_ROOT/examples/ai-forecast/segment-monthly.json` (`{"rows": [...]}`). For CSV or Excel exports, convert to that shape with a short Python step and show the column mapping you used. Ask only for mappings you cannot infer.
2. **Run** (as-of date defaults to today, forecast year to the current year):
   ```bash
   python3 "$PLUGIN_ROOT/scripts/support/powerbi_ai_forecast.py" --input "<rows.json>" --output-directory "<out>" \
     --as-of-date YYYY-MM-DD --forecast-year YYYY --start-month M --end-month 12 --horizon-months 3 --backtest
   ```
   On Windows with an open Power BI Desktop model, `Invoke-PowerBIAIForecast.ps1` can read the data live (route 3 in `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md`).
3. **Read** the summary, detail, top deltas, and model quality outputs. Compare WAPE and bias with the roll forecast. If the model is worse than the roll forecast, mark every number `advisory_only`.
4. **Report:** forecast vs. budget vs. roll per month, the five largest deltas with customer/product and reason, model quality, and confidence.
5. **Offer the next step** that fits the result: `powerbi-forecast-war-room` (management review), `powerbi-revenue-rescue-mode` (close a gap), `powerbi-goal-seeking-planning` (what it takes to hit budget), `powerbi-autonomous-forecast-agents` (challenge the forecast), `powerbi-causal-counterfactual-forecasting` (why it moved).

Keep AI forecast values separate from committed management numbers.
