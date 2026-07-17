from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def test_streamlit_is_local_and_usage_statistics_are_disabled(self):
        config_path = PROJECT_ROOT / ".streamlit" / "config.toml"
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)

        self.assertEqual(config["server"]["address"], "127.0.0.1")
        self.assertTrue(config["server"]["headless"])
        self.assertFalse(config["browser"]["gatherUsageStats"])

    def test_windows_launchers_offer_noninteractive_checks(self):
        for filename in (
            "setup_windows.bat",
            "run_windows.bat",
            "start_windows.bat",
        ):
            script = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
            self.assertIn('"--check"', script)
            self.assertIn("if defined CI exit /b 1", script)

    def test_platform_launchers_use_the_shared_prepare_and_browser_flow(self):
        windows_setup = (PROJECT_ROOT / "setup_windows.bat").read_text(encoding="utf-8")
        windows_run = (PROJECT_ROOT / "run_windows.bat").read_text(encoding="utf-8")
        unix_run = (PROJECT_ROOT / "run.sh").read_text(encoding="utf-8")

        self.assertIn("-m scripts.prepare_app", windows_setup)
        self.assertIn('set "PYTHON_LAUNCHER=python"', windows_setup)
        self.assertIn("https://www.python.org/downloads/windows/", windows_setup)
        self.assertIn("scripts\\launch_app.py", windows_run)
        self.assertIn("-m scripts.prepare_app", unix_run)
        self.assertIn("scripts/launch_app.py", unix_run)

    def test_pinned_runtime_dependencies_include_security_fixes(self):
        requirements = (PROJECT_ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
        runtime = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("pyarrow==23.0.1", requirements)
        self.assertIn("streamlit==1.54.0", requirements)
        self.assertIn("streamlit==1.54.0", runtime)
        self.assertIn('"streamlit==1.54.0"', pyproject)


if __name__ == "__main__":
    unittest.main()
