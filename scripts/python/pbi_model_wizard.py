"""Power BI Model Wizard (no PowerShell required).

Python counterpart of New-PowerBIModelWizard.ps1 with the same output contract
(schema codex.powerbi.modelWizard.v1, model-drafts/ folder) plus:
  * column type inference from sample rows (CSV / JSON)
  * key detection and relationship drafts between facts and dimensions
  * Power Query drafts that match the source type (CSV, JSON, Excel, declared connectors)
  * TMDL table and measure drafts with concrete base DAX (SUM / COUNTROWS / DIVIDE)

It never creates PBIX/PBIT binaries, never stores credentials, and never publishes.

Usage:
  python3 pbi_model_wizard.py --project-name Sales --output-directory OUT \
      [--business-purpose TEXT] [--source FILE ...] [--source-config JSON] \
      [--fact NAME ...] [--dimension NAME ...] [--kpi NAME ...] [--initialize]
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
import sys
from pathlib import Path

FACT_HINT = re.compile(r"(?i)sales|order|transaction|fact|invoice|event|activity|booking|shipment|payment|journal|ticket")
DATE_HINT = re.compile(r"(?i)date|datum|month|monat|year|jahr|time|zeit|period")
AMOUNT_HINT = re.compile(r"(?i)amount|betrag|revenue|umsatz|sales|value|wert|cost|kosten|quantity|menge|qty|price|preis|margin")
KEY_HINT = re.compile(r"(?i)(key|id|nr|no|number|code)$")
SECRET = re.compile(r"(?i)(password|pwd|access[_ -]?token|client[_ -]?secret|secret|apikey|api[_ -]?key)\s*=\s*[^;\s]+")


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def q(name: str) -> str:
    """TMDL/DAX identifier quoting."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


def infer_type(values: list[str]) -> str:
    vals = [v.strip() for v in values if v is not None and str(v).strip() != ""]
    if not vals:
        return "string"
    if all(re.fullmatch(r"-?\d+", v) for v in vals):
        return "int64"
    if all(re.fullmatch(r"-?\d+([.,]\d+)?", v) for v in vals):
        return "decimal"
    if all(re.fullmatch(r"(true|false|wahr|falsch|yes|no|0|1)", v, re.I) for v in vals) and len(set(v.lower() for v in vals)) <= 2:
        return "boolean"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?|\d{1,2}[./]\d{1,2}[./]\d{2,4}", v) for v in vals):
        return "dateTime"
    return "string"


def sniff_csv(path: Path) -> tuple[list[str], list[dict], str]:
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = list(csv.DictReader(raw.splitlines(), delimiter=delim))
    cols = list(rows[0].keys()) if rows else (raw.splitlines()[0].split(delim) if raw.strip() else [])
    return cols, rows[:200], delim


