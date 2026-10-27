"""Fake Codex / Antigravity CLI used by the test-suite.

Invoked as `codex ...` or `agy ...` through small wrappers that tests generate.
Behaviour is selected with the STUB_MODE env var:
  (unset)   create <task>.py (codex) or ui/<task>.html (agy)
  conflict  append a line to shared.txt
  resolve   rewrite shared.txt without conflict markers
  nochange  do nothing
  error     agy: report status ERROR; codex: exit 3
  hang      sleep forever
Every received prompt is written to $STUB_LOG_DIR/<task>.<agent>.prompt for assertions.
"""
import json
import os
import sys
import time

agent = os.environ.get("STUB_AGENT", "codex")
args = sys.argv[1:]

if args and args[0] == "--version":
    print(f"{agent} stub 0.0.1")
    sys.exit(0)

mode = os.environ.get("STUB_MODE", "")
tid = os.environ.get("ORCH_TASK_ID", "adhoc")

if agent == "codex":
    workdir = args[args.index("-C") + 1] if "-C" in args else os.getcwd()
    out_file = args[args.index("-o") + 1] if "-o" in args else None
    prompt = sys.stdin.read() if args and args[-1] == "-" else args[-1]
else:  # agy, stream-json on stdin
    assert args[:4] == ["--input-format", "stream-json", "--output-format", "stream-json"], args
    workdir = os.getcwd()
    out_file = None
    prompt = json.loads(sys.stdin.readline())["message"]["content"]

log_dir = os.environ.get("STUB_LOG_DIR")
if log_dir:
    with open(os.path.join(log_dir, f"{tid}.{agent}.prompt"), "w", encoding="utf-8") as f:
        f.write(prompt)

if "Reply with exactly: PONG" in prompt:
    reply = "PONG"
else:
    if mode == "hang":
        time.sleep(3600)
    if mode == "error" and agent == "codex":
        print("boom", file=sys.stderr)
        sys.exit(3)
    p = lambda *parts: os.path.join(workdir, *parts)  # noqa: E731
    if mode == "conflict":
        with open(p("shared.txt"), "a", encoding="utf-8") as f:
            f.write(f"{agent} {tid}\n")
    elif mode == "resolve":
        with open(p("shared.txt"), "w", encoding="utf-8") as f:
            f.write("base\nresolved\n")
    elif mode in ("nochange", "error"):
        pass
    elif agent == "codex":
        with open(p(f"{tid}.py"), "a", encoding="utf-8") as f:
            f.write("# fixed after feedback\n" if "FEEDBACK FROM MASTER" in prompt else f"print('{tid}')\n")
    else:
        os.makedirs(p("ui"), exist_ok=True)
        with open(p("ui", f"{tid}.html"), "w", encoding="utf-8") as f:
            f.write(f"<h1>{tid}</h1>\n")
    reply = f"## SUMMARY\n- Changed: stuff for {tid}\n- How to verify: look\n"

if agent == "codex":
    print(json.dumps({"type": "thread.started"}))
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": reply}}))
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(reply)
else:
    print(json.dumps({"event": "init", "init": {"cwd": workdir}}))
    status = "ERROR" if mode == "error" else "SUCCESS"
    print(json.dumps({"event": "result", "result": {"status": status, "response": reply,
                                                    "error": "quota exceeded" if status == "ERROR" else None}}))
