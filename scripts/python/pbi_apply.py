#!/usr/bin/env python3
"""PBIP apply engine: writes reviewed changes into a real Power BI project (TMDL), with backup and undo.

Every command is a dry run unless --apply is given. A dry run prints the target file, the action
(insert/replace/skip) and the exact TMDL block. --apply first zips the whole
<Name>.SemanticModel/definition folder to <project>/.pbip-apply/backups/<id>.zip (a zip, so reviews never read
backup copies as model files) and records the change
in <project>/.pbip-apply/manifest.json. `undo` restores the latest (or a given) backup without deleting
anything: files created by later changes are moved to <project>/.pbip-apply/undone/<id>/.

Never touches PBIX/PBIT files. Close the project in Power BI Desktop before applying, then reopen it:
Desktop validates the TMDL on open.

Usage (PBIP = project folder or .pbip file):
  pbi_apply.py measure      PBIP --table T --name N --expression DAX [--format F] [--description D] [--folder X] [--apply]
  pbi_apply.py column       PBIP --table T --name N --expression DAX [--data-type string|int64|double|decimal|boolean|dateTime] [--description D] [--apply]
  pbi_apply.py table        PBIP --name N --expression DAX --column Name:type [--column ...] [--apply]      (calculated table)
  pbi_apply.py relationship PBIP --from T.C --to T.C [--both-directions] [--inactive] [--one-to-one] [--apply]
  pbi_apply.py role         PBIP --name R --table T --filter DAX [--apply]
  pbi_apply.py query        PBIP --name N --m-file FILE [--apply]                                             (shared Power Query expression)
  pbi_apply.py tmdl         PBIP --tmdl-file FILE [--apply]          (draft from New-PowerBI*Draft.ps1: table child, table, relationship, role)
  pbi_apply.py spec         PBIP --spec-file JSON [--apply]          ({"command": "measure", "table": ..., ...}; used by the PowerShell wrappers)
  pbi_apply.py undo         PBIP [--backup ID] [--apply]
  pbi_apply.py history      PBIP
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

SCHEMA = "codex.powerbi.pbipTmdlApply.v2"


# --------------------------------------------------------------------------- tmdl helpers

def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def unq(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1].replace("''", "'")
    return name


def col_ref(ref: str) -> tuple[str, str]:
    """'Table.Column', "'My Table'.'My Col'" or 'Table[Column]' -> (table, column)."""
    m = re.fullmatch(r"\s*('(?:[^']|'')+'|[^.\[]+)\s*(?:\.|\[)\s*('(?:[^']|'')+'|[^\]]+?)\]?\s*", ref)
    if not m:
        raise SystemExit(f"Cannot parse column reference: {ref!r} (use Table.Column or Table[Column])")
    return unq(m.group(1)), unq(m.group(2))


def expr_lines(expression: str, indent: str) -> list[str]:
    lines = expression.strip("\n").splitlines() or [""]
    cut = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return [(indent + l[cut:].rstrip()) if l.strip() else "" for l in lines]


def object_with_expression(keyword: str, name: str, expression: str, base: str) -> list[str]:
    expression = expression.strip()
    if "\n" not in expression:
        return [f"{base}{keyword} {q(name)} = {expression}"]
    return [f"{base}{keyword} {q(name)} ="] + expr_lines(expression, base + "\t\t")


def description_lines(description: str | None, base: str) -> list[str]:
    if not description:
        return []
    return [f"{base}/// {l}".rstrip() for l in description.strip().splitlines()]


def indent_len(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


# --------------------------------------------------------------------------- project

class Project:
    def __init__(self, path: Path):
        path = path.resolve()
        self.root = path.parent if path.is_file() else path
        models = sorted(p for p in self.root.glob("*.SemanticModel") if (p / "definition").is_dir())
        if not models:
            if (self.root / "definition").is_dir() and self.root.name.endswith(".SemanticModel"):
                models = [self.root]
                self.root = self.root.parent
            else:
                raise SystemExit(f"No <Name>.SemanticModel/definition folder under {self.root}. "
                                 "Save the report as a Power BI project (File > Save as > *.pbip) with TMDL format.")
        if len(models) > 1:
            raise SystemExit("Several semantic models found; pass the .SemanticModel folder directly: "
                             + ", ".join(m.name for m in models))
        self.model_dir = models[0]
        self.definition = self.model_dir / "definition"
        self.state = self.root / ".pbip-apply"

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root)).replace(os.sep, "/")

    # tables -----------------------------------------------------------
    def table_file(self, table: str) -> Path:
        for f in sorted((self.definition / "tables").glob("*.tmdl")):
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                if line.strip():
                    m = re.match(r"^table\s+(.+?)\s*$", line)
                    if m and unq(m.group(1)) == table:
                        return f
                    break
        known = [unq(l.split(None, 1)[1]) for f in (self.definition / "tables").glob("*.tmdl")
                 for l in f.read_text(encoding="utf-8-sig").splitlines()[:1] if l.startswith("table ")]
        raise SystemExit(f"Table {table!r} not found. Tables: {', '.join(sorted(known))}")

    def model_tmdl(self) -> Path:
        return self.definition / "model.tmdl"


def read(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8-sig").splitlines() if p.exists() else []


def write(p: Path, lines: list[str]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines).rstrip("\n") + "\n"
    p.write_text(text, encoding="utf-8", newline="\r\n" if os.name == "nt" else "\n")


def child_block(lines: list[str], header_idx: int) -> tuple[int, int]:
    """Return (start, end_exclusive) of a table child (measure/column/...) incl. its /// description."""
    start = header_idx
    while start > 0 and lines[start - 1].lstrip("\t").startswith("///") and indent_len(lines[start - 1]) == 1:
        start -= 1
    end = header_idx + 1
    last = header_idx
    while end < len(lines):
        l = lines[end]
        if l.strip():
            if indent_len(l) < 2:
                break
            last = end
        end += 1
    return start, last + 1


