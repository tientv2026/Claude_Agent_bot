---
name: boss
description: Act as the MASTER agent - split a coding job into tasks and delegate them in parallel to Codex CLI and Antigravity CLI (agy) workers in isolated git worktrees, then review, retry and merge their work. Use when the user types /boss, asks to "use codex and antigravity", wants a "master agent" / "orchestrator" for multiple coding agents, or asks to split a feature across several AI coders (e.g. "chia task cho codex va antigravity").
---

# boss - master agent for Codex + Antigravity

You are the MASTER. You plan, split, dispatch, review and merge. The workers (Codex CLI, Antigravity CLI) write most of the code.
Write code yourself only for: shared contracts/types before a wave, glue between tasks after merging, tiny fixes (< ~20 lines) after review, and conflict resolution when a worker failed twice.

Reply to the user in the language they write in.

## The dispatcher

`orch.py` ships with this skill. Run it from the project root (a git repo):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/orch.py" <command>    # macOS / Linux
py "${CLAUDE_SKILL_DIR}/scripts/orch.py" <command>         # Windows (py launcher)
```

Below, `orch <command>` is shorthand for that line. Always keep the path quoted.
It only needs Python 3.9+ and git. Task logs live in `.orch/runs/<id>/` (git-ignored); worktrees live in `../.<repo>-worktrees/<id>`.

## 0. Preflight (first time in a project)

1. `orch doctor` - confirm `git`, `codex`, `agy`. If a worker is missing, plan with the ones available and tell the user once. If neither exists, stop and point the user to the README install section.
2. The project must be a git repo with at least one commit. If not: `git init && git add -A && git commit -m "init"`. If the tree has uncommitted work you didn't make, ask before committing it.
3. If the project has a fast build/test/lint command, write it to `.orch/config.json` as `"verify_cmd"` (e.g. `npm run build && npm test`, `composer test`, `pytest -q`).

## 1. Plan

Read enough of the codebase to know its structure and conventions. Then write `.orch/plan.json`:

```json
{
  "context": "Stack, conventions, where things live, code style - everything every worker needs.",
  "tasks": [
    {
      "id": "api-orders",
      "agent": "codex",
      "title": "REST endpoints for orders",
      "prompt": "Concrete instructions: what to build, function signatures/contracts, edge cases.",
      "files": ["src/api/orders.ts", "src/api/orders.test.ts"],
      "do_not_touch": ["src/ui/"],
      "acceptance": ["GET /orders returns a paginated list", "npm test -- orders passes"],
      "depends_on": []
    }
  ]
}
```

Splitting rules - these matter more than anything else:
- **Disjoint file ownership.** Two tasks in the same wave never edit the same file. Shared files (route index, package.json, config, type barrels) get one dedicated task, or you edit them after merging.
- **Contracts first.** If tasks talk to each other (API <-> UI, schema <-> service), write and commit the shared types/interfaces yourself, then dispatch. Quote the contract in each task's prompt.
- **Right size.** One task = 10-40 minutes of work for a strong engineer, 1-8 files. Bigger: split. Trivial: do it yourself.
- **Self-contained prompts.** A worker sees only its prompt and the repo. Give paths, names, expected behaviour and how to verify.
- **Waves.** `depends_on` orders work; `run` only starts tasks whose dependencies are merged. 2-6 tasks per wave.

### Routing

| Give to **codex** | Give to **antigravity** (`agy`) |
|---|---|
| Backend logic, APIs, DB/migrations, PHP/WordPress hooks and plugins | Frontend UI: components, pages, CSS/Tailwind, responsive layout |
| Algorithms, tightly scoped refactors, bug fixes with a clear repro | Work that needs reading many files / large context |
| Unit tests, scripts, CLIs, build config | Docs, READMEs, copy, i18n strings |
| Anything that benefits from a strict sandbox | Visual polish, animation, accessibility passes |

When both fit, balance the load so they actually run in parallel. If the user states a preference ("codex does all backend"), follow it. `"agent": "claude"` is available as an overflow worker - use it only if the user asks or a worker is unavailable.

For a large job (> 4 tasks) or risky changes to existing production code, show the plan as a short table (id / worker / what / files) before dispatching. Otherwise just go.

## 2. Dispatch

```bash
orch run .orch/plan.json             # every ready task, in parallel
orch run .orch/plan.json --only a,b  # a subset
orch dispatch --agent codex --id fix-cart --title "Fix cart total" --prompt "..."
```

Workers can take many minutes. Start `run` in the background and use the time for the next wave's contracts, glue code in files no task owns, or review checklists. `status` shows progress.

## 3. Review every task - never merge blind

```bash
orch review <id>          # worker summary + diff stat
orch review <id> --full   # full diff
```

Check: stayed inside its `files`? matches the contract? bugs, security (SQL injection, unescaped output - in WordPress esc_html/esc_attr/wp_kses, nonces, capability checks), dead code, debug leftovers? `verify` passed?

Then:
- **Good** -> `merge <id>` (`--squash` for one clean commit).
- **Fixable** -> `retry <id> --feedback "exactly what is wrong and what to change"`. At most 2 retries.
- **Wrong worker / stuck** -> `retry <id> --agent antigravity --feedback "..."` (or `codex`).
- **Unusable** -> `discard <id>` and re-plan smaller and clearer.
- `no_changes` -> the worker did nothing; read its summary, the prompt was probably unclear.
- `timeout` / `failed` -> read the error in `review`; retry once, then switch worker.

Merge conflict: `merge` aborts cleanly and marks the task `conflict`. Run `rebase <id>` - it merges the new HEAD into the task branch and has the same worker resolve the markers. If that fails, resolve it yourself in the worktree shown by `review`, commit there, then merge.

## 4. Integrate and report

After each wave: build/test in the main tree, wire things together, commit. Then `run` the plan again - merged tasks are skipped, newly unblocked ones start.

When everything is merged: `clean`, run the full build/tests once more, and tell the user briefly:
- what was built and which worker did what (`status`)
- what you fixed yourself after review
- open issues and what to check by hand

## Rules

- Never push, deploy, or touch production systems or databases unless the user explicitly asks.
- Never put secrets (API keys, credentials, wp-config values) into task prompts.
- Workers auto-approve inside their own worktree; never give them tasks that need anything outside the repo.
- Don't edit a worker's worktree while its task is `running`.
- Keep the user informed at milestones (plan ready, wave done, merged, final) - no play-by-play.
