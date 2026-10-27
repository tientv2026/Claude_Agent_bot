#!/usr/bin/env python3
"""
orch.py - dispatcher used by a master agent (Claude Code) to drive
Codex CLI and Antigravity CLI (agy) as parallel coding workers.

Each task runs in its own git worktree (branch orch/<id>), so workers never
step on each other. The master reviews each diff, then merges it.

Commands:
  doctor [--live]                check git / codex / agy / claude (and call them once)
  dispatch --agent A --id ID (--task-file F | --prompt "...")
  run PLAN.json [--only a,b]     run every ready task in parallel (respects depends_on)
  status [--json]                status of all tasks
  review ID [--full]             worker summary + diff stat (+ full diff)
  retry ID --feedback "..."      re-run in the same worktree with master feedback
  merge ID [--squash]            merge the task branch into the current branch
  rebase ID                      bring the task branch up to HEAD; worker fixes conflicts
  discard ID                     drop task, delete worktree + branch
  clean [--all]                  remove worktrees of merged/discarded tasks

Pure standard library, Python 3.9+. Works on Linux, macOS and Windows.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

VERSION = "1.1.0"
LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "agents": {
        "codex": {
            "bin": "codex",
            "model": None,
            # "auto": workspace-write sandbox, no prompts; "yolo": no sandbox at all
            "permission": "auto",
            "extra_args": [],
            "max_parallel": 2,
            "timeout_min": 30,
        },
        "antigravity": {
            "bin": "agy",
            "model": None,
            "effort": None,
            # "auto": --dangerously-skip-permissions (contained: runs in its own worktree)
            # "ask":  rely on permissions.allow in ~/.gemini/antigravity-cli/settings.json
            "permission": "auto",
            "extra_args": [],
            "max_parallel": 2,
            "timeout_min": 30,
        },
        "claude": {
            "bin": "claude",
            "model": None,
            "permission": "auto",
            "extra_args": [],
            "max_parallel": 2,
            "timeout_min": 30,
        },
    },
    # Command run inside the worktree after a worker finishes. Empty = skip.
    "verify_cmd": "",
    "worktree_root": None,  # default: <parent dir>/.<repo-name>-worktrees
}

AGENT_ALIASES = {"agy": "antigravity", "gemini": "antigravity", "ag": "antigravity", "cx": "codex"}

WORKER_PREAMBLE = """You are a WORKER agent dispatched by a master orchestrator.
You are working in an isolated git worktree of the project: {wt}
Rules:
- Implement ONLY the task below. Stay inside the files/areas listed under "Scope". Do not refactor unrelated code.
- Do NOT run `git commit`, `git push`, `git checkout` or change branches. The orchestrator commits for you.
- Do not install new dependencies unless the task explicitly allows it.
- If something is ambiguous, make the most reasonable choice and note it in your final summary.
- If you can run tests/lint/build for what you changed, do so and fix failures.
- Finish with a short summary in this exact format:
  ## SUMMARY
  - Changed: <files>
  - How to verify: <commands or steps>
  - Notes/risks: <anything the master should know>

