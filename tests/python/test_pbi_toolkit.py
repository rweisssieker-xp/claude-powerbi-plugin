import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TOOLKIT = PLUGIN_ROOT / "scripts" / "python" / "pbi_toolkit.py"
EXAMPLES = PLUGIN_ROOT / "examples"
sys.path.insert(0, str(TOOLKIT.parent))

import pbi_toolkit as tk  # noqa: E402


def run(*args):
    out = subprocess.run([sys.executable, "-I", str(TOOLKIT), *args], capture_output=True, text=True, check=True)
    return out.stdout


class TmdlParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = tk.parse_model(EXAMPLES / "pbip-tmdl-model")

    def test_measures_from_real_tmdl(self):
        names = [m["name"] for m in self.model.measures]
        self.assertEqual(names, ["Total Sales", "Total Sales PY", "Sales YoY %", "Active Customer Sales",
                                 "Sales by Ship Date", "Days Since Last Order"])

    def test_multiline_expression_and_properties(self):
        py = next(m for m in self.model.measures if m["name"] == "Total Sales PY")
        self.assertIn("SAMEPERIODLASTYEAR", py["expression"])
        self.assertNotIn("formatString", py["expression"])
        self.assertEqual(py["formatString"], "#,0.00 €")

    def test_description_and_owner(self):
        ts = next(m for m in self.model.measures if m["name"] == "Total Sales")
        self.assertTrue(ts["description"].startswith("Net invoiced revenue"))
        self.assertEqual(ts["owner"], "Finance Controlling")

    def test_relationships_roles_partitions(self):
        self.assertEqual(len(self.model.relationships), 3)
        self.assertTrue(any(r["crossFilteringBehavior"] == "bothDirections" for r in self.model.relationships))
        self.assertTrue(any(not r["isActive"] for r in self.model.relationships))
        self.assertEqual(self.model.roles[0]["tablePermissions"][0]["table"], "Customer")
        sales = next(p for p in self.model.partitions if p["table"] == "Sales")
        self.assertIn("File.Contents", sales["expression"])

    def test_tables_hidden_flags(self):
        self.assertFalse(self.model.tables["Sales"]["hidden"])
        self.assertTrue(self.model.tables["LocalDateTable_1a2b3c"]["hidden"])
        self.assertEqual(self.model.tables["Date"]["dataCategory"], "Time")


class ScanParity(unittest.TestCase):
    """Fixture results must match Invoke-PowerBIInsightScan.ps1."""

    def check(self, example, level, score, measures):
        d = json.loads(run("scan", str(EXAMPLES / example), "--json"))
        self.assertEqual((d["RiskLevel"], d["RiskScore"], d["MeasureCount"]), (level, score, measures))

    def test_sample_model(self):
        self.check("sample-model", "Medium", 8, 5)

    def test_risky_model(self):
        self.check("risky-model", "Medium", 8, 4)

    def test_clean_model(self):
        self.check("clean-model", "Low", 1, 3)


class TmdlFindings(unittest.TestCase):
    def test_findings_on_real_model(self):
        d = json.loads(run("scan", str(EXAMPLES / "pbip-tmdl-model"), "--json"))
        ids = {f.get("RuleId") for f in d["Findings"]}
        for rule in ("dax.filter-all", "dax.volatile-time", "py.rel.bidi", "py.model.auto-date", "py.pq.drive-path", "py.dax.divide"):
            self.assertIn(rule, ids)

    def test_dependency_impact(self):
        d = json.loads(run("dependencies", str(EXAMPLES / "pbip-tmdl-model"), "--json"))
        top = d["impact"][0]
        self.assertEqual(top["measure"], "Total Sales")
        self.assertEqual(top["impactCount"], 4)

    def test_review_writes_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = json.loads(run("review", str(EXAMPLES / "pbip-tmdl-model"), "--out", tmp))
            self.assertEqual(summary["pbipReadiness"], "Strong")
            for name in ("index.md", "powerbi-insight-scan.json", "powerbi-metric-catalog.md", "powerbi-dependency-graph.md"):
                self.assertTrue((Path(tmp) / name).exists(), name)


class ModelBim(unittest.TestCase):
    def test_bim_parsing(self):
        bim = {"model": {"tables": [{"name": "Sales", "dataCategory": "Time",
                                     "columns": [{"name": "Amount", "dataType": "decimal"}],
                                     "measures": [{"name": "Total", "expression": ["SUM(", "Sales[Amount])"],
                                                   "annotations": [{"name": "Owner", "value": "BI"}]}],
                                     "partitions": [{"name": "p", "mode": "import", "source": {"type": "m", "expression": "let x = 1 in x"}}]}],
                         "relationships": []}}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "model.bim").write_text(json.dumps(bim), encoding="utf-8")
            m = tk.parse_model(Path(tmp))
            self.assertEqual(m.measures[0]["expression"], "SUM(\nSales[Amount])")
            self.assertEqual(m.measures[0]["owner"], "BI")


class TrustAndGate(unittest.TestCase):
    """Parity with New-PowerBIKpiTrustScore.ps1 / New-PowerBITrustReleaseGate.ps1 on the sample model."""

    def test_trust_parity(self):
        d = json.loads(run("trust", str(EXAMPLES / "sample-model"), "--json"))
        self.assertEqual(d["overallTrustScore"], 56)
        scores = {m["name"]: m["trustScore"] for m in d["metrics"]}
        self.assertEqual(scores, {"All Customer Sales": 45, "Refresh Sensitive Sales": 45, "Total Sales": 55,
                                  "Total Sales Prior Year": 65, "Sales YoY %": 70})

    def test_gate_decision(self):
        self.assertEqual(json.loads(run("gate", str(EXAMPLES / "sample-model"), "--json"))["decision"], "No-Go")


