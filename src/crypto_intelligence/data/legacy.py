from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path

from .models import Candle
from .validation import CandleValidator


def audit_legacy_price_csv(path: Path, claimed_timeframe: str, output_path: Path) -> dict:
    """Audit a legacy price CSV without changing the source file."""
    candles = []
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            stamp, price = datetime.fromisoformat(row["timestamp"]), float(row["price_usd"])
            volume = float(row["volume_usd"]) if row.get("volume_usd") not in (None, "") else None
            candles.append(Candle(stamp, price, price, price, price, volume))
    validation = CandleValidator().validate(candles, claimed_timeframe, closed_only=False)
    report = {"audit_type": "legacy_dataset_integrity_audit", "legacy_path": str(path), "claimed_timeframe": claimed_timeframe, "record_count": len(candles), "observed_cadence_seconds": validation.get("observed_cadence_seconds"), "validation_status": validation["status"], "findings": validation["findings"], "conclusion": "The source CSV was read without modification."}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
