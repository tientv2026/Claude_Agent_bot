"""End-to-end tests for orch.py with fake Codex / Antigravity workers.

Run:  python -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "skills" / "boss" / "scripts" / "orch.py"
STUB = ROOT / "tests" / "stubs" / "fake_worker.py"
WIN = os.name == "nt"


def make_bin(bin_dir: Path):
    """Create `codex` and `agy` executables that run the fake worker."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, agent in (("codex", "codex"), ("agy", "antigravity")):
        if WIN:
            (bin_dir / f"{name}.cmd").write_text(
                f'@echo off\r\nset STUB_AGENT={agent}\r\n"{sys.executable}" "{STUB}" %*\r\n', encoding="utf-8")
        else:
            p = bin_dir / name
            p.write_text(f'#!/bin/sh\nSTUB_AGENT={agent} exec "{sys.executable}" "{STUB}" "$@"\n', encoding="utf-8")
            p.chmod(0o755)


class OrchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orch-test-"))
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        self.logs = self.tmp / "logs"
        self.logs.mkdir()
        make_bin(self.tmp / "bin")
        self.env = dict(os.environ)
        self.env["PATH"] = str(self.tmp / "bin") + os.pathsep + self.env["PATH"]
        self.env["STUB_LOG_DIR"] = str(self.logs)
        self.env.pop("STUB_MODE", None)
        for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"),
                     ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
            self.env[k] = v
        self.git("init", "-q", "-b", "main")
        (self.repo / "shared.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.repo, capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def orch(self, *a, mode=None, ok=True):
        env = dict(self.env)
        if mode:
            env["STUB_MODE"] = mode
        r = subprocess.run([sys.executable, str(ORCH), *a], cwd=self.repo, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=300)
        if ok and r.returncode != 0:
            self.fail(f"orch {a} failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")
        return r

    def meta(self, tid):
        return json.loads((self.repo / ".orch" / "runs" / tid / "meta.json").read_text(encoding="utf-8"))

    def write_plan(self, tasks, context="test project"):
        d = self.repo / ".orch"
        d.mkdir(exist_ok=True)
        (d / "plan.json").write_text(json.dumps({"context": context, "tasks": tasks}), encoding="utf-8")

    def write_config(self, cfg):
        d = self.repo / ".orch"
        d.mkdir(exist_ok=True)
        (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    # tests
    def test_doctor_live(self):
        r = self.orch("doctor", "--live")
        self.assertIn("[ok] codex: rc=0", r.stdout)
        self.assertIn("[ok] agy: rc=0", r.stdout)

    def test_waves_parallel_and_merge(self):
        self.write_plan([
            {"id": "api", "agent": "codex", "title": "API", "prompt": "make api", "files": ["api.py"]},
            {"id": "home", "agent": "agy", "title": "Home", "prompt": "make home", "files": ["ui/home.html"]},
            {"id": "wire", "agent": "codex", "title": "Wire", "prompt": "wire", "depends_on": ["api", "home"]},
        ])
        r = self.orch("run", ".orch/plan.json")
        self.assertIn("skip wire", r.stdout)
        self.assertEqual(self.meta("api")["status"], "done")
        self.assertEqual(self.meta("home")["status"], "done")
        self.assertEqual(self.meta("home")["agent"], "antigravity")
        self.assertFalse((self.repo / "api.py").exists(), "main tree must be untouched before merge")

        review = self.orch("review", "api").stdout
        self.assertIn("## SUMMARY", review)
        self.assertIn("api.py", review)

        self.orch("merge", "api")
        self.orch("merge", "home", "--squash")
        self.assertTrue((self.repo / "api.py").exists())
        self.assertTrue((self.repo / "ui" / "home.html").exists())

        self.orch("run", ".orch/plan.json")  # wave 2
        self.orch("merge", "wire")
        self.assertTrue((self.repo / "wire.py").exists())
        prompt = (self.logs / "wire.codex.prompt").read_text(encoding="utf-8")
        self.assertIn("test project", prompt)  # shared context is passed

    def test_retry_with_feedback(self):
        self.orch("dispatch", "--agent", "codex", "--id", "fix", "--prompt", "do it")
        self.orch("retry", "fix", "--feedback", "add a comment")
        m = self.meta("fix")
        self.assertEqual(m["attempts"], 2)
        self.orch("merge", "fix")
        self.assertIn("fixed after feedback", (self.repo / "fix.py").read_text(encoding="utf-8"))

    def test_retry_switches_agent(self):
        self.orch("dispatch", "--agent", "codex", "--id", "sw", "--prompt", "x", mode="nochange")
        self.assertEqual(self.meta("sw")["status"], "no_changes")
        self.orch("retry", "sw", "--agent", "agy", "--feedback", "try again")
        self.assertEqual(self.meta("sw")["agent"], "antigravity")
        self.assertEqual(self.meta("sw")["status"], "done")

    def test_conflict_then_rebase_resolves(self):
        self.orch("dispatch", "--agent", "codex", "--id", "c1", "--prompt", "x", mode="conflict")
        self.orch("dispatch", "--agent", "agy", "--id", "c2", "--prompt", "x", mode="conflict")
        self.orch("merge", "c1")
        r = self.orch("merge", "c2", ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.meta("c2")["status"], "conflict")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no"), "", "merge must abort cleanly")

        self.orch("rebase", "c2", mode="resolve")
        self.orch("merge", "c2")
        self.assertEqual((self.repo / "shared.txt").read_text(encoding="utf-8"), "base\nresolved\n")

    def test_agy_error_is_failed(self):
        self.orch("dispatch", "--agent", "agy", "--id", "e1", "--prompt", "x", mode="error")
        self.assertEqual(self.meta("e1")["status"], "failed")
        self.assertIn("quota exceeded", self.orch("review", "e1").stdout)

    def test_codex_nonzero_exit_is_failed(self):
        self.orch("dispatch", "--agent", "codex", "--id", "e2", "--prompt", "x", mode="error")
        m = self.meta("e2")
        self.assertEqual(m["status"], "failed")
        self.assertIn("boom", m["error"])

    def test_timeout(self):
        self.write_config({"agents": {"antigravity": {"timeout_s": 3}}})
        self.orch("dispatch", "--agent", "agy", "--id", "slow", "--prompt", "x", mode="hang")
        self.assertEqual(self.meta("slow")["status"], "timeout")

    def test_verify_cmd_failure(self):
        cmd = f'"{sys.executable}" -c "import sys; sys.exit(1)"'
        self.write_config({"verify_cmd": cmd})
        self.orch("dispatch", "--agent", "codex", "--id", "v1", "--prompt", "x")
        m = self.meta("v1")
        self.assertEqual(m["status"], "verify_failed")
        self.assertEqual(m["verify"], "fail")

    def test_multiline_prompt_reaches_agy_intact(self):
        tricky = 'line 1\nline 2 with "quotes" & | < > %PATH% $HOME `tick`\nviệt nam ✓'
        self.orch("dispatch", "--agent", "agy", "--id", "ml", "--prompt", tricky)
        got = (self.logs / "ml.antigravity.prompt").read_text(encoding="utf-8")
        self.assertIn(tricky, got)

    def test_discard_and_clean(self):
        self.orch("dispatch", "--agent", "codex", "--id", "d1", "--prompt", "x")
        wt = Path(self.meta("d1")["worktree"])
        self.assertTrue(wt.exists())
        self.orch("discard", "d1")
        self.assertFalse(wt.exists())
        self.assertNotIn("orch/d1", self.git("branch"))
        self.orch("clean")
        self.assertIn("discarded", self.orch("status").stdout)

    def test_unicode_summary_on_legacy_codepage(self):
        # Windows pipes default to an ANSI code page; output must not crash on Vietnamese text.
        self.orch("dispatch", "--agent", "agy", "--id", "u1", "--prompt", "x")
        self.env["PYTHONIOENCODING"] = "cp1252"
        r = self.orch("review", "u1")
        self.assertIn("đã xong ✓", r.stdout)

    def test_state_dir_is_git_ignored(self):
        self.orch("dispatch", "--agent", "codex", "--id", "g1", "--prompt", "x")
        self.assertNotIn(".orch", self.git("status", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
