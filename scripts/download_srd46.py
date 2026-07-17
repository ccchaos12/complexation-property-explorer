#!/usr/bin/env python3
"""Download the original NIST SRD 46 SQL package with checksum verification."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

NIST_SRD46_DATASET_URL = "https://data.nist.gov/od/id/mds2-2154"
NIST_SRD46_SQL_URL = (
    "https://data.nist.gov/od/ds/ark:/88434/mds2-2154/SRD%2046%20SQL.zip"
)
NIST_SRD46_SQL_SHA256 = (
    "141269bb8c6d9e8271a5b4bff35f7c9fa913938bb50a62c096847de67e382d18"
)
NIST_SRD46_README_URL = (
    "https://data.nist.gov/od/ds/ark:/88434/mds2-2154/SRD%2046%20README.txt"
)
NIST_SRD46_README_SHA256 = (
    "069d578fd67930146d83b303057bf15faeffe905c64902da94a321afb2ab52d1"
)
USER_AGENT = "Complexation-Property-Explorer/0.3 (+https://doi.org/10.18434/M32154)"
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preserve_invalid_file(path: Path) -> Path:
    suffix = time.strftime("%Y%m%d-%H%M%S")
    base_name = f"{path.name}.invalid-{suffix}"
    preserved = path.with_name(base_name)
    counter = 1
    while preserved.exists():
        preserved = path.with_name(f"{base_name}-{counter}")
        counter += 1
    path.replace(preserved)
    return preserved


def ensure_download(
    *,
    url: str,
    destination: Path,
    expected_sha256: str,
    label: str,
    attempts: int = 3,
) -> str:
    """Keep a verified local file or atomically download an official copy."""
    if urlsplit(url).scheme != "https":
        raise ValueError("Downloads must use an HTTPS URL")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_file():
        current_sha256 = sha256_file(destination)
        if current_sha256 == expected_sha256:
            print(f"{label} is already present and verified.")
            return "existing"
        preserved = _preserve_invalid_file(destination)
        print(f"Preserved an unverified existing file as: {preserved.name}")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{destination.name}.",
            suffix=".download",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            print(f"Downloading {label} from NIST (attempt {attempt}/{attempts})...")
            request = Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
            with urlopen(  # noqa: S310
                request,
                timeout=90,
            ) as response, temporary_path.open("wb") as target:
                total = int(response.headers.get("Content-Length", "0"))
                downloaded = 0
                while chunk := response.read(CHUNK_SIZE):
                    target.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        print(
                            f"\r  {downloaded / 1_048_576:.1f} / "
                            f"{total / 1_048_576:.1f} MiB",
                            end="",
                            flush=True,
                        )
                if total:
                    print()

            downloaded_sha256 = sha256_file(temporary_path)
            if downloaded_sha256 != expected_sha256:
                raise ValueError(
                    f"{label} checksum mismatch: expected {expected_sha256}, "
                    f"received {downloaded_sha256}"
                )
            temporary_path.replace(destination)
            print(f"Verified SHA-256: {downloaded_sha256}")
            return "downloaded"
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = error
            if attempt < attempts:
                print(f"Download attempt failed: {error}. Retrying...")
                time.sleep(attempt)
        finally:
            temporary_path.unlink(missing_ok=True)

    raise RuntimeError(
        f"Could not download {label}. Check the internet connection or download it "
        f"manually from {NIST_SRD46_DATASET_URL}. Last error: {last_error}"
    )


def ensure_srd46_files(archive_path: Path, readme_path: Path) -> None:
    ensure_download(
        url=NIST_SRD46_SQL_URL,
        destination=archive_path,
        expected_sha256=NIST_SRD46_SQL_SHA256,
        label="NIST SRD 46 SQL.zip",
    )
    ensure_download(
        url=NIST_SRD46_README_URL,
        destination=readme_path,
        expected_sha256=NIST_SRD46_README_SHA256,
        label="NIST SRD 46 README",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--readme-output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_srd46_files(args.output, args.readme_output)
    except Exception as error:
        print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