=== TASK [{id}] {title} ===
{body}
"""


# ----------------------------------------------------------------- helpers
def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def sh(cmd, cwd=None, check=True, capture=True):
    r = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"$ {' '.join(map(str, cmd))}\n{r.stdout}\n{r.stderr}")
    return r


def git(*args, cwd=None, check=True):
    return sh(["git", *args], cwd=cwd, check=check).stdout.strip()


def repo_root() -> Path:
    try:
        return Path(git("rev-parse", "--show-toplevel"))
    except Exception:
        die("Not inside a git repo. Run `git init` and make a first commit.")


def die(msg, code=1):
    print(f"[orch] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg):
    with LOCK:
        print(f"[orch {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s.strip()).strip("-").lower()
    if not s:
        die("empty task id")
    return s[:60]


def norm_agent(a: str) -> str:
    a = a.lower().strip()
    a = AGENT_ALIASES.get(a, a)
    if a not in DEFAULT_CONFIG["agents"]:
        die(f"unknown agent: {a} (codex | antigravity | claude)")
    return a


class Ctx:
    def __init__(self):
        self.root = repo_root()
        self.state = self.root / ".orch"
        self.runs = self.state / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self._exclude_state_dir()
        self.cfg = self._load_cfg()
        wr = self.cfg.get("worktree_root")
        self.wt_root = Path(wr) if wr else self.root.parent / f".{self.root.name}-worktrees"

    def _exclude_state_dir(self):
        try:
            gd = Path(git("rev-parse", "--git-common-dir", cwd=self.root))
            if not gd.is_absolute():
                gd = self.root / gd
            ex = gd / "info" / "exclude"
            ex.parent.mkdir(parents=True, exist_ok=True)
            txt = ex.read_text(encoding="utf-8") if ex.exists() else ""
            if ".orch/" not in txt.splitlines():
                with ex.open("a", encoding="utf-8") as f:
                    f.write(("\n" if txt and not txt.endswith("\n") else "") + ".orch/\n")
        except Exception:
            pass

    def _load_cfg(self):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        for p in (Path.home() / ".orch.json", self.state / "config.json"):
            if p.exists():
                try:
                    user = json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:
                    die(f"bad config {p}: {e}")
                for k, v in user.items():
                    if k == "agents":
                        for a, av in v.items():
                            cfg["agents"].setdefault(a, {}).update(av)
                    else:
                        cfg[k] = v
        return cfg

    # ---- per-task metadata
    def run_dir(self, tid):
        return self.runs / tid

    def meta(self, tid):
        p = self.run_dir(tid) / "meta.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def save_meta(self, tid, m):
        d = self.run_dir(tid)
        d.mkdir(parents=True, exist_ok=True)
        with LOCK:
            (d / "meta.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")

    def all_meta(self):
        out = []
        for d in sorted(self.runs.iterdir()) if self.runs.exists() else []:
            m = self.meta(d.name)
            if m:
                out.append(m)
        return out


# ----------------------------------------------------------------- worktree
def ensure_worktree(ctx: Ctx, tid: str, base: str) -> Path:
    wt = ctx.wt_root / tid
    branch = f"orch/{tid}"
    if wt.exists() and (wt / ".git").exists():
        return wt
    ctx.wt_root.mkdir(parents=True, exist_ok=True)
    exists = sh(["git", "rev-parse", "--verify", "--quiet", branch], cwd=ctx.root, check=False).returncode == 0
    if exists:
        git("worktree", "add", str(wt), branch, cwd=ctx.root)
    else:
        git("worktree", "add", "-b", branch, str(wt), base, cwd=ctx.root)
    return wt


def remove_worktree(ctx: Ctx, tid: str, delete_branch=True):
    wt = ctx.wt_root / tid
    if wt.exists():
        sh(["git", "worktree", "remove", "--force", str(wt)], cwd=ctx.root, check=False)
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
    sh(["git", "worktree", "prune"], cwd=ctx.root, check=False)
    if delete_branch:
        sh(["git", "branch", "-D", f"orch/{tid}"], cwd=ctx.root, check=False)


# ----------------------------------------------------------------- workers
def _new_group():
    """Start workers in their own process group so a timeout can kill the whole tree."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_tree(p: subprocess.Popen):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        p.kill()
        p.wait(timeout=10)
    except Exception:
        pass


def resolve_bin(name):
    p = shutil.which(name)
    if not p:
        raise FileNotFoundError(f"'{name}' not found in PATH")
    return p


def build_cmd(agent, acfg, prompt, wt: Path, rdir: Path):
    """Tra ve (cmd, stdin_text)."""
    b = resolve_bin(acfg["bin"])
    perm = acfg.get("permission", "auto")
    extra = list(acfg.get("extra_args") or [])
    if agent == "codex":
        cmd = [b, "exec", "--skip-git-repo-check", "-C", str(wt), "--json",
               "-o", str(rdir / "last_message.txt")]
        cmd += ["--dangerously-bypass-approvals-and-sandbox"] if perm == "yolo" else ["--full-auto"]
        if acfg.get("model"):
            cmd += ["-m", acfg["model"]]
        cmd += extra + ["-"]  # prompt tu stdin
        return cmd, prompt
    if agent == "antigravity":
        # prompt via stdin (stream-json): survives multi-line prompts and .cmd shims on Windows
        cmd = [b, "--input-format", "stream-json", "--output-format", "stream-json"]
        if perm in ("auto", "yolo"):
            cmd.append("--dangerously-skip-permissions")
        if acfg.get("model"):
            cmd += ["--model", acfg["model"]]
        if acfg.get("effort"):
            cmd += ["--effort", acfg["effort"]]
        msg = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
        return cmd + extra, msg
    if agent == "claude":
        cmd = [b, "-p", "--output-format", "json"]
        cmd += ["--dangerously-skip-permissions"] if perm == "yolo" else ["--permission-mode", "acceptEdits"]
        if acfg.get("model"):
            cmd += ["--model", acfg["model"]]
        return cmd + extra, prompt
    raise ValueError(agent)


