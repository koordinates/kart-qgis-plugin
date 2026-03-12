# AGENTS.md

This file provides guidance to agentic coding tools when working with code in this repository.

## Overview

This is a QGIS plugin that integrates [Kart](https://kartproject.org) - a distributed version control system for geospatial and tabular data. The plugin provides GUI dialogs and Processing algorithms for working with Kart repositories directly from QGIS.

## Development Setup

Install the plugin for local development:

```bash
python helper.py install
```

This creates a symlink from `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/kart` to the repository's `kart/` directory on macOS.

## Common Commands

**Run tests:**
```bash
# Via Docker (CI environment)
docker compose -f .docker/docker-compose.gh.yml run --build --rm qgis /usr/src/.docker/run-docker-tests.sh

# Direct pytest (requires QGIS environment)
pytest -v
```

**Lint code:**
```bash
# Uses flake8 (runs in CI)
flake8
```

**Format code:**
```bash
black kart/
# Or install pre-commit hooks
pre-commit install --install-hooks
```

**Package plugin:**
```bash
python helper.py package
# Creates kart.zip in repo root
```

## Architecture

**Core components:**

- `kartapi.py` - Main API wrapper around the Kart CLI. Contains `Repository` class with methods for all Kart operations (commit, branch, merge, diff, etc.) and `executeKart()` function that handles subprocess calls.

- `plugin.py` - QGIS plugin entry point (`KartPlugin` class). Creates the dock widget, menu items, and initializes the Processing provider.

- `gui/` - Qt-based UI components (dialogs, dock widget, history viewer, diff viewer, map swipe tool). Main entry is `dockwidget.py` which provides the repository browser.

- `processing/` - QGIS Processing algorithms (repos, branches, tags, data import, remotes). Registered via `KartProvider` in `processing/__init__.py`.

- `core/repo_manager.py` - Singleton `RepoManager` class that tracks known repositories and their associated layers. Persists repo list to QGIS settings.

- `layers.py` - `LayerTracker` singleton that monitors QGIS layers and maintains visual indicators (bounding boxes) for Kart-managed layers.

**Key design patterns:**

- All Kart operations go through `executeKart()` which manages subprocess calls, environment variables, and error handling.
- The `@executeskart` decorator wraps functions to check Kart installation and display user-friendly error dialogs.
- Repository working copies can be file-based (GeoPackage) or database-based (PostgreSQL/MySQL/SQL Server).
- The plugin uses QGIS settings to persist configuration (repos list, Kart path, bounding box colors).

## Plugin Requirements

- QGIS 3.16+
- Kart 0.15.3 installed separately (minimum supported: 0.14.0)
- Compatible with Python 3.9+

## Testing Notes

Tests run in Docker containers with QGIS pre-installed. Test matrix includes QGIS 3.34 and latest. The plugin is tested against Kart 0.15.3.

Test files are in `kart/tests/` and use pytest. Test data is in `kart/tests/data/`.
