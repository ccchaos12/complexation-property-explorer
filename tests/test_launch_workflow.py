from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import build_srd46_sqlite
from scripts.download_srd46 import (
    NIST_SRD46_SQL_SHA256,
    ensure_download,
    sha256_file,
)
from scripts.launch_app import (
    app_url,
    select_available_port,
    stop_process,
    wait_until_ready,
)
from scripts.prepare_app import prepare, validate_canonical_database
from tests.support import create_test_database


class DownloadWorkflowTests(unittest.TestCase):
    def test_download_checksum_matches_the_database_builder(self):
        self.assertEqual(
            NIST_SRD46_SQL_SHA256,
            build_srd46_sqlite.EXPECTED_ARCHIVE_SHA256,
        )

    def test_existing_verified_file_does_not_use_the_network(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.zip"
            destination.write_bytes(b"verified source")
            checksum = hashlib.sha256(destination.read_bytes()).hexdigest()

            with patch("scripts.download_srd46.urlopen") as mocked_urlopen:
                status = ensure_download(
                    url="https://example.invalid/source.zip",
                    destination=destination,
                    expected_sha256=checksum,
                    label="test source",
                )

            self.assertEqual(status, "existing")
            mocked_urlopen.assert_not_called()

    def test_invalid_file_is_preserved_before_an_atomic_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official_bytes = b"official bytes"
            destination = root / "downloaded.zip"
            destination.write_bytes(b"unverified bytes")
            expected = hashlib.sha256(official_bytes).hexdigest()
            response = io.BytesIO(official_bytes)
            response.headers = {"Content-Length": str(len(official_bytes))}

            with patch(
                "scripts.download_srd46.urlopen",
                return_value=response,
            ):
                status = ensure_download(
                    url="https://example.test/official-source.zip",
                    destination=destination,
                    expected_sha256=expected,
                    label="test source",
                    attempts=1,
                )

            self.assertEqual(status, "downloaded")
            self.assertEqual(sha256_file(destination), expected)
            self.assertEqual(
                len(list(root.glob("downloaded.zip.invalid-*"))),
                1,
            )

    def test_non_https_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                ensure_download(
                    url=Path(directory, "source.zip").as_uri(),
                    destination=Path(directory) / "downloaded.zip",
                    expected_sha256="0" * 64,
                    label="test source",
                )


class PreparationWorkflowTests(unittest.TestCase):
    def test_configured_database_skips_default_source_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = create_test_database(Path(directory) / "curated.db")
            with patch.dict(
                "os.environ",
                {"COMPLEXATION_DB_PATH": str(database)},
            ), patch(
                "scripts.prepare_app.ensure_srd46_files"
            ) as mocked_download:
                selected = prepare()

            self.assertEqual(selected, database.resolve())
            mocked_download.assert_not_called()

    def test_direct_script_entry_points_can_import_project_modules(self):
        project_root = Path(__file__).resolve().parents[1]
        help_result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "scripts/build_srd46_sqlite.py",
                "--help",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)

        with tempfile.TemporaryDirectory() as directory:
            database = create_test_database(Path(directory) / "curated.db")
            environment = {**os.environ, "COMPLEXATION_DB_PATH": str(database)}
            prepare_result = subprocess.run(  # noqa: S603
                [sys.executable, "scripts/prepare_app.py"],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(prepare_result.returncode, 0, prepare_result.stderr)
        self.assertIn("Application database ready", prepare_result.stdout)

    def test_incompatible_configured_database_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "not-canonical.db"
            database.touch()
            with patch.dict(
                "os.environ",
                {"COMPLEXATION_DB_PATH": str(database)},
            ), patch(
                "scripts.prepare_app.ensure_srd46_files"
            ) as mocked_download:
                with self.assertRaisesRegex(ValueError, "missing or empty"):
                    prepare()

            mocked_download.assert_not_called()

    def test_canonical_validation_rejects_foreign_key_damage(self):
        with tempfile.TemporaryDirectory() as directory:
            database = create_test_database(Path(directory) / "damaged.db")
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute(
                    "UPDATE constant_records SET ligand_id = 'MISSING' "
                    "WHERE record_id = 'NIST_SRD46:CONSTANT:100001'"
                )
                connection.commit()

            with self.assertRaisesRegex(ValueError, "foreign-key"):
                validate_canonical_database(database)


class BrowserLaunchTests(unittest.TestCase):
    def test_local_address_is_presented_as_localhost(self):
        self.assertEqual(app_url("127.0.0.1", 8501), "http://localhost:8501")

    def test_wait_until_ready_stops_after_health_succeeds(self):
        process = Mock()
        process.poll.return_value = None
        with patch(
            "scripts.launch_app.is_healthy",
            side_effect=[False, True],
        ), patch("scripts.launch_app.time.sleep"):
            self.assertTrue(wait_until_ready(process, "127.0.0.1", 8501, timeout=2))

    def test_busy_default_port_uses_the_next_available_port(self):
        with patch(
            "scripts.launch_app.is_port_available",
            side_effect=[False, True],
        ):
            self.assertEqual(select_available_port("127.0.0.1", 8501), 8502)

    def test_process_is_killed_if_graceful_shutdown_times_out(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired("streamlit", 10),
            9,
        ]

        self.assertEqual(stop_process(process), 9)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
