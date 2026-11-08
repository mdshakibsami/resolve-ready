# Changelog

All notable changes to Resolve Ready are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/).

## [1.1.2] - 2026-11-08

### Fixed

- Rebuilt the AppImage's bundled FFmpeg with x86 assembly enabled. FFmpeg
  6.1.2's C-only 8-bit DNxHR encoder corrupted chroma, producing magenta/green
  horizontal bars from the SQ, LB and HQ presets. HQX and ProRes were
  unaffected. The AppImage is now covered by an end-to-end frame-quality check.

## [1.1.1] - 2026-11-08

### Changed

- Renamed the application ID and project identity to `mdshakibsami`.
- Clarified the tested Ubuntu and Debian releases and the amd64 packaging scope.

### Removed

- Removed the placeholder Buy Me a Coffee link from the app, documentation,
  AppStream metadata and repository configuration.

## [1.1.0] - 2026-11-08

### Added

- Public open-source release with a GitHub release pipeline, issue templates,
  Contributor Covenant, security policy and third-party notices.
- Universal `Architecture: all` `.deb` for Ubuntu 22.04+ and Debian 12+.
- Fully self-contained AppImage built on Ubuntu 22.04, including Python, GTK 4,
  libadwaita and a static **LGPL** FFmpeg 6.1.2 build.
- GTK 4.6 / libadwaita 1.1 compatibility layer with feature detection.
- "Buy Me a Coffee" support action in the application menu.
- Additional metadata, CLI and compatibility tests.

### Changed

- Minimum supported stack is now GTK 4.6 and libadwaita 1.1 (previously
  GTK 4.10 / libadwaita 1.5).
- Version is single-sourced from `resolve_ready.__version__`.
- The AppImage uses the cairo renderer and disables host EGL vendors, avoiding
  crashes caused by mixing bundled and host GPU drivers.
- The AppImage no longer bundles Ubuntu's GPL ffmpeg or its large graphics
  dependency stack.

### Fixed

- Duplicate `fps` suffix when displaying fractional frame rates.
- Dialog and toolbar fallbacks on Ubuntu 22.04 / Debian 12.
- Missing image and icon decoding in the AppImage on minimal systems.
- Headless `--version` no longer imports GTK.

## [1.0.x]

Earlier internal builds. They supported GTK 4.10+ only and are superseded by
1.1.0.

[1.1.2]: https://github.com/mdshakibsami/resolve-ready/releases/tag/v1.1.2
[1.1.1]: https://github.com/mdshakibsami/resolve-ready/releases/tag/v1.1.1
[1.1.0]: https://github.com/mdshakibsami/resolve-ready/releases/tag/v1.1.0