def extract_summary(agent, rdir: Path, stdout: str) -> str:
    if agent == "codex":
        p = rdir / "last_message.txt"
        if p.exists() and p.read_text(encoding="utf-8", errors="replace").strip():
            return p.read_text(encoding="utf-8", errors="replace").strip()
        # fallback: last agent message in the JSONL stream
        last = ""
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            item = ev.get("item") or ev.get("msg") or {}
            if isinstance(item, dict) and item.get("type") in ("agent_message", "assistant_message"):
                last = item.get("text") or item.get("message") or last
        return last.strip()
    if agent == "antigravity":
        res = None
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("event") == "result":
                res = ev.get("result") or {}
        if res is not None:
            if res.get("status") != "SUCCESS":
                return f"[status={res.get('status')}] {res.get('error','')}\n{res.get('response','')}".strip()
            return (res.get("response") or "").strip()
    # claude (or agy returning a single json envelope)
    txt = stdout.strip()
    for cand in (txt, txt.splitlines()[-1] if txt else ""):
        try:
            env = json.loads(cand)
            if agent == "antigravity":
                if env.get("status") not in (None, "SUCCESS"):
                    return f"[status={env.get('status')}] {env.get('error','')}\n{env.get('response','')}".strip()
                return (env.get("response") or "").strip()
            return (env.get("result") or "").strip()
        except Exception:
            continue
    return txt[-4000:]


