# Changelog

## 1.1.0 - 2026-10-27

First public release.

- `/boss` skill: Claude Code plans, splits, dispatches, reviews and merges.
- `orch.py` dispatcher (stdlib only): `doctor`, `run`, `dispatch`, `status`, `review`, `retry`, `merge`, `rebase`, `discard`, `clean`.
- Workers: Codex CLI (`codex exec`), Antigravity CLI (`agy`, stream-json over stdin), Claude Code (`claude -p`) as overflow.
- One git worktree + branch per task; dependency waves; per-agent parallelism limits; optional `verify_cmd`.
- Conflict handling: clean abort on merge, `rebase` hands conflicts back to the worker.
- Timeouts kill the whole worker process tree (Windows `.cmd` shims included).
- Installable as a Claude Code plugin or as a plain user skill (PowerShell / bash one-liners).
- Test-suite with fake workers, CI on Linux, macOS and Windows.