def profile_file(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Data source not found or not a file: {path}")
    ext = path.suffix.lower()
    cols, rows, delim = [], [], None
    if ext in (".csv", ".txt", ".tsv"):
        cols, rows, delim = sniff_csv(path)
    elif ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and "value" in data:
            data = data["value"]
        rows = data[:200] if isinstance(data, list) else [data]
        rows = [r for r in rows if isinstance(r, dict)]
        cols = list(rows[0].keys()) if rows else []
        rows = [{k: ("" if v is None else str(v)) for k, v in r.items()} for r in rows]
    columns = []
    for c in cols:
        sample = [r.get(c, "") for r in rows]
        non_empty = [s for s in sample if str(s).strip()]
        columns.append({"name": c, "dataType": infer_type(sample),
                        "distinct": len(set(non_empty)), "rows": len(non_empty),
                        "unique": bool(non_empty) and len(set(non_empty)) == len(non_empty)})
    return {"name": safe_name(path.stem), "path": str(path.resolve()), "extension": ext, "connectorKind": {
        ".csv": "Text/CSV", ".txt": "Text/CSV", ".tsv": "Text/CSV", ".json": "JSON", ".xlsx": "Excel Workbook", ".parquet": "Parquet"}.get(ext, "File"),
        "delimiter": delim, "columns": [c["name"] for c in columns] or
        ["Schema inspection requires CSV or JSON; define fields in the generated data contract."],
        "columnProfiles": columns, "mode": "Import", "status": "LocallyProfiled" if columns else "SchemaRequiredInDesktop"}


def profile_declared(config_path: Path) -> list[dict]:
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if cfg.get("schema") != "codex.powerbi.dataSourceConfig.v1":
        raise SystemExit("Unsupported data source configuration schema (expected codex.powerbi.dataSourceConfig.v1).")
    out = []
    for s in cfg.get("sources", []):
        if not s.get("name") or not s.get("connectorKind"):
            raise SystemExit("Every declared source requires name and connectorKind.")
        cols = list(s.get("columns") or [])
        out.append({"name": safe_name(s["name"]), "path": SECRET.sub(lambda m: m.group(1) + "=[REDACTED]", str(s.get("connection", ""))),
                    "extension": "DeclaredConnector", "connectorKind": s["connectorKind"], "delimiter": None, "columns": cols,
                    "columnProfiles": [{"name": c, "dataType": "dateTime" if DATE_HINT.search(c) else
                                        ("decimal" if AMOUNT_HINT.search(c) else ("int64" if KEY_HINT.search(c) else "string")),
                                        "unique": False} for c in cols],
                    "mode": s.get("mode") or "Import", "status": "DeclaredSchema" if cols else "SchemaRequiredInDesktop"})
    return out


def m_query(p: dict) -> str:
    path = p["path"].replace('"', '""')
    types = ", ".join(f'{{"{c["name"]}", {mtype(c["dataType"])}}}' for c in p["columnProfiles"])
    typed = f",\n    Typed = Table.TransformColumnTypes(Promoted, {{{types}}})" if types else ""
    last = "Typed" if types else "Promoted"
    kind = p["connectorKind"]
    if kind == "Text/CSV":
        delim = p.get("delimiter") or ","
        delim = "#(tab)" if delim == "\t" else delim
        return ("let\n    // Replace the path with a parameter (e.g. SourceFolder) before publishing.\n"
                f'    Source = Csv.Document(File.Contents("{path}"), [Delimiter="{delim}", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
                f"    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]){typed}\nin\n    {last}")
    if kind == "JSON":
        return ("let\n    // Replace the path with a parameter before publishing.\n"
                f'    Source = Json.Document(File.Contents("{path}")),\n'
                "    Rows = if Value.Is(Source, type record) and Record.HasFields(Source, \"value\") then Source[value] else Source,\n"
                "    Promoted = Table.FromRecords(Rows)" + typed.replace("Promoted, {", "Promoted, {") + f"\nin\n    {last}")
    return ("let\n"
            f"    // Connector: {kind}. Build this source in Power BI Desktop > Get Data > {kind},\n"
            "    // then paste the generated steps here. Credentials stay in Desktop or the gateway.\n"
            f'    Source = error "Configure connector \'{kind}\' for {p["name"]} ({path or "endpoint alias"}) in Power BI Desktop"\n'
            "in\n    Source")


def mtype(dt: str) -> str:
    return {"int64": "Int64.Type", "decimal": "type number", "boolean": "type logical", "dateTime": "type datetime"}.get(dt, "type text")


def design(args) -> dict:
    profiles = [profile_file(Path(p)) for p in args.source] + (profile_declared(Path(args.source_config)) if args.source_config else [])
    sources = [p["name"] for p in profiles] or args.source_name or ["Define primary source"]
    inferred_facts = [p["name"] for p in profiles if FACT_HINT.search(p["name"])]
    if args.fact:
        facts = args.fact
    elif inferred_facts:
        facts = ["Fact" + n for n in inferred_facts]
    elif profiles:
        facts = ["Fact" + profiles[0]["name"]]
    else:
        facts = ["FactSales"]
    fact_sources = {("Fact" + p["name"]): p for p in profiles}
    dim_sources = [p for p in profiles if ("Fact" + p["name"]) not in facts]
    date_cols = sorted({c for p in profiles for c in p["columns"] if DATE_HINT.search(c)})
    if args.dimension:
        dims = args.dimension
    else:
        dims = ["Dim" + p["name"] for p in dim_sources] + (["DimDate"] if date_cols else [])
        dims = dims or ["DimDate", "DimEntity"]

    # relationships: fact column name == unique column in a dimension source
    rels = []
    for f in facts:
        fp = fact_sources.get(f)
        if not fp:
            continue
        for dp in dim_sources:
            for dc in dp["columnProfiles"]:
                if dc["name"] in fp["columns"] and (dc.get("unique") or KEY_HINT.search(dc["name"])):
                    rels.append({"from": f"{f}[{dc['name']}]", "to": f"Dim{dp['name']}[{dc['name']}]", "cardinality": "many-to-one",
                                 "crossFilter": "single", "confidence": "high" if dc.get("unique") else "medium"})
        for c in fp["columnProfiles"]:
            if c["dataType"] == "dateTime" and "DimDate" in dims:
                rels.append({"from": f"{f}[{c['name']}]", "to": "DimDate[Date]", "cardinality": "many-to-one", "crossFilter": "single",
                             "confidence": "high", "active": not any(r["to"] == "DimDate[Date]" and r["from"].startswith(f + "[") for r in rels)})

    measures = []
    main = fact_sources.get(facts[0])
    if args.kpi:
        measures = [{"name": k, "table": facts[0], "expression": "TODO: define approved DAX expression", "formatString": None} for k in args.kpi]
    elif main:
        amounts = [c["name"] for c in main["columnProfiles"] if c["dataType"] in ("decimal", "int64") and AMOUNT_HINT.search(c["name"])]
        for a in amounts[:3]:
            is_int = next(c["dataType"] for c in main["columnProfiles"] if c["name"] == a) == "int64"
            measures.append({"name": f"Total {a}", "table": facts[0], "expression": f"SUM({q(facts[0])}[{a}])",
                             "formatString": "#,0" if is_int else "#,0.00"})
        measures.append({"name": "Record Count", "table": facts[0], "expression": f"COUNTROWS({q(facts[0])})", "formatString": "#,0"})
        if amounts and "DimDate" in dims:
            base = f"[Total {amounts[0]}]"
            measures.append({"name": f"Total {amounts[0]} PY", "table": facts[0],
                             "expression": f"CALCULATE({base}, SAMEPERIODLASTYEAR(DimDate[Date]))", "formatString": "#,0.00"})
            measures.append({"name": f"Total {amounts[0]} YoY %", "table": facts[0],
                             "expression": f"DIVIDE({base} - [Total {amounts[0]} PY], [Total {amounts[0]} PY])", "formatString": "0.0%"})
    else:
        measures = [{"name": n, "table": facts[0], "expression": "TODO: define approved DAX expression", "formatString": None}
                    for n in ("Record Count", "Trend %", "Data Freshness")]

    return {
        "schema": "codex.powerbi.modelWizard.v1", "generator": "pbi_model_wizard.py", "projectName": args.project_name,
        "businessPurpose": args.business_purpose, "evidenceMaturity": "Draft",
        "architecture": {"pattern": "StarSchema", "factTables": facts, "dimensionTables": dims, "sourceNames": sources,
                         "sourceProfiles": profiles, "relationships": rels,
                         "connectorSupport": "Any connector available in the user's installed Power BI Desktop Get Data experience can be declared by connectorKind."},
        "semanticPlan": {"measures": [m["name"] for m in measures], "measureDrafts": measures,
                         "requiredPolicies": ["Assign KPI owner", "Add measure descriptions", "Define RLS roles", "Define freshness SLO", "Add semantic tests"]},
        "reportPlan": {"pages": ["Executive Overview", "Trend and Drivers", "Detail Explorer", "Data Quality"], "firstPageKpis": [m["name"] for m in measures]},
        "safeNextSteps": ["Create a new PBIP project in Power BI Desktop.", "Copy reviewed model and report drafts into the PBIP project.",
                          "Configure credentials only in Power BI Desktop or an approved gateway.",
                          "Run semantic tests and open the project in Power BI Desktop before publishing."],
        "binaryBoundary": "The wizard does not create or modify PBIX/PBIT binaries and does not publish to Power BI or Fabric.",
    }


def tmdl_table(name: str, profile: dict | None, measures: list[dict], is_date=False) -> str:
    lines = [f"table {q(name)}"]
    if is_date:
        lines.append("\tdataCategory: Time")
    lines.append("")
    for m in measures:
        lines.append(f"\t/// TODO: business definition, grain, accepted filters")
        lines.append(f"\tmeasure {q(m['name'])} = {m['expression']}")
        if m.get("formatString"):
            lines.append(f"\t\tformatString: {m['formatString']}")
        lines.append("\t\tannotation Owner = TODO")
        lines.append("")
    if is_date:
        lines += ["\tcolumn Date", "\t\tdataType: dateTime", "\t\tisKey", "\t\tsummarizeBy: none", "\t\tsourceColumn: [Date]", "",
                  f"\tpartition {q(name)} = calculated", "\t\tmode: import",
                  "\t\tsource = CALENDARAUTO()", ""]
    elif profile:
        for c in profile["columnProfiles"]:
            lines += [f"\tcolumn {q(c['name'])}", f"\t\tdataType: {c['dataType']}",
                      f"\t\tsummarizeBy: {'sum' if c['dataType'] in ('decimal', 'int64') and AMOUNT_HINT.search(c['name']) and not KEY_HINT.search(c['name']) else 'none'}",
                      f"\t\tsourceColumn: {c['name']}", ""]
        lines += [f"\tpartition {q(name)} = m", f"\t\tmode: {'directLake' if profile.get('mode', '').lower() == 'direct lake' else 'import'}", "\t\tsource ="]
        lines += ["\t\t\t\t" + l for l in m_query(profile).splitlines()]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def initialize(d: dict, out_dir: Path) -> Path:
    root = out_dir / d["projectName"]
    if root.exists():
        raise SystemExit(f"Project directory already exists: {root}")
    drafts = root / "model-drafts"
    (drafts / "tmdl" / "tables").mkdir(parents=True)
    arch = d["architecture"]
    dump = lambda o: json.dumps(o, indent=2, ensure_ascii=False) + "\n"
    (drafts / "model-design.json").write_text(dump(d), encoding="utf-8")
    (drafts / "data-contract-draft.json").write_text(dump({
        "schema": "codex.powerbi.dataContractDraft.v1", "sources": arch["sourceNames"], "facts": arch["factTables"],
        "dimensions": arch["dimensionTables"], "relationships": arch["relationships"],
        "rules": ["Keys must be non-null and unique in dimensions.", "Fact tables must reference dimensions through defined keys.",
                  "Every KPI must declare owner, grain, format, and refresh expectation."]}), encoding="utf-8")
    (drafts / "connection-drafts.json").write_text(dump([{
        "name": p["name"], "connectorKind": p["connectorKind"], "connection": p["path"], "mode": p["mode"], "columns": p["columns"],
        "status": "ConfigureInPowerBIDesktop" if p["extension"] == "DeclaredConnector" else "LocallyProfiled",
        "credentialPolicy": "Configure credentials only in Power BI Desktop or an approved gateway; never store secrets in this draft."}
        for p in arch["sourceProfiles"]]), encoding="utf-8")
    (drafts / "measure-drafts.json").write_text(dump([{
        "measureName": m["name"], "tableName": m["table"], "expression": m["expression"], "formatString": m.get("formatString"),
        "owner": "TODO: assign owner", "description": "TODO: define business meaning"} for m in d["semanticPlan"]["measureDrafts"]]), encoding="utf-8")
    pq = ["# Power Query Source Drafts", ""]
    for p in arch["sourceProfiles"]:
        pq += [f"## {p['name']} ({p['connectorKind']})", "", "```powerquery", m_query(p), "```", ""]
    if not arch["sourceProfiles"]:
        pq.append("Add local CSV/JSON source paths or a data source config to generate source drafts.")
    (drafts / "power-query-source-drafts.md").write_text("\n".join(pq) + "\n", encoding="utf-8")

    by_name = {"Fact" + p["name"]: p for p in arch["sourceProfiles"]} | {"Dim" + p["name"]: p for p in arch["sourceProfiles"]}
    for t in arch["factTables"] + arch["dimensionTables"]:
        ms = [m for m in d["semanticPlan"]["measureDrafts"] if m["table"] == t]
        (drafts / "tmdl" / "tables" / f"{safe_name(t)}.tmdl").write_text(
            tmdl_table(t, by_name.get(t), ms, is_date=(t == "DimDate")), encoding="utf-8")
    rel_lines = []
    for k, r in enumerate(arch["relationships"], 1):
        f_t, f_c = r["from"][:-1].split("[", 1)
        t_t, t_c = r["to"][:-1].split("[", 1)
        rel_lines += [f"relationship draft_{k:03d}"] + (["\tisActive: false"] if r.get("active") is False else []) + \
                     [f"\tfromColumn: {q(f_t)}.{q(f_c)}", f"\ttoColumn: {q(t_t)}.{q(t_c)}", ""]
    (drafts / "tmdl" / "relationships.tmdl").write_text("\n".join(rel_lines) or "// no relationships inferred\n", encoding="utf-8")

    readme = ["# Power BI Model Wizard Drafts", "", f"Business purpose: {d['businessPurpose']}", "",
              f"Generated: {_dt.datetime.now().replace(microsecond=0).isoformat()} · Evidence maturity: Draft", "",
              "## Star schema", "", f"- Facts: {', '.join(arch['factTables'])}", f"- Dimensions: {', '.join(arch['dimensionTables'])}", "",
              "## Relationships (inferred)", ""] + \
             [f"- {r['from']} → {r['to']} ({r['confidence']} confidence{'' if r.get('active', True) else ', inactive'})" for r in arch["relationships"]] + \
             ["", "## Generated from data sources", ""] + [f"- {p['name']} ({p['connectorKind']}): {p['path']}" for p in arch["sourceProfiles"]] + \
             ["", "## Next steps", "", "1. In Power BI Desktop, create a new project and save it as PBIP.",
              "2. Build the sources from `model-drafts/power-query-source-drafts.md` (credentials only in Desktop).",
              "3. Compare `model-drafts/tmdl/` with the PBIP `definition/` folder and copy reviewed tables, measures, and relationships.",
              "4. Fill every TODO (owner, description), then run the offline review (`pbi_toolkit.py review`) or `Invoke-PowerBIUnifiedReview.ps1`.",
              "", "These drafts are not a PBIP project and must be reviewed before being applied."]
    (root / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return drafts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Power BI model wizard (draft design pack)")
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--output-directory", default=".")
    ap.add_argument("--business-purpose", default="Describe the decision this model should support.")
    ap.add_argument("--source", action="append", default=[], help="local CSV/JSON file (repeatable)")
    ap.add_argument("--source-config", help="JSON file with schema codex.powerbi.dataSourceConfig.v1")
    ap.add_argument("--source-name", action="append", default=[])
    ap.add_argument("--fact", action="append", default=[])
    ap.add_argument("--dimension", action="append", default=[])
    ap.add_argument("--kpi", action="append", default=[])
    ap.add_argument("--initialize", action="store_true", help="write the draft folder")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", a.project_name):
        ap.error("project name must contain only letters, numbers, spaces, underscores, or hyphens")
    d = design(a)
    if a.initialize:
        d["initializedDraftDirectory"] = str(initialize(d, Path(a.output_directory)))
    print(json.dumps(d, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