def run_worker(ctx: Ctx, tid: str, prompt_body: str, agent: str, title: str,
               base: str | None = None, attempt_note: str | None = None) -> dict:
    agent = norm_agent(agent)
    acfg = ctx.cfg["agents"][agent]
    rdir = ctx.run_dir(tid)
    rdir.mkdir(parents=True, exist_ok=True)
    m = ctx.meta(tid) or {"id": tid, "agent": agent, "title": title, "attempts": 0,
                          "created": now_iso(), "branch": f"orch/{tid}"}
    if base is None:
        base = m.get("base") or git("rev-parse", "HEAD", cwd=ctx.root)
    m.update(agent=agent, title=title, base=m.get("base") or base, status="running",
             started=now_iso(), finished=None, error=None)
    m["attempts"] = m.get("attempts", 0) + 1
    ctx.save_meta(tid, m)
    (rdir / "task.md").write_text(prompt_body, encoding="utf-8")

    try:
        wt = ensure_worktree(ctx, tid, m["base"])
    except Exception as e:
        m.update(status="failed", error=f"worktree: {e}", finished=now_iso())
        ctx.save_meta(tid, m)
        log(f"{tid}: could not create worktree: {e}")
        return m
    m["worktree"] = str(wt)

    body = prompt_body
    if attempt_note:
        body += f"\n\n=== FEEDBACK FROM MASTER (attempt {m['attempts']}) ===\n{attempt_note}\n" \
                "The worktree already contains your previous attempt. Fix it in place."
    prompt = WORKER_PREAMBLE.format(wt=wt, id=tid, title=title, body=body)
    (rdir / f"prompt.{m['attempts']}.md").write_text(prompt, encoding="utf-8")

    try:
        cmd, stdin_text = build_cmd(agent, acfg, prompt, wt, rdir)
    except Exception as e:
        m.update(status="failed", error=str(e), finished=now_iso())
        ctx.save_meta(tid, m)
        log(f"{tid}: {e}")
        return m

    timeout_s = int(acfg.get("timeout_s") or int(acfg.get("timeout_min", 30)) * 60 + 60)
    log(f"{tid}: -> {agent} (attempt {m['attempts']}, timeout {timeout_s//60}m) @ {wt}")
    t0 = time.time()
    out_p, err_p = rdir / "stdout.log", rdir / "stderr.log"
    status, rc = "done", None
    env = dict(os.environ, ORCH_TASK_ID=tid, NO_COLOR="1")
    with out_p.open("w", encoding="utf-8") as fo, err_p.open("w", encoding="utf-8") as fe:
        try:
            p = subprocess.Popen(cmd, cwd=wt, text=True, encoding="utf-8", errors="replace",
                                 stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                 stdout=fo, stderr=fe, env=env, **_new_group())
            if stdin_text is not None:
                try:
                    p.stdin.write(stdin_text)
                    p.stdin.close()
                except BrokenPipeError:
                    pass
            rc = p.wait(timeout=timeout_s)
            if rc != 0:
                status = "failed"
        except subprocess.TimeoutExpired:
            _kill_tree(p)
            status, rc = "timeout", -1
        except Exception as e:
            status = "failed"
            fe.write(f"\n[orch] {e}\n")
    dur = round(time.time() - t0, 1)
    stdout = out_p.read_text(encoding="utf-8", errors="replace")
    summary = extract_summary(agent, rdir, stdout)
    (rdir / "summary.md").write_text(summary or "(worker returned no summary)", encoding="utf-8")
    if agent == "antigravity" and status == "done" and summary.startswith("[status="):
        status = "failed"

    # commit whatever the worker changed
    sh(["git", "add", "-A"], cwd=wt, check=False)
    changed = git("diff", "--cached", "--name-only", cwd=wt, check=False).splitlines()
    if changed:
        msg = f"orch({agent}): {title} [{tid}] attempt {m['attempts']}"
        sh(["git", "-c", "user.name=orch-" + agent, "-c", "user.email=orch@local",
            "commit", "-q", "--no-verify", "-m", msg], cwd=wt, check=False)
    all_changed = git("diff", "--name-only", f"{m['base']}..HEAD", cwd=wt, check=False).splitlines()

    if status == "done" and not all_changed:
        status = "no_changes"

    # verify
    vcmd = ctx.cfg.get("verify_cmd")
    if vcmd and status == "done":
        vr = subprocess.run(vcmd, shell=True, cwd=wt, text=True, capture_output=True,
                            encoding="utf-8", errors="replace")
        (rdir / "verify.log").write_text(vr.stdout + "\n" + vr.stderr, encoding="utf-8")
        m["verify"] = "pass" if vr.returncode == 0 else "fail"
        if vr.returncode != 0:
            status = "verify_failed"

    m.update(status=status, exit_code=rc, duration_s=dur, finished=now_iso(),
             files_changed=all_changed)
    if status in ("failed", "timeout"):
        m["error"] = err_p.read_text(encoding="utf-8", errors="replace")[-1500:]
    ctx.save_meta(tid, m)
    log(f"{tid}: {status} ({dur}s, {len(all_changed)} files)")
    return m


# ----------------------------------------------------------------- commands
def cmd_doctor(args):
    ok = True
    print(f"orch {VERSION}  python {sys.version.split()[0]}  os={sys.platform}")
    for name, ver in (("git", ["--version"]), ("codex", ["--version"]),
                      ("agy", ["--version"]), ("claude", ["--version"])):
        p = shutil.which(name)
        if not p:
            print(f"  [--] {name:7} not in PATH")
            if name in ("git",):
                ok = False
            continue
        try:
            r = subprocess.run([p, *ver], capture_output=True, text=True, timeout=30)
            print(f"  [ok] {name:7} {(r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else ''}  ({p})")
        except Exception as e:
            print(f"  [!!] {name:7} error: {e}")
    if args.live:
        print("\nLive headless call (read-only):")
        ask = "Reply with exactly: PONG"
        # exercise the same invocation path real dispatches use (prompt via stdin)
        tests = {
            "codex": ([shutil.which("codex") or "codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-"], ask),
            "agy": ([shutil.which("agy") or "agy", "--input-format", "stream-json", "--output-format", "stream-json"],
                    json.dumps({"event": "user", "message": {"content": ask}}) + "\n"),
        }
        for n, (c, stdin_text) in tests.items():
            if not shutil.which(n):
                continue
            t0 = time.time()
            try:
                r = subprocess.run(c, capture_output=True, text=True, timeout=180,
                                   input=stdin_text, encoding="utf-8", errors="replace")
                good = "PONG" in (r.stdout or "")
                print(f"  [{'ok' if good else '!!'}] {n}: rc={r.returncode} {time.time()-t0:.0f}s"
                      + ("" if good else f"\n      stdout: {r.stdout[-300:]!r}\n      stderr: {r.stderr[-300:]!r}"))
            except subprocess.TimeoutExpired:
                print(f"  [!!] {n}: hung >180s without a TTY (see README > Troubleshooting).")
    sys.exit(0 if ok else 1)


