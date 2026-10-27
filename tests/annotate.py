"""Turn unittest failures in a log file into GitHub Actions error annotations."""
import re
import sys

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
blocks = re.split(r"^={50,}\n", text, flags=re.M)[1:]
for b in blocks[:10]:
    head, _, body = b.partition("\n")
    msg = body[-3500:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title={head.strip()[:120]}::{msg}")
if not blocks:
    tail = text[-3500:].replace("%", "%25").replace("\n", "%0A")
    print(f"::error title=test log tail::{tail}")