def upsert_table_child(p: Project, table: str, kind: str, name: str, block: list[str]) -> tuple[Path, str, list[str]]:
    f = p.table_file(table)
    lines = read(f)
    header_re = re.compile(rf"^\t{kind}\s+(.+?)\s*(=.*)?$")
    for i, l in enumerate(lines):
        m = header_re.match(l)
        if m and unq(m.group(1)) == name:
            s, e = child_block(lines, i)
            return f, "replace", lines[:s] + block + lines[e:]
    def first_of(pattern):
        for i, l in enumerate(lines):
            if re.match(pattern, l):
                while i > 0 and lines[i - 1].startswith("\t///"):
                    i -= 1
                return i
        return None

    same = [i for i, l in enumerate(lines) if re.match(rf"^\t{kind}\s", l)]
    if same:
        pos = child_block(lines, same[-1])[1]
    elif kind == "measure":
        pos = first_of(r"^\t(column|hierarchy|partition|calculationGroup|annotation)\s")
    else:
        measures = [i for i, l in enumerate(lines) if re.match(r"^\tmeasure\s", l)]
        pos = child_block(lines, measures[-1])[1] if measures else first_of(r"^\t(hierarchy|partition|annotation)\s")
    if pos is None:
        pos = len(lines)
    head, tail = lines[:pos], lines[pos:]
    while head and not head[-1].strip():
        head.pop()
    while tail and not tail[0].strip():
        tail.pop(0)
    new = head + [""] + block + ([""] + tail if tail else [])
    return f, "insert", new


# --------------------------------------------------------------------------- state

def backup(p: Project) -> str:
    bid = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = p.state / "backups" / f"{bid}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p.definition.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(p.definition).as_posix())
    return bid


def manifest(p: Project) -> dict:
    f = p.state / "manifest.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"schema": "codex.powerbi.pbipApplyManifest.v2", "project": str(p.root), "changes": []}


