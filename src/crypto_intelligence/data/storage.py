from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
from typing import Any

from .models import Candle, Provenance


class VersionedDatasetStore:
    """Append-only storage. A new version is created for every acquisition or derivation."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    @staticmethod
    def _path_component(value: str, field: str) -> str:
        """Validate a single portable path component used in dataset paths."""
        if (
            not isinstance(value, str)
            or not value
            or value in {".", ".."}
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value)
            or value.endswith(".")
        ):
            raise ValueError(f"Invalid {field} path component")

        # Windows reserves these names even when followed by an extension.
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update(f"COM{number}" for number in range(1, 10))
        reserved.update(f"LPT{number}" for number in range(1, 10))
        if value.split(".", 1)[0].upper() in reserved:
            raise ValueError(f"Invalid {field} path component")
        return value

    def _dataset_directory(self, category: str, provenance: Provenance) -> Path:
        components = (
            self._path_component(category, "dataset category"),
            self._path_component(provenance.provider, "provider"),
            self._path_component(provenance.market, "market"),
            self._path_component(provenance.timeframe, "timeframe"),
        )
        root = self.data_root.resolve()
        directory = self._path_within_root(root.joinpath(*components), root)
        return directory

    @staticmethod
    def _path_within_root(path: Path, root: Path) -> Path:
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(root)
        except ValueError as error:
            raise ValueError("Dataset path escapes the configured storage root") from error
        return resolved_path

    @staticmethod
    def _version(candles: list[Candle]) -> str:
        material = "\n".join(f"{row.timestamp.isoformat()},{row.open},{row.high},{row.low},{row.close},{row.volume}" for row in candles).encode()
        return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{hashlib.sha256(material).hexdigest()[:12]}-{uuid4().hex[:6]}"

    @staticmethod
    def _write_candles(path: Path, candles: list[Candle]) -> None:
        temporary_path = path.with_suffix(".tmp")

        with temporary_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
            )
            writer.writeheader()
            writer.writerows(item.to_dict() for item in candles)

        temporary_path.replace(path)
    def save_raw(
        self,
        candles: list[Candle],
        provenance: Provenance,
        raw_pages: list[Any],
    ) -> tuple[str, Path, Path]:
        version = self._version(candles)
        directory = self._dataset_directory("raw", provenance)
        directory.mkdir(parents=True, exist_ok=True)

        root = self.data_root.resolve()
        csv_path = self._path_within_root(directory / f"{version}.csv", root)
        self._path_within_root(csv_path.with_suffix(".tmp"), root)
        manifest_path = self._path_within_root(directory / f"{version}.manifest.json", root)
        manifest_temp_path = self._path_within_root(manifest_path.with_suffix(".manifest.tmp"), root)

        raw_bytes = json.dumps(
            raw_pages,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        manifest = {
            "dataset_version": version,
            "provenance": provenance.to_dict(),
            "record_count": len(candles),
            "raw_response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "raw_response_pages": raw_pages,
        }

        try:
            self._write_candles(csv_path, candles)
            manifest["stored_csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            with manifest_temp_path.open("w", encoding="utf-8") as file:
                json.dump(manifest, file, indent=2, sort_keys=True)

            manifest_temp_path.replace(manifest_path)

        except Exception:
            if csv_path.exists():
                csv_path.unlink()

            if manifest_temp_path.exists():
                manifest_temp_path.unlink()

            if manifest_path.exists():
                manifest_path.unlink()

            raise

        return version, csv_path, manifest_path

    def save_validated(
        self,
        candles: list[Candle],
        provenance: Provenance,
        parent_dataset_version: str,
        derivation: str,
    ) -> tuple[str, Path, Path]:
        version = self._version(candles)
        directory = self._dataset_directory("validated", provenance)
        directory.mkdir(parents=True, exist_ok=True)

        root = self.data_root.resolve()
        csv_path = self._path_within_root(directory / f'{version}.csv', root)
        self._path_within_root(csv_path.with_suffix('.tmp'), root)
        manifest_path = self._path_within_root(directory / f'{version}.manifest.json', root)
        manifest_temp_path = self._path_within_root(manifest_path.with_suffix('.manifest.tmp'), root)

        manifest = {
            'dataset_version': version,
            'parent_dataset_version': parent_dataset_version,
            'derivation': derivation,
            'provenance': provenance.to_dict(),
            'record_count': len(candles),
        }

        try:
            self._write_candles(csv_path, candles)
            manifest['stored_csv_sha256'] = hashlib.sha256(csv_path.read_bytes()).hexdigest()

            with manifest_temp_path.open('x', encoding='utf-8') as file:
                json.dump(manifest, file, indent=2, sort_keys=True)

            manifest_temp_path.replace(manifest_path)

        except Exception:
            if csv_path.exists():
                csv_path.unlink()

            if manifest_temp_path.exists():
                manifest_temp_path.unlink()

            raise

        return version, csv_path, manifest_path
