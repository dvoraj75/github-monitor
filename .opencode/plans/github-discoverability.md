# Plan: Improve GitHub Discoverability

## Summary
Make the github-monitor repository more discoverable and professional on GitHub by addressing security, CI, metadata, community health files, and documentation gaps.

---

## 1. Security Fix: Add `config.toml` to `.gitignore`

**File:** `.gitignore`
**Change:** Append at end:
```
# Project-specific
config.toml
```

**Manual action needed:** Rotate the GitHub personal access token (`ghp_3iV5...`) since it's been sitting in an unprotected file.

---

## 2. GitHub Actions CI Workflow

**New file:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.13

      - name: Install dependencies
        run: uv sync

      - name: Lint
        run: uv run ruff check .

      - name: Format check
        run: uv run ruff format --check .

      - name: Type check
        run: uv run mypy github_monitor

      - name: Test
        run: uv run pytest
```

---

## 3. Flesh Out `pyproject.toml` Metadata

**File:** `pyproject.toml`
**Change:** Update `[project]` section to:

```toml
[project]
name = "github-monitor"
version = "1.0.0"
description = "Daemon that monitors GitHub PRs and exposes state over D-Bus"
readme = "README.md"
license = "MIT"
requires-python = ">=3.13"
authors = [
    { name = "Jan Dvorak" },
]
keywords = [
    "github",
    "pull-request",
    "monitor",
    "dbus",
    "notifications",
    "daemon",
    "asyncio",
    "linux",
]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Environment :: No Input/Output (Daemon)",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Version Control :: Git",
]
dependencies = [
    "aiohttp>=3.9,<4",
    "dbus-next>=0.2.3,<1",
]

[project.urls]
Homepage = "https://github.com/dvoraj75/github-monitor"
Repository = "https://github.com/dvoraj75/github-monitor"
Documentation = "https://github.com/dvoraj75/github-monitor/tree/main/docs"
"Bug Tracker" = "https://github.com/dvoraj75/github-monitor/issues"
```

---

## 4. README Improvements

**File:** `README.md`

### 4a. Add CI badge + fix clone URL (line 1-3)

Replace the badge line with:
```markdown
![CI](https://github.com/dvoraj75/github-monitor/actions/workflows/ci.yml/badge.svg) ![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000) ![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue) ![Async](https://img.shields.io/badge/async-asyncio-purple)
```

### 4b. Add Features section after the description paragraph (after line 7)

```markdown

## Features

- **Live PR monitoring** -- polls GitHub Search API for PRs assigned to you or requesting your review
- **Desktop notifications** -- individual notifications for 1-3 new PRs, summary for more; includes author avatars and clickable links
- **D-Bus interface** -- query current PR state, trigger manual refresh, subscribe to change signals
- **Systemd integration** -- runs as a user service with security hardening
- **Resilient** -- exponential backoff, rate limit handling, graceful shutdown via signals (SIGTERM, SIGHUP for config reload)
```

### 4c. Fix clone URL (line 59)

Replace:
```
git clone https://github.com/<you>/github-monitor.git
```
With:
```
git clone https://github.com/dvoraj75/github-monitor.git
```

### 4d. Add screenshot placeholder (after Features section)

```markdown
<!-- TODO: Add a screenshot or GIF of the desktop notification here -->
<!-- Example: ![Notification screenshot](docs/screenshot.png) -->
```

---

## 5. Bug Report Issue Template

**New file:** `.github/ISSUE_TEMPLATE/bug_report.yml`

```yaml
name: Bug Report
description: Report a bug in github-monitor
labels: ["bug"]
body:
  - type: textarea
    id: description
    attributes:
      label: Description
      description: A clear description of the bug.
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      description: How can we reproduce the issue?
      placeholder: |
        1. Configure with ...
        2. Run `uv run github-monitor ...`
        3. See error ...
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
      description: What did you expect to happen?
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: Actual behavior
      description: What actually happened? Include any error output or logs.
    validations:
      required: true
  - type: input
    id: python-version
    attributes:
      label: Python version
      placeholder: "3.13.0"
    validations:
      required: true
  - type: input
    id: os
    attributes:
      label: Operating system
      placeholder: "Ubuntu 24.04"
    validations:
      required: true
```

---

## 6. Feature Request Issue Template

**New file:** `.github/ISSUE_TEMPLATE/feature_request.yml`

```yaml
name: Feature Request
description: Suggest a new feature or enhancement
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: What problem does this feature solve?
    validations:
      required: true
  - type: textarea
    id: solution
    attributes:
      label: Proposed solution
      description: How would you like this to work?
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
      description: Any alternative solutions or workarounds you've considered?
    validations:
      required: false
```

---

## 7. CONTRIBUTING.md

**New file:** `.github/CONTRIBUTING.md`

```markdown
# Contributing to github-monitor

Thanks for your interest in contributing!

## Development setup

```bash
git clone https://github.com/dvoraj75/github-monitor.git
cd github-monitor
uv sync
```

## Running checks

```bash
uv run pytest                  # tests (151 passing)
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run mypy github_monitor     # type check
```

All four must pass before a PR will be merged.

## Code style

- Full type hints everywhere (`str | None`, not `Optional[str]`)
- `from __future__ import annotations` in every file
- Frozen dataclasses for data models
- All I/O is async
- See [docs/development.md](../docs/development.md) for full conventions

## Pull requests

1. Fork the repo and create a feature branch
2. Make your changes
3. Ensure all checks pass (`pytest`, `ruff check`, `ruff format --check`, `mypy`)
4. Open a PR with a clear description of the change
```

---

## 8. CHANGELOG.md

**New file:** `CHANGELOG.md`

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-01

### Added

- GitHub PR polling via Search Issues API with pagination and rate limiting
- In-memory state store with diff computation (new/closed/updated PRs)
- Desktop notifications via `notify-send` with author avatars and clickable links
- D-Bus session bus interface (`org.github_monitor.Daemon`) with methods: `GetPullRequests`, `GetStatus`, `Refresh` and signal: `PullRequestsChanged`
- TOML configuration with environment variable override support (`GITHUB_TOKEN`)
- Exponential backoff retries for API failures
- Graceful shutdown (SIGTERM/SIGINT) and config reload (SIGHUP)
- Systemd user service with security hardening
- 151 tests with full coverage
```

---

## 9. Manual Actions (post-push)

These can't be automated and need to be done in GitHub's web UI:

1. **Rotate the GitHub token** -- Settings > Developer settings > Personal access tokens > delete the old one and create a new one
2. **Set repository topics** -- on the repo page, click the gear icon next to "About" and add topics: `github`, `pull-requests`, `notifications`, `dbus`, `linux`, `daemon`, `python`, `asyncio`, `monitoring`
3. **Write a repo description** -- in the same "About" section, set it to: "Async Python daemon that monitors GitHub PRs and sends desktop notifications"
4. **Capture a screenshot** -- take a screenshot of a desktop notification and add it as `docs/screenshot.png`, then uncomment the image tag in the README

---

## Files Changed Summary

| File | Action |
|---|---|
| `.gitignore` | Edit -- add `config.toml` |
| `.github/workflows/ci.yml` | Create |
| `pyproject.toml` | Edit -- add metadata fields |
| `README.md` | Edit -- CI badge, features section, fix clone URL, screenshot placeholder |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Create |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Create |
| `.github/CONTRIBUTING.md` | Create |
| `CHANGELOG.md` | Create |