def _read_task_body(args):
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    if not sys.stdin.isatty():
        return sys.stdin.read()
    die("need --task-file or --prompt")


def cmd_dispatch(args):
    ctx = Ctx()
    tid = slug(args.id)
    m = ctx.meta(tid)
    if m and m.get("status") == "running":
        die(f"{tid} is running")
    if m and m.get("status") == "merged":
        die(f"{tid} already merged; use another id")
    body = _read_task_body(args)
    res = run_worker(ctx, tid, body, args.agent, args.title or tid, base=args.base)
    print(json.dumps(_brief(res), ensure_ascii=False, indent=2))


def _task_body_from_plan(t):
    parts = [t.get("prompt") or t.get("description") or ""]
    if t.get("files"):
        parts.append("Scope (files/dirs you own): " + ", ".join(t["files"]))
    if t.get("do_not_touch"):
        parts.append("Do NOT modify: " + ", ".join(t["do_not_touch"]))
    if t.get("acceptance"):
        acc = t["acceptance"] if isinstance(t["acceptance"], list) else [t["acceptance"]]
        parts.append("Acceptance criteria:\n" + "\n".join(f"- {a}" for a in acc))
    if t.get("context"):
        parts.append("Context:\n" + t["context"])
    return "\n\n".join(p for p in parts if p)


def cmd_run(args):
    ctx = Ctx()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    tasks = plan["tasks"] if isinstance(plan, dict) else plan
    only = set(slug(x) for x in args.only.split(",")) if args.only else None
    shared = plan.get("context", "") if isinstance(plan, dict) else ""

    # warn when two tasks in the same plan own the same file
    seen = {}
    for t in tasks:
        for f in t.get("files", []):
            if f in seen:
                log(f"WARNING: '{f}' is owned by both {seen[f]} and {t['id']} -> likely merge conflict")
            seen[f] = t["id"]

    runnable, skipped = [], []
    for t in tasks:
        tid = slug(t["id"])
        if only and tid not in only:
            continue
        m = ctx.meta(tid)
        if m and m.get("status") in ("merged", "running"):
            continue
        if m and m.get("status") in ("done", "no_changes") and not args.force:
            skipped.append((tid, f"already {m['status']} (use --force to re-run)"))
            continue
        deps = [slug(d) for d in t.get("depends_on", [])]
        unmet = [d for d in deps if (ctx.meta(d) or {}).get("status") != "merged"]
        if unmet:
            skipped.append((tid, f"waiting for merge of: {', '.join(unmet)}"))
            continue
        runnable.append(t)

    for tid, why in skipped:
        log(f"skip {tid}: {why}")
    if not runnable:
        log("no runnable task in this wave.")
        return

    dirty = git("status", "--porcelain", cwd=ctx.root)
    if dirty:
        log("WARNING: main working tree has uncommitted changes; workers will NOT see them (worktrees start from HEAD).")

    base = git("rev-parse", "HEAD", cwd=ctx.root)
    sems = {a: threading.Semaphore(int(c.get("max_parallel", 2))) for a, c in ctx.cfg["agents"].items()}

    def job(t):
        agent = norm_agent(t.get("agent", "codex"))
        with sems[agent]:
            body = _task_body_from_plan(t)
            if shared:
                body = f"Project context:\n{shared}\n\n{body}"
            return run_worker(ctx, slug(t["id"]), body, agent, t.get("title", t["id"]), base=base)

    total = sum(int(c.get("max_parallel", 2)) for c in ctx.cfg["agents"].values())
    log(f"running {len(runnable)} tasks in parallel: " + ", ".join(f"{t['id']}->{norm_agent(t.get('agent','codex'))}" for t in runnable))
    results = []
    with cf.ThreadPoolExecutor(max_workers=total) as ex:
        for fut in cf.as_completed([ex.submit(job, t) for t in runnable]):
            results.append(fut.result())
    print("\n=== RESULTS ===")
    print(json.dumps([_brief(r) for r in results], ensure_ascii=False, indent=2))


