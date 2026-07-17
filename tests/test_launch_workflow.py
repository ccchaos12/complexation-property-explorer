from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import build_srd46_sqlite
from scripts.download_srd46 import (
    NIST_SRD46_SQL_SHA256,
    ensure_download,
    sha256_file,
)
from scripts.launch_app import app_url, wait_until_ready
from scripts.prepare_app import prepare


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
            source = root / "official-source.zip"
            source.write_bytes(b"official bytes")
            destination = root / "downloaded.zip"
            destination.write_bytes(b"unverified bytes")
            expected = hashlib.sha256(source.read_bytes()).hexdigest()

            status = ensure_download(
                url=source.as_uri(),
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


class PreparationWorkflowTests(unittest.TestCase):
    def test_configured_database_skips_default_source_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "curated.db"
            database.touch()
            with patch.dict(
                "os.environ",
                {"COMPLEXATION_DB_PATH": str(database)},
            ), patch(
                "scripts.prepare_app.ensure_srd46_files"
            ) as mocked_download:
                selected = prepare()

            self.assertEqual(selected, database.resolve())
            mocked_download.assert_not_called()


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


if __name__ == "__main__":
    unittest.main()
