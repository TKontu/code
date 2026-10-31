#!/usr/bin/env python3
"""Prove each `sh -c '...'` body in a workflow survives as ONE argument.

The CI failure this guards against: a step passes a script to
`sh -c '...'` and the body contains an inner pair of single quotes. Those
CLOSE the outer string, so the runner hands the container a SPLIT, broken
script. The step dies with "Unterminated quoted string" before it asserts
anything - which looks like the smoke test failing when it is the TEST that
is malformed.

Faithful method: run each `run:` block through the shell with `docker`
replaced by a probe that counts the arguments following `-c`. The shell's
own parser does the splitting, so the count reflects exactly what the
container would receive. An intact body arrives as one argument; a split
one arrives as several.

Usage: check-shell-quoting.py <workflow.yml>
"""
import re
import subprocess
import sys

PROBE = '''docker() {
  body_args=0
  seen=0
  for a in "$@"; do
    if [ "$seen" = 1 ]; then body_args=$((body_args+1)); fi
    if [ "$a" = "-c" ]; then seen=1; fi
  done
  printf 'BODY_ARGS=%s\\n' "$body_args"
}
'''


def run_blocks(text):
    """Yield (lineno, block_text) for every `run: |` block."""
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if re.match(r"^\s*run: \|\s*$", lines[i]):
            indent = len(lines[i]) - len(lines[i].lstrip())
            body = []
            j = i + 1
            while j < len(lines):
                l = lines[j]
                if l.strip() == "":
                    body.append("")
                    j += 1
                    continue
                if len(l) - len(l.lstrip()) <= indent:
                    break
                body.append(l[indent + 2:])
                j += 1
            out.append((i + 1, "\n".join(body)))
            i = j
        else:
            i += 1
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: check-shell-quoting.py <workflow.yml>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    bad = 0
    checked = 0
    for lineno, body in run_blocks(open(path).read()):
        if "docker run" not in body:
            continue
        r = subprocess.run(
            ["bash", "-c", PROBE + "\n" + body],
            capture_output=True, text=True,
        )
        counts = [int(x) for x in re.findall(r"BODY_ARGS=(\d+)", r.stdout)]
        if not counts:
            continue
        checked += 1
        for n in counts:
            if n != 1:
                print(f"line {lineno}: the -c body became {n} arguments, "
                      f"expected 1 - an inner quote split it")
                bad += 1
    if bad:
        print(f"{bad} broken body/bodies")
        return 1
    print(f"quoting OK ({checked} run blocks checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
