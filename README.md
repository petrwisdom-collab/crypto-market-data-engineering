# Crypto Data Engineering Portfolio

A curated Python portfolio project focused on careful handling of historical OHLCV data. It demonstrates data models, provider boundaries, candle validation, timeframe aggregation, provenance-aware storage, and chronological replay.

This is a public portfolio edition. It intentionally excludes the private market-analysis engine, proprietary experiments and research hypotheses, trained machine-learning models, implemented news intelligence, and autonomous order execution. The included package does not place trades.

## Included capabilities

- Typed candle, provider-response, and provenance models.
- Explicit provider adapters for CoinGecko, Coinbase Exchange, Kraken, and Binance Spot. Binance Spot support in this edition is limited to BTC/USDT hourly candles.
- Historical acquisition helpers that report the coverage actually returned by a provider and do not fabricate missing candles.
- OHLCV validation, missing-period reporting, fixed-timeframe aggregation, and cross-source comparison.
- Versioned CSV storage with JSON metadata, content hashes, and resolved-path containment checks.
- A legacy CSV audit helper that leaves its input unchanged.
- Chronological replay that exposes only candles available at each replay step.

Provider adapters make network requests only when their fetch methods are called. The test suite uses mocked provider responses and synthetic data; it does not contact providers.

## Requirements and installation

Python 3.11 or newer is required. The package uses only the Python standard library at runtime.

### Windows PowerShell

From the project directory, run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### macOS or Linux

From the project directory, run:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Activation is optional when invoking the environment's Python executable directly. On Windows use `.venv\Scripts\python.exe`; on macOS or Linux use `.venv/bin/python`.

## Tests

Run the local, offline test suite from the project directory.

**Windows PowerShell:**

```powershell
python -m unittest discover -s tests -v
```

**macOS or Linux:**

```sh
python -m unittest discover -s tests -v
```

Tests use temporary directories for generated files and synthetic or mocked inputs. They do not require private datasets, checkpoints, credentials, or network access.

## Configuration and data

No environment variables or credentials are required. Provider adapters accept a base URL and can be called explicitly by an application. Before writing, storage resolves the configured data root and candidate paths, rejects dataset path components outside its accepted format, and checks that each resolved candidate remains under that root. These checks help prevent path traversal and paths that resolve outside the configured root. They do not guarantee safety against concurrent filesystem changes or hostile symlink replacement. Choose a storage location you control. Tests use temporary directories that are removed automatically.

## Scope

This edition is a data-engineering and replay foundation, not a complete trading or market-intelligence product. It does not include the private market-analysis or signal logic, research experiments, a trained ML model, implemented news intelligence, a command-line application, or order execution. The provider adapters are data access code and do not submit orders.

Historical experiment results from the separate private project are not included and cannot be reproduced from this edition alone.