def record(p: Project, entry: dict) -> None:
    m = manifest(p)
    m["changes"].append(entry)
    (p.state).mkdir(parents=True, exist_ok=True)
    (p.state / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def commit(p: Project, args, object_type: str, object_name: str, target: Path, action: str, new_lines: list[str] | None,
           block: list[str], extra_writes: list[tuple[Path, list[str]]] = ()) -> dict:
    result = {"schema": SCHEMA, "pbipPath": str(p.root), "semanticModel": p.model_dir.name, "objectType": object_type,
              "objectName": object_name, "targetPath": p.rel(target), "action": action, "applied": False,
              "tmdl": "\n".join(block), "backupId": None,
              "validation": "Close the project in Power BI Desktop, reopen the .pbip (Desktop validates TMDL on open), "
                            "then check the object and run the semantic tests."}
    if action == "skip" or not args.apply:
        result["note"] = "Dry run: nothing written. Re-run with --apply after review." if action != "skip" else "Already present; nothing to do."
        return result
    bid = backup(p)
    write(target, new_lines)
    for path, lines in extra_writes:
        write(path, lines)
    result.update(applied=True, backupId=bid, rollback=f"pbi_apply.py undo \"{p.root}\" --backup {bid} --apply")
    record(p, {"id": bid, "at": _dt.datetime.now().replace(microsecond=0).isoformat(), "objectType": object_type,
               "objectName": object_name, "file": p.rel(target), "action": action,
               "extraFiles": [p.rel(x) for x, _ in extra_writes]})
    return result


# --------------------------------------------------------------------------- commands

def cmd_measure(p: Project, a) -> dict:
    block = description_lines(a.description, "\t") + object_with_expression("measure", a.name, a.expression, "\t")
    if a.format:
        block.append(f"\t\tformatString: {a.format}")
    if a.folder:
        block.append(f"\t\tdisplayFolder: {a.folder}")
    f, action, new = upsert_table_child(p, a.table, "measure", a.name, block)
    return commit(p, a, "Measure", f"{a.table}[{a.name}]", f, action, new, block)


def cmd_column(p: Project, a) -> dict:
    block = description_lines(a.description, "\t") + object_with_expression("column", a.name, a.expression, "\t")
    block += [f"\t\tdataType: {a.data_type}", "\t\tsummarizeBy: none"]
    f, action, new = upsert_table_child(p, a.table, "column", a.name, block)
    return commit(p, a, "CalculatedColumn", f"{a.table}[{a.name}]", f, action, new, block)


def cmd_table(p: Project, a) -> dict:
    target = p.definition / "tables" / (re.sub(r'[\\/:*?"<>|]', "_", a.name) + ".tmdl")
    exists = target.exists()
    block = [f"table {q(a.name)}", ""]
    for spec in a.column:
        cname, _, ctype = spec.partition(":")
        block += [f"\tcolumn {q(cname)}", f"\t\tdataType: {ctype or 'string'}", "\t\tsummarizeBy: none",
                  f"\t\tsourceColumn: [{cname}]", ""]
    block += [f"\tpartition {q(a.name)} = calculated", "\t\tmode: import"]
    if "\n" in a.expression.strip():
        block += ["\t\tsource ="] + expr_lines(a.expression, "\t\t\t\t")
    else:
        block += [f"\t\tsource = {a.expression.strip()}"]
    extra = []
    mt = read(p.model_tmdl())
    refs = [i for i, l in enumerate(mt) if l.startswith("ref table ")]
    if refs and not any(unq(l[len("ref table "):]) == a.name for l in mt if l.startswith("ref table ")):
        mt = mt[:refs[-1] + 1] + [f"ref table {q(a.name)}"] + mt[refs[-1] + 1:]
        extra.append((p.model_tmdl(), mt))
    return commit(p, a, "CalculatedTable", a.name, target, "replace" if exists else "insert", block, block, extra)


def cmd_relationship(p: Project, a) -> dict:
    ft, fc = col_ref(a.from_)
    tt, tc = col_ref(a.to)
    p.table_file(ft)
    p.table_file(tt)
    target = p.definition / "relationships.tmdl"
    lines = read(target)
    frm, to = f"{q(ft)}.{q(fc)}", f"{q(tt)}.{q(tc)}"
    text = "\n".join(lines)
    if re.search(rf"fromColumn:\s*{re.escape(frm)}\s*\n\s*toColumn:\s*{re.escape(to)}\b", text):
        return commit(p, a, "Relationship", f"{frm} -> {to}", target, "skip", None, [])
    block = [f"relationship {uuid.uuid4()}"]
    if a.inactive:
        block.append("\tisActive: false")
    if a.both_directions:
        block.append("\tcrossFilteringBehavior: bothDirections")
    if a.one_to_one:
        block.append("\ttoCardinality: one")
        block.append("\tfromCardinality: one")
    block += [f"\tfromColumn: {frm}", f"\ttoColumn: {to}"]
    new = (lines + [""] if lines and lines[-1].strip() else lines) + block
    return commit(p, a, "Relationship", f"{frm} -> {to}", target, "insert", new, block)


def cmd_role(p: Project, a) -> dict:
    p.table_file(a.table)
    target = p.definition / "roles" / (re.sub(r'[\\/:*?"<>|]', "_", a.name) + ".tmdl")
    block = [f"role {q(a.name)}", "\tmodelPermission: read", ""]
    filt = a.filter.strip()
    if "\n" in filt:
        block += [f"\ttablePermission {q(a.table)} ="] + expr_lines(filt, "\t\t\t")
    else:
        block += [f"\ttablePermission {q(a.table)} = {filt}"]
    return commit(p, a, "RLSRole", a.name, target, "replace" if target.exists() else "insert", block, block)


def cmd_query(p: Project, a) -> dict:
    m = Path(a.m_file).read_text(encoding="utf-8-sig")
    target = p.definition / "expressions.tmdl"
    lines = read(target)
    block = [f"expression {q(a.name)} ="] + expr_lines(m, "\t\t") + [f"\tlineageTag: {uuid.uuid4()}", "",
             "\tannotation PBI_ResultType = Table"]
    for i, l in enumerate(lines):
        mm = re.match(r"^expression\s+(.+?)\s*=", l)
        if mm and unq(mm.group(1)) == a.name:
            end = i + 1
            while end < len(lines) and (not lines[end].strip() or lines[end].startswith("\t")):
                end += 1
            new = lines[:i] + block + ([""] if end < len(lines) else []) + lines[end:]
            return commit(p, a, "PowerQuery", a.name, target, "replace", new, block)
    new = (lines + [""] if lines and lines[-1].strip() else lines) + block
    return commit(p, a, "PowerQuery", a.name, target, "insert", new, block)


def normalize_tabs(lines: list[str]) -> list[str]:
    """Drafts may use 4-space indentation; TMDL from Power BI Desktop uses tabs."""
    out = []
    for l in lines:
        m = re.match(r"^((?:\t| {4})*)(.*)$", l)
        lead, rest = m.group(1), m.group(2)
        out.append("\t" * (lead.count("\t") + lead.count("    ")) + rest)
    return out


def cmd_tmdl(p: Project, a) -> dict:
    raw = normalize_tabs(Path(a.tmdl_file).read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n"))
    while raw and not raw[-1].strip():
        raw.pop()
    first = next((i for i, l in enumerate(raw) if l.strip()), None)
    if first is None:
        raise SystemExit("Empty TMDL draft.")
    head = raw[first]
    if head.startswith("table "):
        table = unq(head[len("table "):])
        children = [l for l in raw[first + 1:]]
        kinds = [re.match(r"^\t(measure|column)\s+(.+?)\s*(=.*)?$", l) for l in children]
        heads = [m for m in kinds if m]
        has_partition = any(re.match(r"^\tpartition\s", l) for l in children)
        if heads and not has_partition and len(heads) == 1:
            kind, name = heads[0].group(1), unq(heads[0].group(2))
            block = [l for l in children if l.strip() or True]
            while block and not block[0].strip():
                block.pop(0)
            f, action, new = upsert_table_child(p, table, kind, name, block)
            return commit(p, a, "Measure" if kind == "measure" else "CalculatedColumn", f"{table}[{name}]", f, action, new, block)
        target = p.definition / "tables" / (re.sub(r'[\\/:*?"<>|]', "_", table) + ".tmdl")
        try:
            p.table_file(table)
            exists = True
        except SystemExit:
            exists = False
        if exists and not has_partition:
            raise SystemExit("Draft contains several children for an existing table; apply them one by one.")
        extra = []
        mt = read(p.model_tmdl())
        refs = [i for i, l in enumerate(mt) if l.startswith("ref table ")]
        if refs and not any(unq(l[len("ref table "):]) == table for l in mt if l.startswith("ref table ")):
            extra.append((p.model_tmdl(), mt[:refs[-1] + 1] + [f"ref table {q(table)}"] + mt[refs[-1] + 1:]))
        return commit(p, a, "CalculatedTable", table, target, "replace" if exists else "insert", raw[first:], raw[first:], extra)
    if head.startswith("relationship "):
        body = "\n".join(raw[first:])
        fm = re.search(r"fromColumn:\s*(.+)", body)
        tm = re.search(r"toColumn:\s*(.+)", body)
        if not (fm and tm):
            raise SystemExit("Relationship draft needs fromColumn and toColumn.")
        a.from_, a.to = fm.group(1).strip(), tm.group(1).strip()
        a.both_directions = "bothDirections" in body
        a.inactive = re.search(r"isActive:\s*false", body) is not None
        a.one_to_one = re.search(r"fromCardinality:\s*one", body) is not None
        return cmd_relationship(p, a)
    if head.startswith("role "):
        name = unq(head[len("role "):])
        target = p.definition / "roles" / (re.sub(r'[\\/:*?"<>|]', "_", name) + ".tmdl")
        block = raw[first:]
        if not any(l.strip().startswith("modelPermission:") for l in block):
            block = block[:1] + ["\tmodelPermission: read", ""] + block[1:]
        for l in block:
            m = re.match(r"^\ttablePermission\s+(.+?)\s*=", l)
            if m:
                p.table_file(unq(m.group(1)))
        return commit(p, a, "RLSRole", name, target, "replace" if target.exists() else "insert", block, block)
    raise SystemExit(f"Unsupported TMDL draft header: {head!r}")


def cmd_spec(p: Project, a) -> dict:
    spec = json.loads(Path(a.spec_file).read_text(encoding="utf-8-sig"))
    command = spec.pop("command")
    defaults = {"format": None, "description": None, "folder": None, "data_type": "string", "column": [],
                "both_directions": False, "inactive": False, "one_to_one": False, "backup": None}
    ns = argparse.Namespace(**{**defaults, **{k.replace("-", "_"): v for k, v in spec.items()}}, apply=a.apply, pbip=a.pbip)
    if "from" in spec:
        ns.from_ = spec["from"]
    if command == "query" and "m" in spec:
        tmp = p.state / "tmp-query.m" if a.apply else Path(os.environ.get("TMP", "/tmp")) / "pbi-apply-query.m"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(spec["m"], encoding="utf-8")
        ns.m_file = str(tmp)
    if command == "tmdl" and "tmdl" in spec:
        tmp = Path(os.environ.get("TMP", "/tmp")) / f"pbi-apply-{uuid.uuid4().hex}.tmdl"
        tmp.write_text(spec["tmdl"], encoding="utf-8")
        ns.tmdl_file = str(tmp)
    fn = {"measure": cmd_measure, "column": cmd_column, "table": cmd_table, "relationship": cmd_relationship,
          "role": cmd_role, "query": cmd_query, "tmdl": cmd_tmdl, "undo": cmd_undo}[command]
    return fn(p, ns)


def cmd_undo(p: Project, a) -> dict:
    folder = p.state / "backups"
    backups = sorted(folder.glob("*.zip")) if folder.exists() else []
    if not backups:
        raise SystemExit("No backups recorded for this project.")
    src = (folder / f"{a.backup}.zip") if a.backup else backups[-1]
    if not src.exists():
        raise SystemExit(f"Backup {a.backup} not found. Available: {', '.join(b.stem for b in backups)}")
    with zipfile.ZipFile(src) as z:
        saved = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    current = {f.relative_to(p.definition).as_posix() for f in p.definition.rglob("*") if f.is_file()}
    added = sorted(current - set(saved))
    changed = sorted(n for n, data in saved.items() if not (p.definition / n).exists() or (p.definition / n).read_bytes() != data)
    result = {"schema": SCHEMA, "pbipPath": str(p.root), "action": "undo", "backupId": src.stem, "applied": False,
              "restoreFiles": changed, "moveAsideFiles": added}
    if not a.apply:
        result["note"] = "Dry run: nothing restored. Re-run with --apply."
        return result
    aside = p.state / "undone" / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for r in added:
        (aside / r).parent.mkdir(parents=True, exist_ok=True)
        os.replace(p.definition / r, aside / r)
    for r in changed:
        (p.definition / r).parent.mkdir(parents=True, exist_ok=True)
        (p.definition / r).write_bytes(saved[r])
    saved_dirs = {str(Path(n).parent.as_posix()) for n in saved}
    for d in sorted((x for x in p.definition.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
        if not any(d.iterdir()) and d.relative_to(p.definition).as_posix() not in saved_dirs:
            try:
                d.rmdir()  # empty folder created by a later change; harmless if removal is not permitted
            except OSError:
                pass
    result["applied"] = True
    record(p, {"id": f"undo-{src.stem}", "at": _dt.datetime.now().replace(microsecond=0).isoformat(), "objectType": "Undo",
               "objectName": src.stem, "file": None, "action": "undo", "movedAside": p.rel(aside)})
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply reviewed changes to a PBIP/TMDL project (dry run by default)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        s = sub.add_parser(name, **kw)
        s.add_argument("pbip")
        s.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
        return s
    s = add("measure"); s.add_argument("--table", required=True); s.add_argument("--name", required=True)
    s.add_argument("--expression", required=True); s.add_argument("--format"); s.add_argument("--description"); s.add_argument("--folder")
    s = add("column"); s.add_argument("--table", required=True); s.add_argument("--name", required=True)
    s.add_argument("--expression", required=True); s.add_argument("--data-type", default="string"); s.add_argument("--description")
    s = add("table"); s.add_argument("--name", required=True); s.add_argument("--expression", required=True)
    s.add_argument("--column", action="append", default=[], help="Name:dataType (repeatable)")
    s = add("relationship"); s.add_argument("--from", dest="from_", required=True); s.add_argument("--to", required=True)
    s.add_argument("--both-directions", action="store_true"); s.add_argument("--inactive", action="store_true"); s.add_argument("--one-to-one", action="store_true")
    s = add("role"); s.add_argument("--name", required=True); s.add_argument("--table", required=True); s.add_argument("--filter", required=True)
    s = add("query"); s.add_argument("--name", required=True); s.add_argument("--m-file", required=True)
    s = add("tmdl"); s.add_argument("--tmdl-file", required=True)
    s = add("spec"); s.add_argument("--spec-file", required=True)
    s = add("undo"); s.add_argument("--backup")
    s = sub.add_parser("history"); s.add_argument("pbip")
    a = ap.parse_args(argv)
    p = Project(Path(a.pbip))
    if a.cmd == "history":
        print(json.dumps(manifest(p), indent=2, ensure_ascii=False))
        return 0
    fn = {"measure": cmd_measure, "column": cmd_column, "table": cmd_table, "relationship": cmd_relationship,
          "role": cmd_role, "query": cmd_query, "tmdl": cmd_tmdl, "spec": cmd_spec, "undo": cmd_undo}[a.cmd]
    print(json.dumps(fn(p, a), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
