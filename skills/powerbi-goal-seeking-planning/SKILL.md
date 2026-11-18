---
name: powerbi-goal-seeking-planning
description: "Reverse-plans what must happen to hit a Power BI revenue, budget, roll, margin, cash, or service target: gap decomposition, required backlog conversion, required demand uplift, and feasibility labels. Use when someone asks \"what do we need to hit budget\", \"Zielerreichung rückwärts rechnen\", \"Lücke zum Budget schließen\", or \"goal seek the target\"."
disable-model-invocation: true
---

# Power BI Goal-Seeking Planning

Use this skill when the question is "What must happen to hit the target?" rather than "What will happen?"

## Workflow

1. Select target: budget, roll forecast, prior year, management target, margin, or cash.
2. Calculate current plan gap by month.
3. Decompose the required change:
   - actual-to-date contribution
   - expected backlog conversion
   - residual demand required
   - customer/product gap drivers
4. Rank feasible levers:
   - improve conversion
   - pull forward backlog
   - recover customer demand
   - substitute product/customer demand
   - challenge the target if infeasible
5. Label target feasibility:
   - `achievable`
   - `stretch`
   - `unlikely`
   - `not_supported_by_data`

## Required outputs

- `forecast_month`
- `target_name`
- `target_value`
- `current_forecast`
- `target_gap`
- `required_backlog_conversion`
- `required_residual_demand`
- `top_required_segments`
- `feasibility`
- `explanation`

## Guardrails

- Do not treat target closure as evidence that the target is realistic.
- Separate mathematically required revenue from operationally feasible revenue.
