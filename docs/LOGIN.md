# Signing in to Codex and Antigravity

[Tiếng Việt](LOGIN.vi.md)

`/boss` runs Codex and Antigravity headless, so there is no window where they could ask you to sign in. **Sign in to each one once, interactively.** Your credentials are cached on your machine and reused from then on.

Run these in PowerShell (Windows) or a terminal (macOS/Linux). If you just installed a tool, **open a new terminal** first.

## 1. Codex

**Usual way: your ChatGPT account**

```
codex login            # opens the browser; sign in and approve
codex login status     # shows the account, or "Not logged in"
```

**No browser on this machine** (SSH, server, or the browser doesn't open):

```
codex login --device-auth
```

Open the printed link on any device, enter the code and sign in.

**API key instead of a ChatGPT plan** (billed at API rates):

```powershell
$env:OPENAI_API_KEY | codex login --with-api-key      # Windows PowerShell
```
```bash
printenv OPENAI_API_KEY | codex login --with-api-key  # macOS / Linux
```

Sign out with `codex logout`.

## 2. Antigravity (`agy`)

**Usual way: your Google account**

```
agy
```

The first run opens a Google sign-in page in your browser. Approve it, come back to the terminal, then type `/exit`. From now on `agy` signs in silently from the saved session. If `agy` opens straight into chat without a browser, you're already signed in.

**No browser on this machine (SSH):** run `agy`, open the printed URL on your own machine, sign in, and paste the code it shows back into the terminal.

**Gemini API key instead:** add `"modelProvider": "gemini"` to `~/.gemini/antigravity-cli/settings.json`, then set `GEMINI_API_KEY` (Windows: `setx GEMINI_API_KEY "AIza..."` and open a new terminal). Setting the key without `modelProvider` has no effect.

Sign out by typing `/logout` inside `agy`.

## 3. Verify both

```powershell
py "$HOME\.claude\skills\boss\scripts\orch.py" doctor --live        # Windows
```
```bash
python3 ~/.claude/skills/boss/scripts/orch.py doctor --live          # macOS / Linux
```

You want to see `[ok] codex: rc=0` and `[ok] agy: rc=0`. Each tool gets one short real prompt and no files are touched.

## Common problems

| Symptom | Fix |
|---|---|
| `codex` / `agy` not recognized | Not installed, or the terminal was opened before installing. Open a new one. |
| `[!!] codex` with 401 / unauthorized | The session expired. Run `codex login` again. |
| `[!!] agy` with `authentication required` | Run `agy` once interactively and sign in. |
| Browser doesn't open | Codex: `codex login --device-auth`. agy: copy the URL it prints. |
| Quota / rate-limit errors | Your plan's usage window is exhausted. Wait, upgrade, or lower `max_parallel`. |
| Switch accounts | `codex logout` then `codex login`. In agy, `/logout`, then run `agy` again. |

> Credentials stay on your machine. Codex keeps them in `~/.codex/` or the OS credential store, and Antigravity keeps them in the OS keyring. `/boss` never reads, copies or sends them. It only invokes `codex` and `agy` the same way you would.
