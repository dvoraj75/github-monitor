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