def _brief(m):
    return {k: m.get(k) for k in ("id", "agent", "status", "attempts", "duration_s",
                                  "files_changed", "verify", "branch", "error") if m.get(k) is not None}


def cmd_status(args):
    ctx = Ctx()
    ms = ctx.all_meta()
    if args.json:
        print(json.dumps([_brief(m) for m in ms], ensure_ascii=False, indent=2))
        return
    if not ms:
        print("(no tasks yet)")
        return
    print(f"{'ID':28} {'AGENT':12} {'STATUS':14} {'TRY':>3} {'FILES':>5}  TITLE")
    for m in ms:
        print(f"{m['id'][:28]:28} {m['agent']:12} {m['status']:14} {m.get('attempts',0):>3} "
              f"{len(m.get('files_changed') or []):>5}  {m.get('title','')[:50]}")


def cmd_review(args):
    ctx = Ctx()
    tid = slug(args.id)
    m = ctx.meta(tid) or die(f"no such task: {tid}")
    wt = Path(m.get("worktree", ctx.wt_root / tid))
    print(f"# {tid} [{m['agent']}] status={m['status']} attempts={m.get('attempts')}")
    print(f"branch {m['branch']}  base {m['base'][:10]}  worktree {wt}\n")
    s = ctx.run_dir(tid) / "summary.md"
    print("## Worker summary\n" + (s.read_text(encoding="utf-8") if s.exists() else "(none)") + "\n")
    if m.get("verify"):
        print(f"## Verify: {m['verify']}  (log: {ctx.run_dir(tid)/'verify.log'})\n")
    if m.get("error"):
        print("## Error (tail)\n" + m["error"] + "\n")
    print("## Diff stat")
    print(git("diff", "--stat", f"{m['base']}..{m['branch']}", cwd=ctx.root, check=False))
    if args.full:
        print("\n## Diff")
        print(git("diff", f"{m['base']}..{m['branch']}", cwd=ctx.root, check=False))


def cmd_retry(args):
    ctx = Ctx()
    tid = slug(args.id)
    m = ctx.meta(tid) or die(f"no such task: {tid}")
    if m["status"] in ("merged", "running"):
        die(f"{tid} is {m['status']}")
    body = (ctx.run_dir(tid) / "task.md").read_text(encoding="utf-8")
    agent = args.agent or m["agent"]
    res = run_worker(ctx, tid, body, agent, m.get("title", tid), attempt_note=args.feedback)
    print(json.dumps(_brief(res), ensure_ascii=False, indent=2))


def cmd_merge(args):
    ctx = Ctx()
    tid = slug(args.id)
    m = ctx.meta(tid) or die(f"no such task: {tid}")
    if m["status"] == "merged":
        die("already merged")
    if m["status"] == "running":
        die("task is running")
    if git("status", "--porcelain", "--untracked-files=no", cwd=ctx.root):
        die("main working tree has uncommitted changes; commit or stash before merging.")
    br = m["branch"]
    if not git("log", "--oneline", f"HEAD..{br}", cwd=ctx.root, check=False):
        die(f"{br} has no new commits relative to HEAD")
    if args.squash:
        r = sh(["git", "merge", "--squash", br], cwd=ctx.root, check=False)
        if r.returncode == 0:
            r = sh(["git", "commit", "-q", "-m", f"{m.get('title', tid)} [{tid}, by {m['agent']}]"],
                   cwd=ctx.root, check=False)
    else:
        r = sh(["git", "merge", "--no-ff", "-m", f"merge {tid} ({m['agent']}): {m.get('title','')}", br],
               cwd=ctx.root, check=False)
    if r.returncode != 0:
        conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=ctx.root, check=False)
        sh(["git", "merge", "--abort"], cwd=ctx.root, check=False)
        sh(["git", "reset", "-q", "--merge"], cwd=ctx.root, check=False)
        m["status"] = "conflict"
        m["conflicts"] = conflicts.splitlines()
        ctx.save_meta(tid, m)
        die(f"CONFLICT merging {tid}: {conflicts or r.stderr.strip()}\n"
            f"Hint: `orch.py rebase {tid}` lets the worker resolve it on the new HEAD, or resolve it by hand.", 2)
    m.update(status="merged", merged_at=now_iso(), merged_into=git("rev-parse", "HEAD", cwd=ctx.root))
    ctx.save_meta(tid, m)
    if not args.keep:
        remove_worktree(ctx, tid)
    log(f"{tid}: merged into {git('branch', '--show-current', cwd=ctx.root)}")


