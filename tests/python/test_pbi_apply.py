import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
APPLY = PLUGIN_ROOT / "scripts" / "python" / "pbi_apply.py"
TOOLKIT = PLUGIN_ROOT / "scripts" / "python" / "pbi_toolkit.py"
EXAMPLE = PLUGIN_ROOT / "examples" / "pbip-tmdl-model"
sys.path.insert(0, str(TOOLKIT.parent))

import pbi_toolkit as tk  # noqa: E402


def apply(*args):
    out = subprocess.run([sys.executable, "-I", str(APPLY), *map(str, args)], capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(out.stderr or out.stdout)
    return json.loads(out.stdout)


def snapshot(root: Path) -> dict:
    d = root / "Sales.SemanticModel" / "definition"
    return {f.relative_to(d).as_posix(): f.read_bytes() for f in d.rglob("*") if f.is_file()}


class ApplyEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.proj = self.tmp / "proj"
        shutil.copytree(EXAMPLE, self.proj)
        self.defn = self.proj / "Sales.SemanticModel" / "definition"
        self.original = snapshot(self.proj)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        r = apply("measure", self.proj, "--table", "Sales", "--name", "Avg Sale", "--expression", "AVERAGE(Sales[Amount])")
        self.assertFalse(r["applied"])
        self.assertEqual(r["action"], "insert")
        self.assertIn("measure 'Avg Sale' = AVERAGE(Sales[Amount])", r["tmdl"])
        self.assertEqual(snapshot(self.proj), self.original)
        self.assertFalse((self.proj / ".pbip-apply").exists())

    def test_insert_measure_with_properties_and_zip_backup(self):
        r = apply("measure", self.proj, "--table", "Sales", "--name", "Avg Sale", "--expression", "AVERAGE(Sales[Amount])",
                  "--format", "#,0.00", "--description", "Average invoice", "--folder", "Revenue", "--apply")
        self.assertTrue(r["applied"])
        text = (self.defn / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
        self.assertIn("\t/// Average invoice\n\tmeasure 'Avg Sale' = AVERAGE(Sales[Amount])", text)
        self.assertIn("\t\tformatString: #,0.00", text)
        backup = self.proj / ".pbip-apply" / "backups" / f"{r['backupId']}.zip"
        self.assertTrue(backup.exists())
        with zipfile.ZipFile(backup) as z:
            self.assertIn("tables/Sales.tmdl", z.namelist())
        model = tk.parse_model(self.proj)
        names = [m["name"] for m in model.measures]
        self.assertEqual(names.count("Avg Sale"), 1)
        self.assertEqual(names.count("Total Sales"), 1, "backups must not be scanned as model files")

    def test_replace_existing_measure(self):
        r = apply("measure", self.proj, "--table", "Sales", "--name", "Sales YoY %",
                  "--expression", "DIVIDE([Total Sales] - [Total Sales PY], [Total Sales PY])", "--format", "0.0%", "--apply")
        self.assertEqual(r["action"], "replace")
        text = (self.defn / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
        self.assertEqual(text.count("measure 'Sales YoY %'"), 1)
        self.assertIn("DIVIDE([Total Sales] - [Total Sales PY]", text)
        self.assertIn("measure 'Active Customer Sales'", text)

    def test_multiline_measure_parses_back(self):
        apply("measure", self.proj, "--table", "Sales", "--name", "Sales YTD",
              "--expression", "CALCULATE(\n    [Total Sales],\n    DATESYTD('Date'[Date])\n)", "--apply")
        m = next(x for x in tk.parse_model(self.proj).measures if x["name"] == "Sales YTD")
        self.assertIn("DATESYTD", m["expression"])

    def test_relationship_dedupe_and_insert(self):
        r = apply("relationship", self.proj, "--from", "Sales.CustomerKey", "--to", "Customer.CustomerKey", "--apply")
        self.assertEqual(r["action"], "skip")
        self.assertFalse(r["applied"])
        r = apply("relationship", self.proj, "--from", "Sales[ShipDate]", "--to", "Customer[CustomerKey]", "--inactive", "--apply")
        self.assertTrue(r["applied"])
        text = (self.defn / "relationships.tmdl").read_text(encoding="utf-8")
        self.assertIn("\tfromColumn: Sales.ShipDate\n\ttoColumn: Customer.CustomerKey", text)

    def test_unknown_table_is_rejected(self):
        out = subprocess.run([sys.executable, "-I", str(APPLY), "measure", str(self.proj), "--table", "Nope",
                              "--name", "X", "--expression", "1", "--apply"], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(snapshot(self.proj), self.original)

    def test_role_and_calculated_table(self):
        apply("role", self.proj, "--name", "EU only", "--table", "Customer", "--filter", "Customer[Region] = \"EU\"", "--apply")
        role = (self.defn / "roles" / "EU only.tmdl").read_text(encoding="utf-8")
        self.assertIn("role 'EU only'", role)
        self.assertIn("tablePermission Customer = Customer[Region] = \"EU\"", role)
        apply("table", self.proj, "--name", "Regions", "--expression", "DISTINCT(Customer[Region])", "--column", "Region:string", "--apply")
        self.assertTrue((self.defn / "tables" / "Regions.tmdl").exists())
        self.assertIn("ref table Regions", (self.defn / "model.tmdl").read_text(encoding="utf-8"))

    def test_spec_and_query(self):
        spec = self.tmp / "spec.json"
        spec.write_text(json.dumps({"command": "column", "table": "Sales", "name": "Is Big",
                                    "expression": "Sales[Amount] > 1000", "dataType": "boolean"}), encoding="utf-8")
        r = apply("spec", self.proj, "--spec-file", spec, "--apply")
        self.assertTrue(r["applied"])
        self.assertIn("column 'Is Big' = Sales[Amount] > 1000", (self.defn / "tables" / "Sales.tmdl").read_text(encoding="utf-8"))
        m = self.tmp / "q.pq"
        m.write_text('let\n    Source = #table({"A"}, {{1}})\nin\n    Source', encoding="utf-8")
        apply("query", self.proj, "--name", "Helper", "--m-file", m, "--apply")
        self.assertIn("expression Helper =", (self.defn / "expressions.tmdl").read_text(encoding="utf-8"))

    def test_undo_restores_original_exactly(self):
        first = apply("measure", self.proj, "--table", "Sales", "--name", "Avg Sale", "--expression", "1", "--apply")
        apply("role", self.proj, "--name", "EU only", "--table", "Customer", "--filter", "TRUE()", "--apply")
        dry = apply("undo", self.proj, "--backup", first["backupId"])
        self.assertFalse(dry["applied"])
        self.assertIn("roles/EU only.tmdl", dry["moveAsideFiles"])
        r = apply("undo", self.proj, "--backup", first["backupId"], "--apply")
        self.assertTrue(r["applied"])
        self.assertEqual(snapshot(self.proj), self.original)
        hist = apply("history", self.proj)
        self.assertEqual([c["action"] for c in hist["changes"]][-1], "undo")

    def test_tmdl_bare_measure_needs_table(self):
        draft = self.tmp / "m.tmdl"
        draft.write_text("/// Half of sales\nmeasure 'Half Sales' = [Total Sales] / 2\n    formatString: #,0\n", encoding="utf-8")
        out = subprocess.run([sys.executable, "-I", str(APPLY), "tmdl", str(self.proj), "--tmdl-file", str(draft)],
                             capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("--table", out.stderr + out.stdout)
        r = apply("tmdl", self.proj, "--tmdl-file", draft, "--table", "Sales", "--apply")
        self.assertTrue(r["applied"])
        text = (self.defn / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
        self.assertIn("\t/// Half of sales\n\tmeasure 'Half Sales' = [Total Sales] / 2\n\t\tformatString: #,0", text)

    def test_page_adds_pbir_page_and_undo_restores_report(self):
        report = self.proj / "Sales.Report" / "definition"
        before = {f.relative_to(report).as_posix(): f.read_bytes() for f in report.rglob("*") if f.is_file()}
        dry = apply("page", self.proj, "--name", "KPI", "--measure", "Total Sales,Sales YoY %")
        self.assertFalse(dry["applied"])
        self.assertEqual([v["measure"] for v in dry["visuals"]], ["Total Sales", "Sales YoY %"])
        r = apply("page", self.proj, "--name", "KPI", "--measure", "Total Sales", "--measure", "Sales YoY %", "--apply")
        self.assertTrue(r["applied"])
        order = json.loads((report / "pages" / "pages.json").read_text(encoding="utf-8"))["pageOrder"]
        self.assertEqual(order[-1], r["pageId"])
        page = json.loads((report / "pages" / r["pageId"] / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(page["displayName"], "KPI")
        visuals = list((report / "pages" / r["pageId"] / "visuals").glob("*/visual.json"))
        self.assertEqual(len(visuals), 2)
        v = json.loads(visuals[0].read_text(encoding="utf-8"))
        self.assertEqual(v["visual"]["visualType"], "card")
        rep = tk.parse_model(self.proj).report
        self.assertIn("KPI", [pg["name"] for pg in rep["pages"]])
        self.assertEqual(apply("page", self.proj, "--name", "KPI", "--measure", "Total Sales")["action"], "skip")
        with self.assertRaises(AssertionError):
            apply("page", self.proj, "--name", "Other", "--measure", "Nope")
        apply("undo", self.proj, "--apply")
        after = {f.relative_to(report).as_posix(): f.read_bytes() for f in report.rglob("*") if f.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(snapshot(self.proj), self.original)

    def test_calcgroup_writes_table_flag_and_ref(self):
        r = apply("calcgroup", self.proj, "--name", "Time Intelligence", "--column-name", "Time Calculation",
                  "--item", "Current=SELECTEDMEASURE()", "--item", "Prior Year=CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('Date'[Date]))",
                  "--item", "YoY %=DIVIDE(SELECTEDMEASURE(), 1)", "--item-format", 'YoY %="0.0%"', "--precedence", "10", "--apply")
        self.assertTrue(r["applied"])
        text = (self.defn / "tables" / "Time Intelligence.tmdl").read_text(encoding="utf-8")
        self.assertIn("\tcalculationGroup\n\t\tprecedence: 10", text)
        self.assertIn("\t\tcalculationItem 'Prior Year' = CALCULATE(", text)
        # properties before child objects: Power BI Desktop rejects ordinal after formatStringDefinition
        self.assertIn("\t\t\tordinal: 2\n\t\t\tformatStringDefinition = \"0.0%\"", text)
        self.assertIn("\tpartition 'Time Intelligence' = calculationGroup", text)
        model = (self.defn / "model.tmdl").read_text(encoding="utf-8")
        self.assertIn("\tdiscourageImplicitMeasures", model)
        self.assertIn("ref table 'Time Intelligence'", model)
        names = [m["name"] for m in tk.parse_model(self.proj).measures]
        self.assertNotIn("Current", names)
        with self.assertRaises(AssertionError):
            apply("calcgroup", self.proj, "--name", "X", "--item", "no equals sign")
        apply("undo", self.proj, "--apply")
        self.assertEqual(snapshot(self.proj), self.original)


if __name__ == "__main__":
    unittest.main()
