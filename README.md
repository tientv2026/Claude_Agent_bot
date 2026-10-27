# agent-boss

**Claude Code is the boss. Codex and Antigravity do the coding, side by side.**

[Tiếng Việt](README.vi.md)

Type `/boss <what to build>` in Claude Code. Claude reads your repo, splits the job into tasks with clear file ownership, and hands them to **Codex CLI** and **Antigravity CLI** (`agy`) to run in parallel. Each task runs in its own git worktree. Claude then reviews every diff, sends work back with feedback if it isn't right, and merges what passes.

```
                 you: /boss add an orders page with filters
                                   │
                     Claude Code (master: plan · review · merge)
                                   │  .orch/plan.json
                                orch.py
                 ┌─────────────────┼──────────────────┐
         codex exec          agy (stream-json)     claude -p (overflow)
        worktree orch/api    worktree orch/ui      worktree orch/…
                 └───── diff ──────┴────── diff ──────┘
                                   │
                  review → retry --feedback / merge / rebase
                                   ▼
                             your branch
```

## Why

- **Parallel**: backend and frontend get built at the same time by two different agents.
- **Safe**: workers never touch your working tree. Every change arrives as a branch, and nothing lands until the master has reviewed it.
- **Uses what you already pay for**: each worker runs on its own subscription (ChatGPT for Codex, Google AI for Antigravity). No API keys go through this tool.
- **No dependencies**: one Python file using only the standard library. Runs on Windows, macOS and Linux.

## Requirements

| | |
|---|---|
| [Claude Code](https://code.claude.com) | the master (CLI or desktop app, **Local** environment) |
| [Codex CLI](https://github.com/openai/codex) | `npm i -g @openai/codex` then `codex login` |
| [Antigravity CLI](https://antigravity.google/docs/getting-started) | install `agy`, then run `agy` once to sign in |
| Git, Python 3.9+ | |

You can run with just one worker. The master plans around whatever `doctor` finds.

New Windows machine? `install/setup-windows.ps1` installs Git, Python, Node and Codex with winget.

## Install

**Option A: Claude Code plugin** (gets updates)

```bash
claude plugin marketplace add tientv2026/Claude_Agent_bot
claude plugin install agent-boss@agent-boss
```

**Option B: user skill, one line**

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/tientv2026/Claude_Agent_bot/main/install/install.sh | bash
```

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/tientv2026/Claude_Agent_bot/main/install/install.ps1 | iex
```

**Check that the workers really respond** (this makes one real headless call to each):

```bash
python3 ~/.claude/skills/boss/scripts/orch.py doctor --live      # Windows: py "$HOME\.claude\skills\boss\scripts\orch.py" doctor --live
```

## Use

Open your project in Claude Code (it must be a git repo) and type:

```
/boss build a contact form: REST endpoint in PHP with rate limiting + responsive Tailwind UI
```

If you installed it as a plugin, the command is `/agent-boss:boss`, or plain `/boss` when no other command has that name.

To steer the routing, just say it: *"codex does the backend, antigravity does all the UI"*.

What happens:

1. **Plan**: Claude writes `.orch/plan.json` with tasks, the worker for each, the files each one owns, acceptance criteria and dependencies (see [examples/plan.example.json](examples/plan.example.json)).
2. **Dispatch**: every ready task starts in parallel, each in `../.<repo>-worktrees/<id>` on its own branch `orch/<id>`.
3. **Review**: Claude reads each diff and the worker's summary, then merges it, retries with precise feedback, or hands it to the other worker.
4. **Waves**: tasks that depend on others start once those are merged.
5. **Report**: what got built, by whom, and what to check by hand.

## Routing defaults

| Codex | Antigravity |
|---|---|
| backend, APIs, DB, PHP/WordPress hooks | UI components, pages, CSS/Tailwind |
| algorithms, scoped refactors, bug fixes | work that needs a large context |
| tests, scripts, build config | docs, copy, i18n, visual polish |

## orch.py commands

Claude calls these itself. You can call them too.

| Command | |
|---|---|
| `doctor [--live]` | check git / codex / agy / claude |
| `run .orch/plan.json [--only a,b] [--force]` | run every ready task in parallel |
| `dispatch --agent codex --id x --prompt "…"` | one-off task (`--task-file` also works) |
| `status [--json]` | table of all tasks |
| `review <id> [--full]` | worker summary + diff |
| `retry <id> --feedback "…" [--agent agy]` | redo in place, optionally with another worker |
| `merge <id> [--squash] [--keep]` | merge into the current branch |
| `rebase <id>` | update the task branch to HEAD; the worker resolves conflicts |
| `discard <id>`, `clean [--all]` | drop a task / remove finished worktrees |

Task statuses: `running`, `done`, `no_changes`, `failed`, `timeout`, `verify_failed`, `conflict`, `merged`, `discarded`.
Logs for each task (prompt, stdout, stderr, summary, verify) are in `.orch/runs/<id>/`. The `.orch/` folder is added to `.git/info/exclude` automatically.

## Configuration

Optional. Put it in `.orch/config.json` (per project) or `~/.orch.json` (global). See [examples/config.example.json](examples/config.example.json).

```json
{
  "verify_cmd": "npm run build && npm test",
  "agents": {
    "codex":       { "model": null, "permission": "auto", "max_parallel": 2, "timeout_min": 30 },
    "antigravity": { "model": "gemini-3.1-pro-high", "effort": "high", "max_parallel": 2 }
  }
}
```

| Key | Meaning |
|---|---|
| `verify_cmd` | runs inside the worktree after each task; failure → `verify_failed` and Claude retries |
| `model`, `effort` | passed through to the worker (`agy models` lists Antigravity's) |
| `max_parallel` | concurrent tasks per worker (each one uses your quota) |
| `timeout_min` | per-task limit; on timeout the whole process tree is killed |
| `permission` | codex: `auto` = `--full-auto` (workspace-write sandbox), `yolo` = no sandbox. agy: `auto` = `--dangerously-skip-permissions`, `ask` = use your `permissions.allow` rules |
| `bin`, `extra_args` | custom binary path / extra flags |

## Security notes

- Workers run **unattended with auto-approval** inside a worktree of your repo. Codex keeps its sandbox by default. Antigravity's `auto` mode approves all of its tool calls, including shell commands. If that is too much, set `"permission": "ask"` for it and whitelist commands in `~/.gemini/antigravity-cli/settings.json`.
- Use it on repos you trust, and keep secrets (`.env`, `wp-config.php`, keys) out of the repo.
- The master never pushes or deploys unless you tell it to.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `agy` task ends in `timeout` with no output | Older `agy` builds could hang without a TTY. Update `agy`. Meanwhile `retry <id> --agent codex`. |
| `agy` → `authentication required` | Run `agy` once interactively and sign in. |
| `codex` sandbox errors on Windows | Run the project inside WSL, or set codex `"permission": "yolo"` (no sandbox). |
| `Python was not found` on Windows | That's the Microsoft Store alias. Install real Python: `winget install -e --id Python.Python.3.12`. |
| merge says `conflict` | `orch.py rebase <id>`, or resolve in the worktree and merge again. |
| task `no_changes` | The prompt was too vague. Check `review <id>`. |

## Development

```bash
python -m unittest discover -s tests -v   # fake workers, no network, ~10s
claude plugin validate .
```

PRs welcome. Adding another worker (Gemini CLI, Aider, …) means one branch in `build_cmd()` plus one in `extract_summary()`.

## License

MIT
