"""instructions for validated tasks + the dev / held-out split.

instruction = the linked issue if there is one (it describes the problem, not
the fix), else the PR title + body, with template boilerplate stripped. an
instruction is flagged for human review when it's thin, or when it names a
file or function the gold patch touches. flagged ones get a rewritten
statement in eval/tasks/rewrites.json (kept next to the original).

    uv run python -m ax_eval.statements --dev 10 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys

from ax_eval.mine import TASKS

THIN = 200
MAX_TASKS = 50

BOILERPLATE = [
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"^#+\s*The author should do the following.*?(?=^#|\Z)", re.S | re.M | re.I),
    re.compile(r"^\s*[-*]\s*\[[ xX]\].*$", re.M),
    re.compile(r"^#+\s*(Checklist|Check list)\b.*?(?=^#|\Z)", re.S | re.M | re.I),
]


def clean(text: str) -> str:
    for rx in BOILERPLATE:
        text = rx.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def changed_symbols(patch: str) -> set[str]:
    """function/const/class names on added or removed lines, plus hunk headers."""
    names = set()
    for l in patch.splitlines():
        if l.startswith(("+++", "---")):
            continue
        if l[:1] in "+-" or l.startswith("@@"):
            names.update(re.findall(r"(?:function|const|let|class|interface|type)\s+([A-Za-z_$][\w$]{3,})", l))
    return names


def leaks(text: str, task: dict) -> list[str]:
    """source files of the gold patch named in the text (that points at the fix)."""
    hits = []
    for f in task["src_files"]:
        base = f.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0]
        if f in text or (stem not in {"index", "utils", "types"} and re.search(rf"\b{re.escape(base)}\b", text)):
            hits.append(f)
    return hits


def mentions(text: str, task: dict) -> list[str]:
    """changed symbols named in the text. usually the public api the bug is
    about, so it's reported, not flagged."""
    return [s for s in sorted(changed_symbols(task["gold_patch"])) if re.search(rf"\b{re.escape(s)}\b", text)]


def instruction(task: dict) -> tuple[str, str]:
    """(text, source)"""
    issues = [i for i in task.get("issues") or [] if len(clean(i.get("body") or "")) >= 80]
    if issues:
        i = issues[0]
        return f"{i['title']}\n\n{clean(i['body'])}", f"issue #{i['number']}"
    return f"{task['title']}\n\n{clean(task['body'])}", f"PR #{task['pr']}"


def diff_size(task: dict) -> int:
    return sum(1 for l in task["gold_patch"].splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))


def split(tasks: list[dict], dev: int, seed: int) -> dict[str, str]:
    """seeded draw stratified by gold diff size: sort by size, cut into `dev`
    strata, pick one per stratum for dev."""
    rng = random.Random(seed)
    ordered = sorted(tasks, key=lambda t: (diff_size(t), t["id"]))
    k = len(ordered)
    out = {t["id"]: "heldout" for t in ordered}
    for s in range(dev):
        stratum = ordered[s * k // dev : (s + 1) * k // dev]
        if stratum:
            out[rng.choice(stratum)["id"]] = "dev"
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dev", type=int, default=10)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--max", type=int, default=MAX_TASKS)
    a = p.parse_args(argv)
    tasks = [json.loads(l) for l in open(TASKS / "tasks.jsonl")]
    rng = random.Random(a.seed)
    if len(tasks) > a.max:
        tasks = sorted(rng.sample(tasks, a.max), key=lambda t: t["id"])
    rewrites = {}
    rw = TASKS / "rewrites.json"
    if rw.exists():
        rewrites = json.loads(rw.read_text())
    sets = split(tasks, a.dev, a.seed)
    flagged = []
    with open(TASKS / "final.jsonl", "w") as f:
        for t in tasks:
            text, source = instruction(t)
            reasons = []
            if len(text) < THIN:
                reasons.append("thin")
            lk = leaks(text, t)
            if lk:
                reasons.append("names " + ", ".join(lk[:5]))
            rec = {
                "id": t["id"],
                "set": sets[t["id"]],
                "instruction": rewrites.get(t["id"], text),
                "original_instruction": text,
                "instruction_source": "rewrite" if t["id"] in rewrites else source,
                "flagged": bool(reasons),
                "flag_reasons": reasons,
                "symbol_mentions": mentions(text, t),
                **{k: t[k] for k in ("repo", "pr", "commit", "base", "src_files", "test_files", "gold_patch", "test_patch", "image", "test_run_files", "fail_to_pass", "pass_to_pass")},
            }
            if reasons:
                flagged.append(rec)
            f.write(json.dumps(rec) + "\n")
    n_dev = sum(1 for v in sets.values() if v == "dev")
    print(
        json.dumps({"tasks": len(tasks), "dev": n_dev, "heldout": len(tasks) - n_dev, "flagged": len(flagged), "rewritten": sum(1 for t in tasks if t["id"] in rewrites)}),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
