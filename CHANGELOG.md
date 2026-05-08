# Changelog

## v2.0.3
- Fix persistent data reset issue by moving runtime data directory from `Path.cwd()/data` to `%LOCALAPPDATA%/LocalGalgameManager/data`.
- Unify data-dir resolution for both GUI (`app.main`) and CLI (`app.cli`) to ensure consistent library/config loading across launch methods.
- Add best-effort legacy data migration on startup (copy missing entries only, no overwrite) from old working-directory/executable-adjacent `data` folders.
- Improve startup crash dialog to show the actual absolute path of `startup.log`.

## v2.0.2
- Preserve local display names during VNDB imports (avoid forced English title overwrite).
- Stop automatic deletion of unmatched games during scan/VNDB workflow to prevent unexpected library shrink.
- Add `app.feature_selftest` module for one-command functional verification (DB, scanner, plugin, cover, VNDB parse, optional network/UI checks).
- Document self-test usage in README for faster release validation.

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
