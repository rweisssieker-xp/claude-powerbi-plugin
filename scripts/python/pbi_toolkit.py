#!/usr/bin/env python3
"""Power BI offline toolkit (no PowerShell required).

Reads PBIP projects, TMDL folders, model.bim, simplified .dax exports and .pq
files and produces the same evidence the PowerShell scripts produce, using the
same rule files and schema names. Standard library only.

Usage:
  python3 pbi_toolkit.py <command> <path> [--out FILE_OR_DIR] [--json]

Commands:
  inventory       Power BI files found under <path>
  structure       PBIP/TMDL round-trip readiness            (Get-PowerBIPBIPStructure.ps1)
  summary         Tables, columns, measures, relationships   (New-PowerBIModelSummary.ps1)
  scan            DAX / Power Query / model risk findings    (Invoke-PowerBIInsightScan.ps1)
  catalog         KPI/metric catalog                         (New-PowerBIMetricCatalog.ps1)
  best-practices  Governance score                           (Test-PowerBIModelBestPractices.ps1)
  dependencies    Measure dependency graph and impact        (New-PowerBIDependencyGraph.ps1)
  trust           KPI trust score per measure                (New-PowerBIKpiTrustScore.ps1)
  gate            Offline Go/Warn/No-Go release gate         (approximates New-PowerBITrustReleaseGate.ps1)
  review          Runs all of the above into one folder (--out DIR required)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = PLUGIN_ROOT / "rules"
EVIDENCE = "local (python direct file analysis)"

TEXT_EXT = {".pbip", ".pbism", ".pbir", ".bim", ".tmdl", ".dax", ".pq", ".json"}
POWERBI_EXT = {".pbix", ".pbit", ".pbip", ".pbism", ".pbir", ".bim", ".tmdl", ".dax", ".pq"}
SEVERITY_SCORE = {"High": 3, "Medium": 2, "Low": 1}
TMDL_PROPERTY = re.compile(
    r"^(formatString|formatStringDefinition|displayFolder|lineageTag|sourceLineageTag|description|annotation|"
    r"changedProperty|isHidden|dataCategory|detailRowsDefinition|kpi|extendedProperty|dataType|summarizeBy|"
    r"sourceColumn|isKey|isNameInferred|isDataTypeInferred|sortByColumn|mode|queryGroup|expression)\b"
)


def now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def load_rules(name: str, default: dict) -> dict:
    path = RULES_DIR / name
    if path.exists():
        return json.loads(read_text(path))
    return default


def walk(root: Path):
    skip = {".git", "node_modules", "__pycache__", ".pbi", ".pbip-apply"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for f in sorted(filenames):
            yield Path(dirpath) / f


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1].replace("''", "'")
    return name


def indent_of(line: str) -> int:
    expanded = line.replace("\t", "    ")
    return len(expanded) - len(expanded.lstrip(" "))


# --------------------------------------------------------------------------- parsing

class Model:
    def __init__(self, root: Path):
        self.root = root
        self.files: list[Path] = []
        self.tables: dict[str, dict] = {}
        self.measures: list[dict] = []
        self.columns: list[dict] = []
        self.relationships: list[dict] = []
        self.partitions: list[dict] = []
        self.queries: list[dict] = []
        self.roles: list[dict] = []
        self.tmdl_objects: list[dict] = []
        self.formats: set[str] = set()
        self.report: dict | None = None
        self.column_stats: list[dict] = []
        self.notes: list[str] = []

    def table(self, name: str, source: str) -> dict:
        return self.tables.setdefault(name, {"name": name, "source": source, "hidden": False, "dataCategory": None})


def parse_model(root: Path) -> Model:
    if root.is_file():
        if root.suffix.lower() in (".pbix", ".pbit"):
            return parse_pbix(root)
        model = Model(root.parent)
        files = [root]
    else:
        model = Model(root)
        files = list(walk(root))
    for path in files:
        ext = path.suffix.lower()
        if ext in POWERBI_EXT or path.name in (".platform", "definition.pbir"):
            model.files.append(path)
        if ext not in TEXT_EXT:
            continue
        source = rel(root, path)
        try:
            text = read_text(path)
        except OSError:
            continue
        if ext == ".tmdl":
            model.formats.add("tmdl")
            parse_tmdl(model, text, source)
        elif ext == ".dax":
            model.formats.add("dax")
            parse_simple_dax(model, text, source)
        elif ext == ".pq":
            model.formats.add("pq")
            model.queries.append({"name": path.stem, "source": source, "expression": text,
                                  "lines": len(text.splitlines()), "hasLetExpression": bool(re.search(r"(?m)^\s*let\s*$", text))})
        elif ext == ".bim":
            model.formats.add("bim")
            parse_bim(model, text, source)
    if root.is_dir():
        entries = {rel(root, f).replace(os.sep, "/"): (lambda f=f: f.read_bytes()) for f in files
                   if f.suffix.lower() == ".json" and "/definition/" in rel(root, f).replace(os.sep, "/")
                   or f.name == "report.json"}
        if entries:
            model.report = parse_report(entries)
    return model


SIMPLE_DAX = re.compile(
    r"(?ms)^\s*(?:MEASURE\s+)?(?:(?P<table>'[^']+'|\w+)\s*)?\[(?P<name>[^\]\r\n=]+)\]\s*=\s*(?P<expr>.*?)"
    r"(?=^\s*(?:MEASURE\s+)?(?:(?:'[^']+'|\w+)\s*)?\[[^\]\r\n=]+\]\s*=|\Z)"
)


def parse_simple_dax(model: Model, text: str, source: str) -> None:
    for m in SIMPLE_DAX.finditer(text):
        name, expr = m.group("name").strip(), m.group("expr").strip()
        if name and expr:
            table = unquote(m.group("table") or "")
            model.measures.append({"name": name, "table": table, "expression": expr, "source": source,
                                   "formatString": None, "description": None, "owner": None,
                                   "displayFolder": None, "hidden": False})


TMDL_HEAD = re.compile(
    r"^(?P<kind>table|column|measure|relationship|partition|calculationGroup|calculationItem|role|tablePermission|expression|hierarchy|level)"
    r"\s+(?P<rest>.+?)\s*$"
)


def split_name_expr(rest: str) -> tuple[str, str | None]:
    """Split "'My Name' = expr" or "Name = expr" or "Name" into (name, expr)."""
    rest = rest.strip()
    if rest.startswith("'"):
        i = 1
        while i < len(rest):
            if rest[i] == "'" and (i + 1 >= len(rest) or rest[i + 1] != "'"):
                break
            i += 2 if rest[i] == "'" else 1
        name = rest[: i + 1]
        tail = rest[i + 1:].strip()
    else:
        parts = rest.split("=", 1)
        name = parts[0]
        tail = "=" + parts[1] if len(parts) > 1 else ""
    expr = None
    if tail.startswith("="):
        expr = tail[1:].strip()
    return unquote(name), expr


def parse_tmdl(model: Model, text: str, source: str) -> None:
    lines = text.splitlines()
    current_table = None
    pending_desc: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            i += 1
            continue
        head = TMDL_HEAD.match(stripped)
        if not head:
            if stripped:
                pending_desc = []
            i += 1
            continue
        kind, rest = head.group("kind"), head.group("rest")
        base_indent = indent_of(raw)
        name, expr = split_name_expr(rest)
        # collect the object's body (lines indented deeper than the header)
        body: list[str] = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if nxt.strip() and indent_of(nxt) <= base_indent:
                break
            body.append(nxt)
            j += 1
        desc = " ".join(pending_desc) or None
        pending_desc = []
        model.tmdl_objects.append({"kind": kind, "name": name, "source": source})

        if kind == "table":
            current_table = name
            t = model.table(name, source)
            first = min((indent_of(b) for b in body if b.strip()), default=0)
            for b in body:
                bs = b.strip()
                if not bs or indent_of(b) != first:
                    continue
                if bs == "isHidden":
                    t["hidden"] = True
                if bs.startswith("dataCategory:"):
                    t["dataCategory"] = bs.split(":", 1)[1].strip()
            i += 1  # children are parsed as their own headers
            continue

        props, expr_lines = split_props(body, base_indent)
        if expr is not None and expr == "" and expr_lines:
            expr = dedent_block(expr_lines)
        elif expr is not None and expr.startswith("```"):
            expr = dedent_block(expr_lines).replace("```", "").strip()

        if kind == "measure" and (expr or "").strip():
            model.measures.append({
                "name": name, "table": current_table or "", "expression": (expr or "").strip(), "source": source,
                "formatString": props.get("formatString"), "description": desc or props.get("description"),
                "owner": props.get("annotation:Owner") or props.get("annotation:MetricOwner"),
                "displayFolder": props.get("displayFolder"), "hidden": "isHidden" in props,
            })
        elif kind == "column":
            model.columns.append({
                "name": name, "table": current_table or "", "calculated": expr is not None,
                "expression": (expr or "").strip() or None, "dataType": props.get("dataType"),
                "hidden": "isHidden" in props, "source": source,
            })
        elif kind == "relationship":
            model.relationships.append({
                "name": name, "from": props.get("fromColumn"), "to": props.get("toColumn"),
                "crossFilteringBehavior": props.get("crossFilteringBehavior", "oneDirection"),
                "isActive": props.get("isActive", "true") != "false",
                "fromCardinality": props.get("fromCardinality", "many"), "toCardinality": props.get("toCardinality", "one"),
                "source": source,
            })
        elif kind == "partition":
            mexpr = None
            for k, b in enumerate(body):
                if b.strip().startswith("source ="):
                    after = b.strip()[len("source ="):].strip()
                    if not after:
                        lvl, block = indent_of(b), []
                        for x in body[k + 1:]:
                            if x.strip() and indent_of(x) <= lvl:
                                break
                            block.append(x)
                        after = dedent_block(block)
                    mexpr = after
                    break
            ptype = (expr or "").strip()
            model.partitions.append({"name": name, "table": current_table or "", "type": ptype,
                                     "mode": props.get("mode"), "expression": mexpr or "", "source": source})
        elif kind == "role":
            model.roles.append({"name": name, "source": source, "tablePermissions": []})
        elif kind == "tablePermission" and model.roles:
            model.roles[-1]["tablePermissions"].append({"table": name, "filter": (expr or "").strip()})
        elif kind == "expression":
            model.queries.append({"name": name, "source": source, "expression": expr or dedent_block(expr_lines),
                                  "lines": len(expr_lines) + 1, "hasLetExpression": "let" in (expr or "") + "".join(expr_lines)})
        i = j if kind in ("measure", "column", "partition", "relationship", "expression", "tablePermission", "calculationItem", "level") else i + 1


PROP_LINE = re.compile(
    r"^(annotation\s|source\s*=|isHidden$|isKey$|isNameInferred$|isDataTypeInferred$|showAsVariationsOnly$|isPrivate$|"
    r"[A-Za-z][A-Za-z0-9]*:(\s|$))"
)


def split_props(body: list[str], base_indent: int) -> tuple[dict, list[str]]:
    """Separate TMDL properties (one level below the header) from expression lines (deeper)."""
    props: dict = {}
    prop_levels = [indent_of(b) for b in body if b.strip() and PROP_LINE.match(b.strip())]
    prop_level = min(prop_levels) if prop_levels else None
    expr_lines: list[str] = []
    for b in body:
        s = b.strip()
        if not s:
            if not props:
                expr_lines.append(b)
            continue
        lvl = indent_of(b)
        if prop_level is not None and lvl == prop_level and PROP_LINE.match(s):
            if s.startswith("annotation"):
                m = re.match(r"annotation\s+(\S+)\s*=\s*(.*)", s)
                if m:
                    props["annotation:" + m.group(1)] = m.group(2).strip()
            elif s.startswith("source"):
                props["source"] = True
            elif ":" in s:
                k, v = s.split(":", 1)
                props[k.strip()] = v.strip()
            else:
                props[s] = True
            continue
        if not props and (prop_level is None or lvl > prop_level):
            expr_lines.append(b)
    return props, expr_lines


def dedent_block(lines: list[str]) -> str:
    nonblank = [l for l in lines if l.strip()]
    if not nonblank:
        return ""
    cut = min(indent_of(l) for l in nonblank)
    out = []
    for l in lines:
        e = l.replace("\t", "    ")
        out.append(e[cut:] if len(e) >= cut else e.strip())
    return "\n".join(out).strip()


def parse_bim(model: Model, text: str, source: str) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    m = data.get("model") if isinstance(data, dict) else None
    if not m:
        return
    join = lambda v: "\n".join(v) if isinstance(v, list) else (v or "")
    for t in m.get("tables", []):
        tn = t.get("name", "")
        model.table(tn, source)["hidden"] = bool(t.get("isHidden"))
        model.tables[tn]["dataCategory"] = t.get("dataCategory")
        model.tmdl_objects.append({"kind": "table", "name": tn, "source": source})
        for c in t.get("columns", []):
            model.columns.append({"name": c.get("name"), "table": tn, "calculated": c.get("type") == "calculated",
                                  "expression": join(c.get("expression")) or None, "dataType": c.get("dataType"),
                                  "hidden": bool(c.get("isHidden")), "source": source})
        for ms in t.get("measures", []):
            ann = {a.get("name"): a.get("value") for a in ms.get("annotations", []) if isinstance(a, dict)}
            model.measures.append({"name": ms.get("name"), "table": tn, "expression": join(ms.get("expression")).strip(),
                                   "source": source, "formatString": ms.get("formatString"),
                                   "description": join(ms.get("description")) or None,
                                   "owner": ann.get("Owner") or ann.get("MetricOwner"),
                                   "displayFolder": ms.get("displayFolder"), "hidden": bool(ms.get("isHidden"))})
        for p in t.get("partitions", []):
            src = p.get("source", {})
            model.partitions.append({"name": p.get("name"), "table": tn, "type": src.get("type", ""),
                                     "mode": p.get("mode"), "expression": join(src.get("expression")), "source": source})
    for r in m.get("relationships", []):
        model.relationships.append({
            "name": r.get("name"), "from": f"{r.get('fromTable')}.{r.get('fromColumn')}", "to": f"{r.get('toTable')}.{r.get('toColumn')}",
            "crossFilteringBehavior": r.get("crossFilteringBehavior", "oneDirection"), "isActive": r.get("isActive", True),
            "fromCardinality": r.get("fromCardinality", "many"), "toCardinality": r.get("toCardinality", "one"), "source": source})
    for role in m.get("roles", []):
        model.roles.append({"name": role.get("name"), "source": source,
                            "tablePermissions": [{"table": tp.get("name"), "filter": join(tp.get("filterExpression"))}
                                                 for tp in role.get("tablePermissions", [])]})


# --------------------------------------------------------------------------- PBIX / report

AUTO_DATE_PREFIX = ("LocalDateTable_", "DateTableTemplate_")


def parse_pbix(path: Path) -> Model:
    """Read a .pbix/.pbit: report definition with the standard library, the semantic model with pbixray (optional)."""
    import zipfile
    model = Model(path.parent)
    model.files.append(path)
    model.formats.add("pbix")
    source = path.name
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        model.notes.append(f"{source}: not a readable PBIX/PBIT archive")
        return model
    names = z.namelist()
    entries = {n: (lambda n=n: z.read(n)) for n in names
               if n.startswith("Report/") and (n.endswith(".json") or n == "Report/Layout")}
    model.report = parse_report(entries)
    model.report["file"] = source
    try:
        model.report["version"] = z.read("Version").decode("utf-16-le", errors="ignore").strip("\x00 ") if "Version" in names else None
    except Exception:  # noqa: BLE001
        model.report["version"] = None
    try:
        from pbixray import PBIXRay  # optional dependency: pip install pbixray
    except ImportError:
        model.notes.append("Semantic model not read: install the optional package `pbixray` (pip install pbixray) "
                           "or export the file as PBIP (File > Save as > Power BI project). Report-level checks still ran.")
        return model
    try:
        px = PBIXRay(str(path))
    except Exception as e:  # noqa: BLE001
        model.notes.append(f"pbixray could not read the data model ({type(e).__name__}: {e}). Export as PBIP for a full review.")
        return model
    model.formats.add("pbix-model")

    def frame(attr):
        try:
            df = getattr(px, attr)
            return df.to_dict("records") if df is not None and hasattr(df, "to_dict") else []
        except Exception as e:  # noqa: BLE001
            model.notes.append(f"pbixray: {attr} unavailable ({type(e).__name__})")
            return []

    def val(v):
        return None if v is None or (isinstance(v, float) and v != v) else v

    for t in list(px.tables):
        tbl = model.table(str(t), source)
        tbl["hidden"] = str(t).startswith(AUTO_DATE_PREFIX)
    for m in frame("dax_measures"):
        model.measures.append({"name": str(m.get("Name")), "table": str(m.get("TableName") or ""),
                               "expression": str(val(m.get("Expression")) or "").strip(), "source": source,
                               "formatString": None, "description": val(m.get("Description")), "owner": None,
                               "displayFolder": val(m.get("DisplayFolder")), "hidden": False})
    calc = {(str(c.get("TableName")), str(c.get("ColumnName"))): str(val(c.get("Expression")) or "") for c in frame("dax_columns")}
    for c in frame("schema"):
        key = (str(c.get("TableName")), str(c.get("ColumnName")))
        model.columns.append({"name": key[1], "table": key[0], "calculated": key in calc, "expression": calc.get(key),
                              "dataType": str(val(c.get("PandasDataType")) or ""), "hidden": False, "source": source})
    known = {(c["table"], c["name"]) for c in model.columns}
    for (t, n), e in calc.items():
        if (t, n) not in known:
            model.columns.append({"name": n, "table": t, "calculated": True, "expression": e, "dataType": "", "hidden": False, "source": source})
    for r in frame("relationships"):
        card = str(val(r.get("Cardinality")) or "M:1").split(":")
        model.relationships.append({
            "name": None, "from": f"{r.get('FromTableName')}.{r.get('FromColumnName')}", "to": f"{r.get('ToTableName')}.{r.get('ToColumnName')}",
            "crossFilteringBehavior": "bothDirections" if str(r.get("CrossFilteringBehavior")) == "Both" else "oneDirection",
            "isActive": bool(val(r.get("IsActive")) if val(r.get("IsActive")) is not None else True),
            "fromCardinality": "many" if card[0] == "M" else "one", "toCardinality": "many" if card[-1] == "M" else "one", "source": source})
    for q in frame("power_query"):
        model.partitions.append({"name": str(q.get("TableName")), "table": str(q.get("TableName")), "type": "m", "mode": None,
                                 "expression": str(val(q.get("Expression")) or ""), "source": source})
    roles: dict[str, dict] = {}
    for r in frame("rls"):
        role = roles.setdefault(str(r.get("RoleName")), {"name": str(r.get("RoleName")), "source": source, "tablePermissions": []})
        role["tablePermissions"].append({"table": str(r.get("TableName")), "filter": str(val(r.get("FilterExpression")) or "")})
    model.roles = list(roles.values())
    for st in frame("statistics"):
        size = sum(int(val(st.get(k)) or 0) for k in ("Dictionary", "HashIndex", "DataSize"))
        model.column_stats.append({"table": str(st.get("TableName")), "column": str(st.get("ColumnName")),
                                   "cardinality": int(val(st.get("Cardinality")) or 0), "bytes": size})
    try:
        model.report["modelBytes"] = int(px.size)
    except Exception:  # noqa: BLE001
        pass
    return model


def _field_refs(node, out: set, ctx=None):
    """Collect (kind, Entity, Property) references from a visual JSON tree.

    Filters and legacy queries address tables through aliases: "From": [{"Name": "f", "Entity": "Sales"}] plus
    "SourceRef": {"Source": "f"}. Aliases are resolved per subtree; unresolved aliases are skipped, never reported.
    """
    if isinstance(node, dict):
        if isinstance(node.get("From"), list):
            ctx = dict(ctx or {})
            ctx.update({f.get("Name"): f.get("Entity") for f in node["From"] if isinstance(f, dict) and f.get("Name") and f.get("Entity")})
        for kind in ("Measure", "Column"):
            v = node.get(kind)
            if isinstance(v, dict) and "Property" in v:
                ref = (v.get("Expression") or {}).get("SourceRef") or {}
                ent = ref.get("Entity") or (ctx or {}).get(ref.get("Source"))
                if ent:
                    out.add((kind, ent, v["Property"]))
        for v in node.values():
            _field_refs(v, out, ctx)
    elif isinstance(node, list):
        for v in node:
            _field_refs(v, out, ctx)


def parse_report(entries: dict) -> dict:
    """entries: relative path -> callable returning bytes. Handles PBIR (definition/pages/...) and legacy Report/Layout."""
    rep = {"format": None, "pages": [], "visuals": [], "customVisuals": [], "publicCustomVisuals": [], "theme": None}
    load = lambda k: json.loads(entries[k]().decode("utf-8-sig"))
    pbir_pages = {}
    for k in sorted(entries):
        if k.endswith("/page.json") and "/pages/" in k:
            try:
                pj = load(k)
            except Exception:  # noqa: BLE001
                continue
            pid = k.split("/pages/")[1].split("/")[0]
            pbir_pages[pid] = {"id": pid, "name": pj.get("displayName") or pid, "visuals": 0,
                               "hidden": pj.get("visibility") == "HiddenInViewMode",
                               "width": pj.get("width"), "height": pj.get("height")}
    if pbir_pages:
        rep["format"] = "PBIR"
        for k in sorted(entries):
            if not (k.endswith("/visual.json") and "/pages/" in k):
                continue
            pid = k.split("/pages/")[1].split("/")[0]
            try:
                vj = load(k)
            except Exception:  # noqa: BLE001
                continue
            v = vj.get("visual") or {}
            refs: set = set()
            _field_refs(v.get("query") or {}, refs)
            _field_refs(vj.get("filterConfig") or {}, refs)
            pos = vj.get("position") or {}
            rep["visuals"].append({"page": pbir_pages.get(pid, {}).get("name", pid), "name": vj.get("name"),
                                   "type": v.get("visualType") or ("group" if "visualGroup" in vj else "unknown"),
                                   "fields": sorted(f"{e}[{p}]" for _, e, p in refs), "refs": sorted(refs),
                                   "x": pos.get("x"), "y": pos.get("y"), "w": pos.get("width"), "h": pos.get("height"),
                                   "hidden": bool(vj.get("isHidden"))})
            if pid in pbir_pages:
                pbir_pages[pid]["visuals"] += 1
        order = []
        pk = next((k for k in entries if k.endswith("pages/pages.json")), None)
        if pk:
            try:
                order = load(pk).get("pageOrder") or []
            except Exception:  # noqa: BLE001
                order = []
        rep["pages"] = [pbir_pages[p] for p in order if p in pbir_pages] + [v for k, v in pbir_pages.items() if k not in order]
        rk = next((k for k in entries if k.endswith("definition/report.json")), None)
        if rk:
            try:
                rj = load(rk)
                rep["publicCustomVisuals"] = rj.get("publicCustomVisuals") or []
                rep["theme"] = ((rj.get("themeCollection") or {}).get("baseTheme") or {}).get("name")
            except Exception:  # noqa: BLE001
                pass
    elif "Report/Layout" in entries or "report.json" in entries:
        rep["format"] = "Legacy layout"
        raw = entries.get("Report/Layout") or entries.get("report.json")
        b = raw()
        try:
            lay = json.loads(b.decode("utf-16-le") if b[:2] != b"{\x00"[:2] and b[1:2] == b"\x00" else b.decode("utf-8-sig"))
        except Exception:  # noqa: BLE001
            try:
                lay = json.loads(b.decode("utf-16"))
            except Exception:  # noqa: BLE001
                lay = {}
        for sec in lay.get("sections", []):
            page = {"id": sec.get("name"), "name": sec.get("displayName") or sec.get("name"), "visuals": 0, "hidden": False,
                    "width": sec.get("width"), "height": sec.get("height")}
            for vc in sec.get("visualContainers", []):
                try:
                    cfg = json.loads(vc.get("config") or "{}")
                except json.JSONDecodeError:
                    cfg = {}
                sv = cfg.get("singleVisual") or {}
                refs: set = set()
                _field_refs(sv.get("prototypeQuery") or {}, refs)
                try:
                    _field_refs(json.loads(vc.get("filters") or "[]"), refs)
                except json.JSONDecodeError:
                    pass
                rep["visuals"].append({"page": page["name"], "name": cfg.get("name"), "type": sv.get("visualType") or "group",
                                       "fields": sorted(f"{e}[{p}]" for _, e, p in refs), "refs": sorted(refs),
                                       "x": vc.get("x"), "y": vc.get("y"), "w": vc.get("width"), "h": vc.get("height"), "hidden": False})
                page["visuals"] += 1
            rep["pages"].append(page)
        rep["publicCustomVisuals"] = lay.get("publicCustomVisuals") or []
    for k in sorted(entries):
        if k.startswith("Report/CustomVisuals/") and k.endswith("/package.json"):
            try:
                pj = load(k)
                vis = pj.get("visual") or {}
                rep["customVisuals"].append({"guid": vis.get("guid") or k.split("/")[2], "name": vis.get("displayName") or vis.get("name"),
                                             "version": vis.get("version"), "author": (pj.get("author") or {}).get("name")})
            except Exception:  # noqa: BLE001
                rep["customVisuals"].append({"guid": k.split("/")[2], "name": None, "version": None, "author": None})
    rep["pageCount"] = len(rep["pages"])
    rep["visualCount"] = len(rep["visuals"])
    return rep


def report_findings(model: Model, source: str) -> list[dict]:
    rep = model.report
    if not rep:
        return []
    fs = []
    have_model = bool(model.tables) or bool(model.measures)
    if have_model:
        cols = {(c["table"], c["name"]) for c in model.columns}
        meas = {(m["table"], m["name"]) for m in model.measures}
        meas_names = {m["name"] for m in model.measures}
        broken = []
        for v in rep["visuals"]:
            for kind, ent, prop in v["refs"]:
                ok = (ent, prop) in cols or (ent, prop) in meas or (kind == "Measure" and prop in meas_names)
                if not ok:
                    broken.append(f"{v['page']} / {v['type']}: {ent}[{prop}]")
        if broken:
            fs.append(finding("High", "Report Integrity", "Visual references a missing field",
                              f"{len(broken)} field reference(s) do not exist in the semantic model; these visuals show errors: " + "; ".join(broken[:6]),
                              source, "py.report.broken-field"))
        used = {p for v in rep["visuals"] for _, _, p in v["refs"]}
        referenced = set()
        for m in model.measures:
            referenced |= {r.group("name") for r in MEASURE_REF.finditer(strip_comments(m["expression"]))}
        unused = [m["name"] for m in model.measures if m["name"] not in used and m["name"] not in referenced]
        if unused and rep["visuals"]:
            fs.append(finding("Low", "Model Hygiene", "Measures not used in the report",
                              f"{len(unused)} measure(s) are not used by any visual or other measure: {', '.join(unused[:8])}. Remove, hide, or document them.",
                              source, "py.report.unused-measure"))
    embedded = [c for c in rep["customVisuals"] if c.get("guid") not in set(rep.get("publicCustomVisuals") or [])]
    if embedded:
        fs.append(finding("Medium", "Report Governance", "Custom visuals embedded from file",
                          f"{len(embedded)} custom visual(s) are packaged in the file instead of AppSource/organizational store: "
                          + ", ".join(sorted({c.get('name') or c['guid'] for c in embedded})[:6])
                          + ". Check certification, version pinning, and tenant settings for custom visuals.", source, "py.report.custom-visual"))
    dense = [p for p in rep["pages"] if p["visuals"] > 15]
    if dense:
        fs.append(finding("Low", "Report UX", "Dense report page",
                          "Pages with more than 15 visuals load slowly and overload readers: " + ", ".join(f"{p['name']} ({p['visuals']})" for p in dense),
                          source, "py.report.dense-page"))
    empty = [p["name"] for p in rep["pages"] if p["visuals"] == 0 and not p.get("hidden")]
    if empty:
        fs.append(finding("Low", "Report UX", "Empty report page", "Visible pages without visuals: " + ", ".join(empty), source, "py.report.empty-page"))
    return fs


# --------------------------------------------------------------------------- analyses

def inventory(root: Path, model: Model) -> list[dict]:
    items = []
    for p in model.files:
        st = p.stat()
        items.append({"Type": p.suffix.lstrip(".").upper() or p.name, "Name": p.name, "RelativePath": rel(root, p),
                      "SizeKB": round(st.st_size / 1024, 1),
                      "LastWriteTime": _dt.datetime.fromtimestamp(st.st_mtime).replace(microsecond=0).isoformat(),
                      "EditableText": p.suffix.lower() in {".pbip", ".pbism", ".bim", ".tmdl", ".dax", ".pq", ".pbir"}})
    return items


def structure(root: Path) -> dict:
    files = list(walk(root))
    dirs = [Path(d) for d, _, _ in os.walk(root)]
    pbip = [f for f in files if f.suffix.lower() == ".pbip"]
    sm = [d for d in dirs if d.name.endswith(".SemanticModel")]
    rp = [d for d in dirs if d.name.endswith(".Report")]
    tmdl = [f for f in files if f.suffix.lower() == ".tmdl"]
    report_meta = [f for f in files if f.name in ("report.json", "definition.pbir")]
    model_meta = [f for f in files if f.name in ("model.bim", "definition.pbism")]
    platform = [f for f in files if f.name == ".platform"]
    pbir = [f for f in files if f.name == "definition.pbir"]
    score = min(100, 20 * bool(pbip) + 20 * bool(sm) + 15 * bool(rp) + 20 * bool(tmdl) + 10 * bool(report_meta)
                + 15 * bool(model_meta) + 5 * bool(platform) + 5 * bool(pbir))

    def check(cid, name, passed, sev, detail):
        return {"id": cid, "name": name, "status": "Pass" if passed else sev, "passed": passed, "severity": sev, "detail": detail}

    checks = [
        check("pbip.entrypoint", "PBIP entry point", bool(pbip), "Fail", "A .pbip file is required as the source-controlled Desktop project entry point."),
        check("semantic.folder", "Semantic model folder", bool(sm), "Fail", "A *.SemanticModel folder is expected for realistic PBIP round-trip validation."),
        check("semantic.definition", "Semantic model definition", bool(tmdl or model_meta), "Fail", "TMDL files, model.bim, or definition.pbism should be present for model round-tripping."),
        check("report.folder", "Report folder", bool(rp), "Warn", "A *.Report folder is expected when validating report layout round-tripping."),
        check("report.definition", "Report definition", bool(report_meta), "Warn", "Report metadata such as definition.pbir or report.json should be present."),
        check("platform.metadata", "Platform metadata", bool(platform), "Warn", ".platform files are usually present in complete PBIP artifacts."),
    ]
    fails = sum(c["status"] == "Fail" for c in checks)
    warns = sum(c["status"] == "Warn" for c in checks)
    recs = []
    if not pbip:
        recs.append("Create or export a PBIP entry point for source-controlled Desktop round-tripping.")
    if not (sm or tmdl or model_meta):
        recs.append("Export the semantic model to TMDL or model.bim before requesting structural changes.")
    if not (rp or report_meta):
        recs.append("Export report metadata if layout or visual analysis is required.")
    if not platform:
        recs.append("Include .platform metadata from Desktop/Git export to improve PBIP completeness checks.")
    if not recs:
        recs.append("Project structure is ready for deeper model and report review.")
    return {
        "schema": "codex.powerbi.pbipStructure.v1", "root": str(root), "generated": now(), "evidence": EVIDENCE,
        "readiness": "Strong" if score >= 80 and fails == 0 else ("Partial" if score >= 40 else "Limited"),
        "roundtripStatus": "Incomplete" if fails else ("Warning" if warns else "Ready"), "score": score,
        "pbipRelativeFiles": [rel(root, f) for f in pbip], "semanticModelDirectories": [rel(root, d) for d in sm],
        "reportDirectories": [rel(root, d) for d in rp], "tmdlFileCount": len(tmdl),
        "reportMetadataFileCount": len(report_meta), "modelMetadataFileCount": len(model_meta),
        "platformMetadataFileCount": len(platform), "checks": checks, "recommendations": recs,
    }


MEASURE_REF = re.compile(r"(?<![\w'\]])\[(?P<name>[^\]]+)\]")
COLUMN_REF = re.compile(r"(?P<table>'[^']+'|[A-Za-z_][\w]*)\s*\[(?P<col>[^\]]+)\]")


def strip_comments(expr: str) -> str:
    expr = re.sub(r"/\*.*?\*/", " ", expr, flags=re.S)
    expr = re.sub(r"(--|//)[^\n]*", " ", expr)
    return re.sub(r'"(?:[^"]|"")*"', '""', expr)


def dependencies(model: Model) -> dict:
    names = {m["name"] for m in model.measures}
    nodes, edges = [], []
    for m in model.measures:
        expr = strip_comments(m["expression"])
        refs = sorted({r.group("name") for r in MEASURE_REF.finditer(expr) if r.group("name") in names})
        cols = sorted({f"{unquote(c.group('table'))}[{c.group('col')}]" for c in COLUMN_REF.finditer(expr)})
        nodes.append({"id": m["name"], "table": m["table"], "measures": refs, "columns": cols, "source": m["source"]})
        edges += [{"from": m["name"], "to": r} for r in refs]
    downstream: dict[str, set] = {n["id"]: set() for n in nodes}
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        stack = list(n["measures"])
        seen = set()
        while stack:
            d = stack.pop()
            if d in seen:
                continue
            seen.add(d)
            downstream.setdefault(d, set()).add(n["id"])
            stack += by_id.get(d, {}).get("measures", [])
    impact = sorted(({"measure": k, "dependentMeasures": sorted(v), "impactCount": len(v)} for k, v in downstream.items()),
                    key=lambda x: (-x["impactCount"], x["measure"]))
    return {"schema": "codex.powerbi.dependencyGraph.v1", "generated": now(), "evidence": EVIDENCE,
            "nodeCount": len(nodes), "edgeCount": len(edges), "nodes": nodes, "edges": edges, "impact": impact}


def finding(sev, category, title, detail, source, rule_id=None):
    return {"Severity": sev, "Score": SEVERITY_SCORE.get(sev, 0), "Category": category, "Title": title,
            "Detail": detail, "Source": source, "RuleId": rule_id}


def scan(root: Path, model: Model) -> dict:
    rules = load_rules("powerbi-governance-rules.json",
                       {"dax": [], "powerQuery": [], "thresholds": {"longMeasureLines": 20, "highRiskScore": 9, "mediumRiskScore": 4}})
    th = rules.get("thresholds", {})
    fs: list[dict] = []

    def apply(rule_list, text, source):
        for r in rule_list or []:
            if r.get("enabled") is False:
                continue
            if re.search("(?i)" + r["pattern"], text):
                fs.append(finding(r["severity"], r["category"], r["title"], r["detail"], source, r.get("id")))

    for f in model.files:
        if f.suffix.lower() in (".pbix", ".pbit"):
            fs.append(finding("Medium", "Source Control", "Binary report file",
                              "Binary PBIX/PBIT files limit transparent review and diff quality. Prefer PBIP export for governed changes.",
                              rel(root, f) if root in f.parents else f.name))
    for m in model.measures:
        src = f"{m['source']} :: {m['table']}[{m['name']}]"
        expr = strip_comments(m["expression"])
        apply(rules.get("dax"), expr, src)
        if len(m["expression"].splitlines()) > th.get("longMeasureLines", 20):
            fs.append(finding("Low", "DAX Maintainability", "Long measure expression",
                              "Long measures are harder to review and test. Consider variables, helper measures, or business-rule documentation.", src))
        if re.search(r"(?<![/*])/(?![/*])", expr) and "DIVIDE" not in expr.upper():
            fs.append(finding("Low", "DAX Robustness", "Division operator instead of DIVIDE",
                              "The / operator raises errors or infinity on zero denominators. DIVIDE handles blanks and zero safely.", src, "py.dax.divide"))
        if re.search(r"(?i)\bIFERROR\s*\(|\bISERROR\s*\(", expr):
            fs.append(finding("Medium", "DAX Performance", "IFERROR/ISERROR usage",
                              "Error trapping forces slower evaluation. Prefer DIVIDE or explicit checks.", src, "py.dax.iferror"))
        if m.get("formatString") is None and "tmdl" in model.formats and m["source"].endswith(".tmdl"):
            fs.append(finding("Low", "Model Usability", "Measure without format string",
                              "Unformatted measures render inconsistently across visuals and Copilot answers.", src, "py.measure.format"))
    pq_texts = [(q["expression"], q["source"]) for q in model.queries] + \
               [(p["expression"], f"{p['source']} :: partition {p['name']}") for p in model.partitions if p.get("expression")]
    for text, src in pq_texts:
        apply(rules.get("powerQuery"), text, src)
        if re.search(r"(?i)Web\.Contents\s*\(", text) and not re.search(r"(?i)RelativePath", text):
            fs.append(finding("Low", "Power Query Maintainability", "Web.Contents without RelativePath",
                              "Using RelativePath and Query options often improves gateway compatibility and credential scoping.", src))
        if re.search(r'(?i)File\.Contents\s*\(\s*"[A-Za-z]:\\', text):
            fs.append(finding("Medium", "Refresh Reliability", "Hard-coded local file path",
                              "A drive-letter path only refreshes on one machine. Use a parameter, SharePoint/OneDrive, or a gateway-reachable share.", src, "py.pq.drive-path"))
    for r in model.relationships:
        src = f"{r['source']} :: {r['from']} -> {r['to']}"
        if str(r.get("crossFilteringBehavior", "")).lower() == "bothdirections":
            fs.append(finding("Medium", "Model Semantics", "Bidirectional relationship",
                              "Both-direction filters can create ambiguous paths and slow queries. Prefer single direction plus explicit CROSSFILTER in measures.", src, "py.rel.bidi"))
        if r.get("fromCardinality") == "many" and r.get("toCardinality") == "many":
            fs.append(finding("Medium", "Model Semantics", "Many-to-many relationship",
                              "Many-to-many relationships are easy to misread. Document the grain or introduce a bridge table.", src, "py.rel.m2m"))
    auto_dates = [t for t in model.tables if t.startswith(("LocalDateTable_", "DateTableTemplate_"))]
    if auto_dates:
        fs.append(finding("Medium", "Model Size", "Auto date/time is enabled",
                          f"{len(auto_dates)} hidden auto date tables found. Disable Auto date/time and use one governed date table.", ", ".join(auto_dates[:5]), "py.model.auto-date"))
    total = sum(c["bytes"] for c in model.column_stats)
    if total:
        top = max(model.column_stats, key=lambda c: c["bytes"])
        if top["bytes"] > 0.4 * total and total > 5_000_000:
            fs.append(finding("Low", "Model Size", "One column dominates model memory",
                              f"{top['table']}[{top['column']}] uses {top['bytes'] * 100 // total}% of column storage (cardinality {top['cardinality']}). "
                              "Consider removing, splitting, or reducing precision.", f"{top['table']}[{top['column']}]", "py.model.column-hotspot"))
    user_tables = [t for t in model.tables if not t.startswith(("LocalDateTable_", "DateTableTemplate_"))]
    if len(user_tables) > 1 and not model.relationships:
        fs.append(finding("Low", "Model Design", "Tables without relationships",
                          f"{len(user_tables)} tables and no relationships. Fine for independent demo or per-visual tables; "
                          "for analysis across tables, model a star schema with shared dimensions.", ", ".join(user_tables[:6]), "py.model.no-relationships"))
    calc_cols = [c for c in model.columns if c["calculated"] and not c["table"].startswith(("LocalDateTable_", "DateTableTemplate_"))]
    if calc_cols:
        fs.append(finding("Low", "Model Design", "Calculated columns present",
                          f"{len(calc_cols)} calculated column(s). Prefer Power Query columns or measures where the logic allows (trust rule preferMeasuresOverCalculatedColumns).",
                          ", ".join(f"{c['table']}[{c['name']}]" for c in calc_cols[:5]), "py.model.calc-columns"))
    time_intel = re.compile(r"(?i)\b(SAMEPERIODLASTYEAR|DATEADD|DATESYTD|DATESQTD|DATESMTD|TOTALYTD|TOTALQTD|TOTALMTD|PARALLELPERIOD|"
                            r"PREVIOUS(YEAR|QUARTER|MONTH|DAY)|NEXT(YEAR|QUARTER|MONTH|DAY)|DATESBETWEEN|DATESINPERIOD|OPENINGBALANCE\w*|CLOSINGBALANCE\w*)\s*\(")
    uses_time_intel = any(time_intel.search(strip_comments(m["expression"])) for m in model.measures)
    if uses_time_intel and model.partitions and not any((t.get("dataCategory") or "").lower() == "time" for t in model.tables.values()):
        fs.append(finding("Low", "Time Intelligence", "No table marked as date table",
                          "Mark the governed date table (dataCategory Time) so time-intelligence functions behave predictably.", ".", "py.model.date-table"))
    fs += report_findings(model, model.report.get("file", ".") if model.report else ".")
    has_text_model = bool(model.formats & {"tmdl", "bim", "dax", "pq", "pbix-model"})
    if not has_text_model and model.report and model.report.get("pageCount"):
        fs.append(finding("Medium", "Inspectability", "Semantic model not inspected",
                          "Only the report layer was reviewed. Install the optional pbixray package or export the file as PBIP "
                          "(File > Save as > Power BI project) to review measures, relationships, and Power Query.", ".", "py.inspect.model-missing"))
    elif not has_text_model:
        fs.append(finding("High", "Inspectability", "No text-based model artifacts",
                          "The plugin can inventory binary files, but deep semantic review needs PBIP, TMDL, model.bim, DAX, or Power Query exports"
                          + (" (or the optional pbixray package for PBIX files)." if "pbix" in model.formats else "."), "."))
    if has_text_model and "pbix" not in model.formats and not any(f.suffix.lower() == ".pbip" for f in model.files):
        fs.append(finding("Low", "Project Format", "Text artifacts without PBIP file",
                          "A PBIP entry point improves Power BI Desktop round-tripping and source-control structure.", "."))
    fs.sort(key=lambda x: (-x["Score"], x["Category"], x["Title"]))
    risk = sum(x["Score"] for x in fs)
    level = "High" if risk >= th.get("highRiskScore", 9) else ("Medium" if risk >= th.get("mediumRiskScore", 4) else "Low")
    return {"Root": str(root), "Generated": now(), "Evidence": EVIDENCE, "RiskLevel": level, "RiskScore": risk,
            "FileCount": len(model.files), "MeasureCount": len(model.measures), "QueryCount": len(pq_texts),
            "TmdlObjectCount": len(model.tmdl_objects), "Formats": sorted(model.formats), "Notes": model.notes, "Findings": fs,
            "RecommendedNextActions": [
                "Export PBIX/PBIT assets to PBIP before structural edits.",
                "Generate a model summary and attach it to the report documentation.",
                "Review high and medium findings before optimizing visuals or adding features.",
                "Use Tabular Editor Best Practice Analyzer when available."]}


def metric_tags(name: str, expr: str) -> list[str]:
    probe = f"{name} {expr}"
    tags = []
    for tag, pat in (("finance", r"sales|revenue|amount|margin|profit|umsatz|ertrag|kosten"),
                     ("time-intelligence", r"yoy|prior year|previous year|sameperiodlastyear|vorjahr|\bpy\b|ytd|datesytd"),
                     ("customer", r"customer|account|active|kunde"), ("ratio", r"divide\s*\(|%"),
                     ("counting", r"count|distinctcount|anzahl")):
        if re.search("(?i)" + pat, probe):
            tags.append(tag)
    return tags or ["uncategorized"]


def metric_risks(expr: str) -> list[str]:
    e = strip_comments(expr)
    risks = []
    for label, pat in (("performance: FILTER over ALL", r"\bFILTER\s*\(\s*ALL\s*\("),
                       ("determinism: volatile date/time", r"\bTODAY\s*\(|\bNOW\s*\("),
                       ("maintainability: EARLIER", r"\bEARLIER\s*\("),
                       ("semantics: inactive relationship", r"\bUSERELATIONSHIP\s*\(")):
        if re.search("(?i)" + pat, e):
            risks.append(label)
    if len(expr.splitlines()) > 20:
        risks.append("maintainability: long expression")
    if re.search(r"(?<![/*])/(?![/*])", e) and "DIVIDE" not in e.upper():
        risks.append("robustness: division without DIVIDE")
    return risks


def catalog(root: Path, model: Model) -> dict:
    metrics = []
    for m in model.measures:
        risks = metric_risks(m["expression"])
        mid = f"{m['table']}.{m['name']}".strip(".").lower().replace(" ", "-").replace("%", "pct")
        metrics.append({"id": mid, "name": m["name"], "table": m["table"], "source": m["source"],
                        "tags": metric_tags(m["name"], m["expression"]),
                        "riskLevel": "review" if risks else "normal", "risks": risks,
                        "owner": m.get("owner") or "[TODO: metric owner]",
                        "businessDefinition": m.get("description") or "[TODO: business definition]",
                        "formatString": m.get("formatString"), "displayFolder": m.get("displayFolder"),
                        "validationQuestion": f"Does `{m['name']}` reconcile to the accepted business source for the selected filter context?",
                        "expression": m["expression"]})
    return {"schema": "codex.powerbi.metricCatalog.v1", "root": str(root), "generated": now(), "evidence": EVIDENCE,
            "metricCount": len(metrics), "metrics": metrics}


def best_practices(root: Path, model: Model, cat: dict, sc: dict, st: dict) -> dict:
    rules = load_rules("powerbi-trust-rules.json", {"bestPractices": {}}).get("bestPractices", {})
    fs = []
    for m in cat["metrics"]:
        e = strip_comments(m["expression"])
        if rules.get("requireMetricOwner", True) and "TODO" in m["owner"]:
            fs.append({"severity": "Medium", "category": "Metric Governance", "source": m["name"], "message": "Metric owner is missing.",
                       "recommendation": "Assign a business or BI owner before release (TMDL: annotation Owner = <name>)."})
        if rules.get("requireBusinessDefinition", True) and "TODO" in m["businessDefinition"]:
            fs.append({"severity": "Medium", "category": "Metric Governance", "source": m["name"], "message": "Business definition is missing.",
                       "recommendation": "Document business meaning, grain, and accepted filters (TMDL: /// description)."})
        if rules.get("discourageVolatileTimeFunctions", True) and re.search(r"(?i)\bTODAY\s*\(|\bNOW\s*\(", e):
            fs.append({"severity": "Medium", "category": "DAX Determinism", "source": m["name"], "message": "Volatile date/time function detected.",
                       "recommendation": "Use a governed date table or refresh parameter."})
        if rules.get("discourageFilterAllOnFactTables", True) and re.search(r"(?i)FILTER\s*\(\s*ALL\s*\(", e):
            fs.append({"severity": "High", "category": "DAX Performance", "source": m["name"], "message": "FILTER over ALL pattern detected.",
                       "recommendation": "Use narrower REMOVEFILTERS/KEEPFILTERS semantics where possible."})
    if rules.get("requirePbipForSourceControl", True) and st["score"] < 70:
        fs.append({"severity": "High", "category": "Source Control", "source": "model", "message": "PBIP/TMDL readiness is below strong threshold.",
                   "recommendation": "Export to PBIP/TMDL for reliable review and source control."})
    penalty = sum(15 if f["severity"] == "High" else 8 if f["severity"] == "Medium" else 3 for f in fs)
    return {"schema": "codex.powerbi.modelBestPractices.v1", "root": str(root), "generated": now(), "evidence": EVIDENCE,
            "score": max(0, 100 - penalty), "riskScore": sc["RiskScore"], "findingCount": len(fs), "findings": fs}


def summary(root: Path, model: Model) -> dict:
    tables = []
    for name, t in sorted(model.tables.items()):
        tables.append({"name": name, "hidden": t["hidden"], "dataCategory": t["dataCategory"],
                       "columns": sum(c["table"] == name for c in model.columns),
                       "calculatedColumns": sum(c["table"] == name and c["calculated"] for c in model.columns),
                       "measures": sum(m["table"] == name for m in model.measures),
                       "partitions": [{"name": p["name"], "type": p["type"], "mode": p["mode"]} for p in model.partitions if p["table"] == name]})
    return {"schema": "claude.powerbi.modelSummary.v1", "root": str(root), "generated": now(), "evidence": EVIDENCE,
            "formats": sorted(model.formats), "tableCount": len(tables), "columnCount": len(model.columns),
            "measureCount": len(model.measures), "relationshipCount": len(model.relationships),
            "roleCount": len(model.roles), "queryCount": len(model.queries), "tables": tables,
            "relationships": model.relationships, "roles": model.roles,
            "measures": [{k: m[k] for k in ("table", "name", "displayFolder", "formatString", "source")} for m in model.measures],
            "calculatedColumns": [{"table": c["table"], "name": c["name"], "expression": c["expression"]} for c in model.columns if c["calculated"]],
            "storage": {"modelBytes": (model.report or {}).get("modelBytes"), "columnBytes": sum(c["bytes"] for c in model.column_stats),
                        "topColumns": sorted(model.column_stats, key=lambda c: -c["bytes"])[:10]},
            "report": {k: v for k, v in (model.report or {}).items() if k != "visuals"} if model.report else None,
            "visuals": [{k: v[k] for k in ("page", "type", "fields")} for v in (model.report or {}).get("visuals", [])],
            "notes": model.notes}


def kpi_trust(cat: dict, deps: dict) -> dict:
    w = load_rules("powerbi-trust-rules.json", {}).get("weights", {})
    down = {i["measure"]: i["impactCount"] for i in deps["impact"]}
    metrics = []
    for m in cat["metrics"]:
        score, ded = 100, []
        if m["risks"]:
            score -= w.get("daxRisk", 25); ded.append("DAX risk detected")
        if "TODO" in m["owner"]:
            score -= w.get("missingOwner", 15); ded.append("Metric owner missing")
        if "TODO" in m["businessDefinition"]:
            score -= w.get("missingBusinessDefinition", 15); ded.append("Business definition missing")
        dc = down.get(m["name"], 0)
        if dc:
            score -= min(w.get("maxDownstreamDependencyPenalty", 15), dc * w.get("downstreamDependencyPerMeasure", 5))
            ded.append("Downstream dependency impact")
        score = max(0, score)
        metrics.append({"id": m["id"], "name": m["name"], "table": m["table"], "trustScore": score,
                        "trustBand": "High" if score >= 80 else ("Medium" if score >= 60 else "Low"), "deductions": ded,
                        "riskCount": len(m["risks"]), "risks": m["risks"], "downstreamCount": dc,
                        "owner": m["owner"], "businessDefinition": m["businessDefinition"],
                        "releaseUse": "Approved candidate after business sign-off." if score >= 80 else
                        ("Use with warning and validation note." if score >= 60 else "Do not use for executive release without remediation.")})
    overall = int(sum(x["trustScore"] for x in metrics) / len(metrics)) if metrics else None
    return {"schema": "codex.powerbi.kpiTrustScore.v1", "generated": now(), "evidence": EVIDENCE, "metricCount": len(metrics),
            "overallTrustScore": overall, "metrics": sorted(metrics, key=lambda x: (x["trustScore"], x["name"]))}


def release_gate(st: dict, sc: dict, bp: dict, tr: dict) -> dict:
    g = load_rules("powerbi-trust-rules.json", {}).get("releaseGate", {})
    go, warn = g.get("goThreshold", 80), g.get("warnThreshold", 60)
    high = sum(f["Severity"] == "High" for f in sc["Findings"])
    med = sum(f["Severity"] == "Medium" for f in sc["Findings"])
    low_trust = sum(m["trustScore"] < 60 for m in tr["metrics"])

    def chk(cid, name, status, value, detail, impact):
        return {"id": cid, "name": name, "status": status, "value": value, "detail": detail, "gateImpact": impact}

    ot = tr["overallTrustScore"]
    checks = [
        chk("kpi.trustScore", "KPI trust score", "Warn" if ot is None else ("Pass" if ot >= go else ("Warn" if ot >= warn else "Fail")),
            "n/a (no measures)" if ot is None else ot, "Overall KPI trust score." if ot is not None else "No DAX measures found; KPIs are implicit column aggregations.",
            "No-Go when below warn threshold"),
        chk("kpi.lowTrustCount", "Low-trust KPI count", "Pass" if low_trust == 0 else ("Fail" if g.get("blockOnLowTrustKpis", True) else "Warn"), low_trust, "KPIs below trust score 60.", "No-Go"),
        chk("findings.high", "High-severity findings (P0)", "Pass" if high == 0 else ("Fail" if g.get("blockOnP0", True) else "Warn"), high, "High findings from the insight scan block release.", "No-Go"),
        chk("findings.medium", "Medium-severity findings (P1)", "Pass" if med == 0 else "Warn", med, "Medium findings need a caveat or waiver.", "Warn"),
        chk("governance.score", "Best-practice score", "Pass" if bp["score"] >= 70 else "Warn", bp["score"], "Model best-practice governance score.", "Warn"),
        chk("pbip.readiness", "PBIP readiness", "Pass" if st["readiness"] == "Strong" else "Warn", st["readiness"], "Source-control and round-trip readiness.", "Warn"),
        chk("semantic.pendingTests", "Semantic tests", "Warn" if g.get("warnOnPendingSemanticTests", True) else "Pass", "NotRun",
            "Semantic tests need Invoke-PowerBISemanticTestRunner.ps1 or live DAX; not run offline.", "Warn"),
        chk("live.availability", "Live validation", "Warn" if g.get("warnOnLiveUnavailable", True) else "Pass", "NotChecked",
            "Live Desktop validation runs on Windows (see running-scripts.md).", "Warn"),
    ]
    fails = [c for c in checks if c["status"] == "Fail"]
    warns = [c for c in checks if c["status"] == "Warn"]
    decision = "No-Go" if fails else ("Warn" if warns else "Go")
    return {"schema": "claude.powerbi.offlineReleaseGate.v1", "generated": now(), "evidence": EVIDENCE, "decision": decision,
            "failCount": len(fails), "warnCount": len(warns), "checks": checks,
            "blockingReasons": [f"{c['id']}: {c['value']}" for c in fails], "warnings": [f"{c['id']}: {c['value']}" for c in warns],
            "releaseNote": {"Go": "Publish candidate after normal business sign-off.", "Warn": "Publish only with documented caveats.",
                            "No-Go": "Block publish until failing checks are remediated."}[decision],
            "scope": "Offline approximation of New-PowerBITrustReleaseGate.ps1. The PowerShell gate additionally runs the guided fix plan, Copilot readiness, and the semantic test runner."}


def md_trust(t):
    out = ["# Power BI KPI Trust Score", "", f"Overall trust score: **{t['overallTrustScore'] if t['overallTrustScore'] is not None else 'n/a (no measures)'}** · Evidence: {t['evidence']}", "",
           "| KPI | Score | Band | Deductions | Release use |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {m['table']}[{m['name']}] | {m['trustScore']} | {m['trustBand']} | {'; '.join(m['deductions']) or 'none'} | {m['releaseUse']} |" for m in t["metrics"]]
    return "\n".join(out) + "\n"


def md_gate(g):
    icon = {"Pass": "✅", "Warn": "⚠️", "Fail": "⛔"}
    out = ["# Power BI Release Gate (offline)", "", f"Decision: **{g['decision']}**", "", f"Release note: {g['releaseNote']}", "",
           "| Check | Status | Value | Detail |", "| --- | --- | --- | --- |"]
    out += [f"| {c['name']} | {icon.get(c['status'], '')} {c['status']} | {c['value']} | {c['detail']} |" for c in g["checks"]]
    out += ["", f"_{g['scope']}_"]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- markdown

def md_inventory(items):
    out = ["# Power BI Inventory", "", f"Evidence: {EVIDENCE}", "", "| Type | Path | KB | Editable text |", "| --- | --- | --- | --- |"]
    out += [f"| {i['Type']} | `{i['RelativePath']}` | {i['SizeKB']} | {i['EditableText']} |" for i in items] or ["| - | no Power BI files found | | |"]
    return "\n".join(out) + "\n"


def md_structure(s):
    out = ["# PBIP Structure", "", f"Readiness: **{s['readiness']}** (score {s['score']}), round-trip: **{s['roundtripStatus']}**", "",
           "| Check | Status | Detail |", "| --- | --- | --- |"]
    out += [f"| {c['name']} | {c['status']} | {c['detail']} |" for c in s["checks"]]
    out += ["", "## Recommendations", ""] + [f"- {r}" for r in s["recommendations"]]
    return "\n".join(out) + "\n"


def md_summary(s):
    out = ["# Power BI Model Summary", "", f"Root: `{s['root']}`  ", f"Generated: {s['generated']}  ", f"Evidence: {s['evidence']}", "",
           f"Tables {s['tableCount']} · Columns {s['columnCount']} · Measures {s['measureCount']} · Relationships {s['relationshipCount']} · Roles {s['roleCount']}",
           "", "## Tables", "", "| Table | Columns | Calc. columns | Measures | Storage | Hidden |", "| --- | --- | --- | --- | --- | --- |"]
    for t in s["tables"]:
        modes = ", ".join(sorted({p["mode"] or p["type"] or "?" for p in t["partitions"]})) or "-"
        out.append(f"| {t['name']} | {t['columns']} | {t['calculatedColumns']} | {t['measures']} | {modes} | {t['hidden']} |")
    out += ["", "## Relationships", ""]
    out += [f"- `{r['from']}` → `{r['to']}` ({r['crossFilteringBehavior']}{'' if r['isActive'] else ', inactive'})" for r in s["relationships"]] or ["None found."]
    out += ["", "## Measures", ""]
    out += [f"- `{m['table']}[{m['name']}]`" + (f" · folder {m['displayFolder']}" if m.get("displayFolder") else "") +
            (f" · format `{m['formatString']}`" if m.get("formatString") else "") for m in s["measures"]] or ["None found."]
    if s.get("storage", {}).get("topColumns"):
        st = s["storage"]
        out += ["", "## Storage (VertiPaq statistics)", "", f"File model size: {st['modelBytes'] or '-'} bytes · column storage {st['columnBytes']} bytes", "",
                "| Column | Cardinality | Bytes |", "| --- | --- | --- |"]
        out += [f"| {c['table']}[{c['column']}] | {c['cardinality']} | {c['bytes']} |" for c in st["topColumns"]]
    if s.get("calculatedColumns"):
        out += ["", "## Calculated columns", ""] + [f"- `{c['table']}[{c['name']}]` = `{(c['expression'] or '').strip()[:120]}`" for c in s["calculatedColumns"]]
    rep = s.get("report")
    if rep:
        out += ["", "## Report", "", f"Format {rep.get('format')} · pages {rep.get('pageCount')} · visuals {rep.get('visualCount')}"
                + (f" · theme {rep['theme']}" if rep.get("theme") else ""), "", "| Page | Visuals | Hidden |", "| --- | --- | --- |"]
        out += [f"| {p['name']} | {p['visuals']} | {p.get('hidden', False)} |" for p in rep.get("pages", [])]
        if rep.get("customVisuals"):
            out += ["", "Custom visuals in file: " + ", ".join(f"{c.get('name') or c['guid']} {c.get('version') or ''}".strip() for c in rep["customVisuals"])]
        types = {}
        for v in s.get("visuals", []):
            types[v["type"]] = types.get(v["type"], 0) + 1
        if types:
            out += ["", "Visual types: " + ", ".join(f"{k} ({n})" for k, n in sorted(types.items(), key=lambda x: -x[1]))]
    for n in s.get("notes", []):
        out += ["", f"> Note: {n}"]
    if s["roles"]:
        out += ["", "## Security roles", ""]
        for r in s["roles"]:
            out.append(f"- **{r['name']}**: " + ("; ".join(f"{p['table']}: `{p['filter']}`" for p in r["tablePermissions"]) or "no table filters"))
    return "\n".join(out) + "\n"


def md_scan(s):
    out = ["# Power BI Insight Scan", "", f"Root: `{s['Root']}`  ", f"Generated: {s['Generated']}  ", f"Evidence: {s['Evidence']}", "",
           "## Executive Signal", "", f"- Risk level: **{s['RiskLevel']}**", f"- Risk score: **{s['RiskScore']}**",
           f"- Power BI files: {s['FileCount']}", f"- Measures detected: {s['MeasureCount']}",
           f"- Power Query sources detected: {s['QueryCount']}", f"- TMDL objects detected: {s['TmdlObjectCount']}"]
    out += [f"- Note: {n}" for n in s.get("Notes", [])]
    out += ["", "## Findings", ""]
    if not s["Findings"]:
        out.append("No findings detected by local heuristics.")
    for f in s["Findings"]:
        out += [f"### [{f['Severity']}] {f['Title']}", "", f"- Category: {f['Category']}", f"- Source: `{f['Source']}`", f"- Detail: {f['Detail']}", ""]
    out += ["## Recommended Next Actions", ""] + [f"- {a}" for a in s["RecommendedNextActions"]]
    return "\n".join(out) + "\n"


def md_catalog(c):
    out = ["# Power BI Metric Catalog", "", f"Schema: `{c['schema']}`  ", f"Metrics: {c['metricCount']}  ", f"Evidence: {c['evidence']}", ""]
    for m in c["metrics"]:
        out += [f"## {m['table']}[{m['name']}]" if m["table"] else f"## {m['name']}", "", f"- ID: `{m['id']}`", f"- Source: `{m['source']}`",
                f"- Tags: {', '.join(m['tags'])}", f"- Risk level: {m['riskLevel']}"]
        if m["risks"]:
            out.append(f"- Risks: {'; '.join(m['risks'])}")
        out += [f"- Owner: {m['owner']}", f"- Business definition: {m['businessDefinition']}",
                f"- Validation question: {m['validationQuestion']}", "", "```DAX", m["expression"], "```", ""]
    return "\n".join(out) + "\n"


def md_best(b):
    out = ["# Power BI Model Best Practices", "", f"Score: **{b['score']}**", "", f"Findings: {b['findingCount']}", ""]
    out += [f"- [{f['severity']}] {f['category']} `{f['source']}`: {f['message']} {f['recommendation']}" for f in b["findings"]]
    return "\n".join(out) + "\n"


def md_deps(d):
    out = ["# Measure Dependency Graph", "", f"Measures {d['nodeCount']} · references {d['edgeCount']}", "", "## Change impact (most depended-on first)", "",
           "| Measure | Dependent measures |", "| --- | --- |"]
    out += [f"| {i['measure']} | {', '.join(i['dependentMeasures']) or '-'} |" for i in d["impact"]]
    out += ["", "## Graph", "", "```mermaid", "graph LR"]
    ids = {n["id"]: f"m{k}" for k, n in enumerate(d["nodes"])}
    out += [f'  {ids[n["id"]]}["{n["id"]}"]' for n in d["nodes"]]
    out += [f"  {ids[e['to']]} --> {ids[e['from']]}" for e in d["edges"] if e["to"] in ids]
    out += ["```"]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- cli

def review_one(root: Path, model: Model, out: Path) -> dict:
    dump = lambda o: json.dumps(o, indent=2, ensure_ascii=False, default=str) + "\n"
    out.mkdir(parents=True, exist_ok=True)
    inv, st, su, sc, ca, de = inventory(root, model), structure(root), summary(root, model), scan(root, model), catalog(root, model), dependencies(model)
    bp = best_practices(root, model, ca, sc, st)
    tr = kpi_trust(ca, de)
    gt = release_gate(st, sc, bp, tr)
    parts = [("inventory", inv, md_inventory), ("pbip-structure", st, md_structure), ("model-summary", su, md_summary),
             ("insight-scan", sc, md_scan), ("metric-catalog", ca, md_catalog), ("best-practices", bp, md_best),
             ("dependency-graph", de, md_deps), ("kpi-trust", tr, md_trust), ("release-gate", gt, md_gate)]
    for name, data, md in parts:
        (out / f"powerbi-{name}.json").write_text(dump(data), encoding="utf-8")
        (out / f"powerbi-{name}.md").write_text(md(data), encoding="utf-8")
    top = [f for f in sc["Findings"] if f["Severity"] in ("High", "Medium")][:8]
    index = ["# Power BI Offline Review", "", f"Model: `{root}`  ", f"Generated: {now()}  ", f"Evidence: {EVIDENCE}", "",
             "| Signal | Value |", "| --- | --- |", f"| Offline release gate | **{gt['decision']}** |",
             f"| KPI trust score | {tr['overallTrustScore'] if tr['overallTrustScore'] is not None else 'n/a (no measures)'} |",
             f"| PBIP readiness | {st['readiness']} ({st['score']}) |", f"| Risk level | {sc['RiskLevel']} (score {sc['RiskScore']}) |",
             f"| Best-practice score | {bp['score']} |", f"| Tables / measures / relationships | {su['tableCount']} / {su['measureCount']} / {su['relationshipCount']} |",
             f"| Metrics needing review | {sum(m['riskLevel'] == 'review' for m in ca['metrics'])} of {ca['metricCount']} |"]
    if model.report:
        index.append(f"| Report pages / visuals / custom visuals | {model.report['pageCount']} / {model.report['visualCount']} / {len(model.report['customVisuals'])} |")
    index += [""] + [f"> Note: {n}" for n in model.notes] + (["" ] if model.notes else []) + ["## Top findings", ""]
    index += [f"- **[{f['Severity']}] {f['Title']}** — `{f['Source']}`" for f in top] or ["- No high or medium findings."]
    index += ["", "## Files", ""] + [f"- [powerbi-{n}.md](powerbi-{n}.md)" for n, _, _ in parts]
    (out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return_summary = ({"outputDirectory": str(out), "riskLevel": sc["RiskLevel"], "riskScore": sc["RiskScore"],
                      "bestPracticeScore": bp["score"], "kpiTrust": tr["overallTrustScore"], "gate": gt["decision"], "pbipReadiness": st["readiness"],
                      "tables": su["tableCount"], "measures": su["measureCount"]})
    return_summary.update({"pages": (model.report or {}).get("pageCount", 0), "visuals": (model.report or {}).get("visualCount", 0),
                           "topFinding": top[0]["Title"] if top else "-", "notes": model.notes})
    return return_summary




def write(out: str | None, text: str) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Power BI offline toolkit (PBIP/TMDL/BIM/DAX/PQ)")
    ap.add_argument("command", choices=["inventory", "structure", "summary", "scan", "catalog", "best-practices", "dependencies", "trust", "gate", "review"])
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--out", help="output file (or folder for review)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    a = ap.parse_args(argv)
    root = Path(a.path).resolve()
    if not root.exists():
        ap.error(f"path not found: {root}")
    model = parse_model(root)
    dump = lambda o: json.dumps(o, indent=2, ensure_ascii=False, default=str) + "\n"

    if a.command == "review":
        if not a.out:
            ap.error("review needs --out <folder>")
        out = Path(a.out)
        pbix_files = []
        if root.is_dir() and not (model.formats & {"tmdl", "bim", "dax", "pq"}):
            pbix_files = [f for f in model.files if f.suffix.lower() in (".pbix", ".pbit")]
        if len(pbix_files) > 1:
            rows = []
            for f in pbix_files:
                sub = out / re.sub(r"[^A-Za-z0-9._-]+", "_", f.stem).strip("_")
                rows.append((f.name, sub.name, review_one(f, parse_model(f), sub)))
            idx = ["# Power BI Portfolio Review", "", f"Folder: `{root}`  ", f"Generated: {now()}  ", f"Evidence: {EVIDENCE}", "",
                   "| File | Gate | Risk | Best practice | KPI trust | Tables | Measures | Pages | Visuals | Top finding |",
                   "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
            for name, sub, r in rows:
                idx.append(f"| [{name}]({sub}/index.md) | **{r['gate']}** | {r['riskLevel']} ({r['riskScore']}) | {r['bestPracticeScore']} | "
                           f"{r['kpiTrust'] if r['kpiTrust'] is not None else 'n/a'} | {r['tables']} | {r['measures']} | {r['pages']} | {r['visuals']} | {r['topFinding']} |")
            notes = sorted({n for _, _, r in rows for n in r["notes"]})
            idx += [""] + [f"> Note: {n}" for n in notes]
            out.mkdir(parents=True, exist_ok=True)
            (out / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
            (out / "portfolio.json").write_text(dump([dict(r, file=n) for n, _, r in rows]), encoding="utf-8")
            print(json.dumps({"outputDirectory": str(out), "files": len(rows),
                              "gates": {g: sum(r["gate"] == g for _, _, r in rows) for g in ("Go", "Warn", "No-Go")}}, indent=2))
            return 0
        print(json.dumps(review_one(root, model, out), indent=2, ensure_ascii=False))
        return 0

    if a.command == "inventory":
        data, md = inventory(root, model), md_inventory
    elif a.command == "structure":
        data, md = structure(root), md_structure
    elif a.command == "summary":
        data, md = summary(root, model), md_summary
    elif a.command == "scan":
        data, md = scan(root, model), md_scan
    elif a.command == "catalog":
        data, md = catalog(root, model), md_catalog
    elif a.command == "dependencies":
        data, md = dependencies(model), md_deps
    elif a.command == "trust":
        data, md = kpi_trust(catalog(root, model), dependencies(model)), md_trust
    elif a.command == "gate":
        sc, ca, st = scan(root, model), catalog(root, model), structure(root)
        data, md = release_gate(st, sc, best_practices(root, model, ca, sc, st), kpi_trust(ca, dependencies(model))), md_gate
    else:
        sc, ca, st = scan(root, model), catalog(root, model), structure(root)
        data, md = best_practices(root, model, ca, sc, st), md_best
    write(a.out, dump(data) if a.json else md(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
