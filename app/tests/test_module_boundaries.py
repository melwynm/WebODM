from pathlib import Path

from django.test import SimpleTestCase


class ModuleBoundaryTests(SimpleTestCase):
    def repo_root(self):
        return Path(__file__).resolve().parents[2]

    def python_files(self, *roots):
        repo_root = self.repo_root()
        for root in roots:
            root_path = repo_root / root
            for path in root_path.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                yield path

    def test_legacy_monitoring_facade_is_removed(self):
        self.assertFalse((self.repo_root() / "app" / "monitoring.py").exists())

    def test_runtime_code_does_not_import_legacy_monitoring_facade(self):
        offenders = []
        for path in self.python_files("app", "worker", "coreplugins"):
            if path.name == "test_module_boundaries.py":
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if "app.monitoring" in text:
                offenders.append(str(path.relative_to(self.repo_root())))

        self.assertEqual([], offenders)

    def test_services_do_not_import_api_layer(self):
        offenders = []
        for path in self.python_files("app/services"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "from app.api" in text or "import app.api" in text:
                offenders.append(str(path.relative_to(self.repo_root())))

        self.assertEqual([], offenders)

    def test_services_do_not_import_worker_layer(self):
        offenders = []
        for path in self.python_files("app/services"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "from worker" in text or "import worker" in text:
                offenders.append(str(path.relative_to(self.repo_root())))

        self.assertEqual([], offenders)

    def test_runtime_code_does_not_import_test_named_async_result(self):
        offenders = []
        for path in self.python_files("app", "worker", "coreplugins"):
            if path.name == "test_module_boundaries.py":
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if "TestSafeAsyncResult" in text:
                offenders.append(str(path.relative_to(self.repo_root())))

        self.assertEqual([], offenders)
