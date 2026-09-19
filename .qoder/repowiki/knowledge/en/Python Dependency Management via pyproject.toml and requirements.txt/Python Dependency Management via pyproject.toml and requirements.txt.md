---
kind: dependency_management
name: Python Dependency Management via pyproject.toml and requirements.txt
category: dependency_management
scope:
    - '**'
source_files:
    - pyproject.toml
    - requirements.txt
    - semantic_reliability_engine.egg-info/requires.txt
---

## What system/approach is used

This repository uses standard Python packaging with **setuptools** (build backend `setuptools.build_meta`, requires `setuptools>=61.0`) declared in `pyproject.toml`. Dependencies are declared as version-ranged strings in two places:
- Runtime dependencies: the `[project]` `dependencies` list in `pyproject.toml`
- A flat `requirements.txt` at the repo root that mirrors the same runtime packages plus `pytest`

There is no lockfile (no `poetry.lock`, `Pipfile.lock`, `uv.lock`, or `requirements.txt` pinning), no vendored third-party code, and no private PyPI registry configuration. The project also defines an optional `dev` extra (`[project.optional-dependencies] dev = ["pytest>=8.0.0"]`) for test-only installs.

## Key files and packages

- `pyproject.toml` — single source of truth for package metadata, build system, runtime dependencies, optional dev dependencies, CLI entry points (`semantic-reliability`, `sre` → `semantic_reliability.cli:main`), setuptools package discovery, and pytest config.
- `requirements.txt` — flattened dependency list used by environments that consume a plain requirements file; it duplicates the runtime deps from `pyproject.toml` and adds `pytest`.
- `semantic_reliability_engine.egg-info/` — generated metadata from `pip install .` / `python -m build`; contains `requires.txt`, `PKG-INFO`, `SOURCES.txt`, `entry_points.txt`, confirming setuptools-based distribution.

## Architecture and conventions

- **Flat layout**: all runtime dependencies are pinned with minimum versions only (e.g. `sqlglot>=25.0.0`, `pydantic>=2.0.0`, `duckdb>=1.0.0`, `pandas>=2.0.0`, `jsonschema>=4.0.0`, `requests>=2.31.0`, `click>=8.1.0`, `rich>=13.0.0`, `pyyaml>=6.0.1`). No upper bounds are specified anywhere in this repo.
- **No lockfile strategy**: there is no `poetry.lock`, `Pipfile.lock`, `uv.lock`, or pinned `requirements.txt`. Reproducible builds therefore rely on the minimum-version constraints rather than exact hashes.
- **Dev vs runtime split**: development-only tooling (`pytest`) lives exclusively in the `[project.optional-dependencies] dev` group and is not required to install the package itself; `requirements.txt` includes it for convenience when installing via `pip install -r requirements.txt`.
- **No vendoring**: the tree contains no `vendor/` directory and no vendored third-party sources. All third-party code is resolved at install time from PyPI.
- **No private registry / authentication**: there is no `.pypirc`, `pip.conf`, `pip.conf.d/`, Poetry/uv private index config, or `--index-url` overrides visible in the repo.

## Conventions and constraints

- **Minimum-version pins only**: every dependency uses `>=X.Y.Z` syntax; no `==` or `<` constraints are present. This is enforced by the fact that both `pyproject.toml` and `requirements.txt` use this style consistently.
- **Python version gate**: `requires-python = ">=3.10"` in `pyproject.toml` constrains the supported interpreter.
- **Single package namespace**: `tool.setuptools.packages.find` restricts discovered packages to those matching `semantic_reliability*`, preventing accidental inclusion of unrelated modules.
- **CLI exposure via entry points**: the package exposes two console scripts (`semantic-reliability`, `sre`) both pointing at `semantic_reliability.cli:main`, so users invoke the engine through these commands after installation.
- **No CI dependency management**: the GitHub Actions workflows under `.github/workflows/` do not include steps that update or validate lockfiles; dependency updates would be manual edits to `pyproject.toml` and `requirements.txt`.