WIZARD = PLUGIN_ROOT / "scripts" / "python" / "pbi_model_wizard.py"
SOURCES = EXAMPLES / "model-wizard-sources"


class ModelWizard(unittest.TestCase):
    def test_initialize_generates_star_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([sys.executable, "-I", str(WIZARD), "--project-name", "SalesModel", "--output-directory", tmp,
                                  "--source", str(SOURCES / "Sales.csv"), "--source", str(SOURCES / "Customer.csv"),
                                  "--source", str(SOURCES / "Product.json"), "--initialize"], capture_output=True, text=True, check=True)
            d = json.loads(out.stdout)
            arch = d["architecture"]
            self.assertEqual(arch["factTables"], ["FactSales"])
            self.assertEqual(arch["dimensionTables"], ["DimCustomer", "DimProduct", "DimDate"])
            targets = {r["to"] for r in arch["relationships"]}
            self.assertEqual(targets, {"DimCustomer[CustomerKey]", "DimProduct[ProductKey]", "DimDate[Date]"})
            self.assertIn("SUM(FactSales[Amount])", [m["expression"] for m in d["semanticPlan"]["measureDrafts"]])
            drafts = Path(tmp) / "SalesModel" / "model-drafts"
            pq = (drafts / "power-query-source-drafts.md").read_text(encoding="utf-8")
            self.assertIn('Delimiter=";"', pq)
            self.assertIn("Json.Document", pq)
            model = tk.parse_model(drafts / "tmdl")
            self.assertEqual(len(model.measures), 5)
            self.assertEqual(len(model.relationships), 3)

    def test_declared_connector_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "src.json"
            cfg.write_text(json.dumps({"schema": "codex.powerbi.dataSourceConfig.v1", "sources": [
                {"name": "Warehouse Orders", "connectorKind": "SQL Server database", "connection": "server=x;password=geheim", "columns": ["OrderDate", "Amount"]}]}))
            out = subprocess.run([sys.executable, "-I", str(WIZARD), "--project-name", "W", "--source-config", str(cfg)],
                                 capture_output=True, text=True, check=True)
            self.assertNotIn("geheim", out.stdout)
            self.assertIn("[REDACTED]", out.stdout)


class ReportAndPbix(unittest.TestCase):
    def test_pbir_report_checks(self):
        d = json.loads(run("scan", str(EXAMPLES / "pbip-tmdl-model"), "--json"))
        by_rule = {f.get("RuleId"): f for f in d["Findings"]}
        self.assertIn("Sales[Gross Margin]", by_rule["py.report.broken-field"]["Detail"])
        self.assertNotIn("[IsActive]", by_rule["py.report.broken-field"]["Detail"])  # alias "c" in filter resolves to Customer
        unused = by_rule["py.report.unused-measure"]["Detail"]
        self.assertIn("Days Since Last Order", unused)
        self.assertNotIn("Total Sales PY", unused)  # referenced by Sales YoY %

    def _fake_pbix(self, tmp):
        import zipfile
        path = Path(tmp) / "Demo.pbix"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Version", "1.28".encode("utf-16-le"))
            z.writestr("DataModel", b"not-a-real-model")
            z.writestr("Report/definition/report.json", json.dumps({"publicCustomVisuals": []}))
            z.writestr("Report/definition/pages/pages.json", json.dumps({"pageOrder": ["p1", "p2"]}))
            z.writestr("Report/definition/pages/p1/page.json", json.dumps({"displayName": "Overview"}))
            z.writestr("Report/definition/pages/p2/page.json", json.dumps({"displayName": "Empty"}))
            z.writestr("Report/definition/pages/p1/visuals/v1/visual.json", json.dumps(
                {"name": "v1", "visual": {"visualType": "myVisualABC", "query": {"queryState": {"Values": {"projections": [
                    {"field": {"Column": {"Expression": {"SourceRef": {"Entity": "T"}}, "Property": "C"}}}]}}}}}))
            z.writestr("Report/CustomVisuals/myVisualABC/package.json", json.dumps({"visual": {"guid": "myVisualABC", "displayName": "My Visual", "version": "1.0.0"}}))
        return path

    def test_pbix_report_only_when_model_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = tk.parse_model(self._fake_pbix(tmp))
            self.assertEqual(m.report["format"], "PBIR")
            self.assertEqual([p["name"] for p in m.report["pages"]], ["Overview", "Empty"])
            self.assertEqual(m.report["visuals"][0]["fields"], ["T[C]"])
            self.assertTrue(m.notes)  # explains why the model was not read
            d = json.loads(run("scan", str(Path(tmp) / "Demo.pbix"), "--json"))
            rules = {f.get("RuleId") for f in d["Findings"]}
            self.assertIn("py.report.custom-visual", rules)
            self.assertIn("py.report.empty-page", rules)
            self.assertNotIn("py.report.broken-field", rules)  # no model -> no false broken-field claims

    def test_portfolio_review_of_pbix_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._fake_pbix(tmp)
            second = Path(tmp) / "Demo.pbix"
            (Path(tmp) / "Copy.pbix").write_bytes(second.read_bytes())
            out = Path(tmp) / "out"
            summary = json.loads(run("review", tmp, "--out", str(out)))
            self.assertEqual(summary["files"], 2)
            self.assertTrue((out / "index.md").exists())
            self.assertTrue((out / "Demo" / "powerbi-model-summary.md").exists())

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("pbixray"), "pbixray not installed")
    def test_pbixray_path_available(self):
        self.assertTrue(callable(tk.parse_pbix))


if __name__ == "__main__":
    unittest.main()