def cmd_rebase(args):
    """Merge current HEAD into the task branch; on conflict, ask the worker to resolve it."""
    ctx = Ctx()
    tid = slug(args.id)
    m = ctx.meta(tid) or die(f"no such task: {tid}")
    wt = Path(m["worktree"])
    head = git("rev-parse", "HEAD", cwd=ctx.root)
    r = sh(["git", "-c", "user.name=orch", "-c", "user.email=orch@local", "merge", "--no-edit", head],
           cwd=wt, check=False)
    if r.returncode == 0:
        m.update(status="done", base=head)
        ctx.save_meta(tid, m)
        log(f"{tid}: updated to HEAD, no conflicts. Ready to merge.")
        return
    files = git("diff", "--name-only", "--diff-filter=U", cwd=wt, check=False)
    note = (f"The branch was merged with the latest main and has CONFLICTS in: {files}. "
            "Resolve every conflict marker (<<<<<<< ======= >>>>>>>) keeping BOTH sides' intent, "
            "make sure it builds, and do not touch other files.")
    m["base"] = head
    ctx.save_meta(tid, m)
    body = (ctx.run_dir(tid) / "task.md").read_text(encoding="utf-8")
    res = run_worker(ctx, tid, body, m["agent"], m.get("title", tid), attempt_note=note)
    left = sh(["git", "grep", "-l", "-E", "^(<<<<<<<|>>>>>>>) "], cwd=wt, check=False).stdout.strip()
    if left:
        res["status"] = "conflict"
        ctx.save_meta(tid, res)
        die(f"conflict markers still present in: {left}", 2)
    print(json.dumps(_brief(res), ensure_ascii=False, indent=2))


def cmd_discard(args):
    ctx = Ctx()
    tid = slug(args.id)
    m = ctx.meta(tid) or die(f"no such task: {tid}")
    remove_worktree(ctx, tid)
    m["status"] = "discarded"
    ctx.save_meta(tid, m)
    log(f"{tid}: discarded")


def cmd_clean(args):
    ctx = Ctx()
    n = 0
    for m in ctx.all_meta():
        if m["status"] in ("merged", "discarded") or args.all:
            remove_worktree(ctx, m["id"])
            if args.all:
                shutil.rmtree(ctx.run_dir(m["id"]), ignore_errors=True)
            n += 1
    log(f"cleaned {n} tasks")


def _utf8_stdio():
    # Windows pipes default to the ANSI code page (cp1252/cp1258); worker summaries are often non-ASCII.
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _utf8_stdio()
    ap = argparse.ArgumentParser(prog="orch", description="Master-agent dispatcher: Codex + Antigravity")
    ap.add_argument("--version", action="version", version=f"agent-boss orch {VERSION}")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("doctor"); p.add_argument("--live", action="store_true", help="really call codex/agy once")
    p.set_defaults(fn=cmd_doctor)

    p = sp.add_parser("dispatch")
    p.add_argument("--agent", required=True); p.add_argument("--id", required=True)
    p.add_argument("--title"); p.add_argument("--task-file"); p.add_argument("--prompt")
    p.add_argument("--base", help="base commit/branch (default HEAD)")
    p.set_defaults(fn=cmd_dispatch)

    p = sp.add_parser("run"); p.add_argument("plan"); p.add_argument("--only")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_run)

    p = sp.add_parser("status"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_status)

    p = sp.add_parser("review"); p.add_argument("id"); p.add_argument("--full", action="store_true")
    p.set_defaults(fn=cmd_review)

    p = sp.add_parser("retry"); p.add_argument("id"); p.add_argument("--feedback", required=True)
    p.add_argument("--agent", help="hand the task to another agent"); p.set_defaults(fn=cmd_retry)

    p = sp.add_parser("merge"); p.add_argument("id"); p.add_argument("--squash", action="store_true")
    p.add_argument("--keep", action="store_true", help="keep the worktree"); p.set_defaults(fn=cmd_merge)

    p = sp.add_parser("rebase"); p.add_argument("id"); p.set_defaults(fn=cmd_rebase)
    p = sp.add_parser("discard"); p.add_argument("id"); p.set_defaults(fn=cmd_discard)
    p = sp.add_parser("clean"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_clean)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
