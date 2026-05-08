# Changelog

## v2.0.1
- Fix major UI freeze risk by removing synchronous network cover fetch from the UI thread.
- Add incremental game-card rendering in batches to keep the window responsive on large libraries.
- Improve cover fallback state when VNDB image cache is not ready (`等待缓存` placeholder).

## v2.0.0
- Switch to VNDB-first metadata import workflow with no-auth public API access.
- Add 6-thread VNDB batch import in UI with progress, cancellation, and result summary dialog.
- Extend database schema for VNDB metadata fields and add transactional `upsert_games_batch`.
- Support VNDB cover CDN integration with local cache and improved cover source labeling.
- Upgrade cover rendering with consistent ratio handling, centered crop strategy, and unified placeholders.
- Improve startup robustness and diagnostics; simplify single-instance behavior for stability.
- Add CLI VNDB import mode (`--vndb-import`, `--threads`) with structured summary output.
- Add plugin architecture for scan-result transformation (builtin + external plugins).
- Refine scanner exclusions to avoid importing project/build/dev folders as games.
- Update docs for VNDB-only workflow, operational limits, and plugin extension guide.

## v1.0.1
- Improve scanner accuracy for nested Galgame directory structures.
- Add scan-root management dialog (add/remove/clear) in UI.
- Support custom game name/start path overrides with higher priority than auto-scan.
- Fix desktop shortcut creation by generating Windows `.lnk` shortcuts with fallback.
- Exclude Local-Galgame-Manager project/build folders from scan results.
- Clear game library data when all scan roots are removed.

## v1.0.0
- Bootstrap project structure.
- Implement scanning/import and launcher foundations.
- Add UI shell, tray behavior, search/filter, backup/restore.
