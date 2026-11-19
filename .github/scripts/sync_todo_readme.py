import re
import subprocess
from collections import defaultdict

README = "README.md"
HEADER_NEEDLE = "Complete TODO List"
TARGET_PATHS = [
    "luffy/deepscaler/utils.py",
    "luffy/verl/verl/protocol.py",
]

ENTRY_RE = re.compile(r'^- \[ \] \*\*(?P<path>.+?):(?P<line>\d+)\*\* - (?P<text>.*)$')


def norm_text(s):
    s = (s or "").lower()
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', s)


def extract_todo_text(raw_line):
    idx = raw_line.find("TODO")
    if idx < 0:
        return None
    rest = raw_line[idx + 4:]
    rest = rest.lstrip()
    if rest.startswith(":"):
        rest = rest[1:]
    return rest.strip()


def extract_todos(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                if "TODO" not in raw:
                    continue
                text = extract_todo_text(raw)
                if text is None:
                    continue
                out.append((lineno, text))
    except FileNotFoundError:
        print("MISSING FILE", path)
    return out


def changed_py_targets():
    targets = set(TARGET_PATHS)
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "origin/main", "HEAD"],
            text=True,
            stderr=subprocess.STDOUT,
        )
        for line in out.splitlines():
            path = line.strip()
            if path.endswith(".py") and path.startswith("luffy/"):
                targets.add(path)
        print("GIT DIFF main..HEAD:")
        print(out.strip())
    except Exception as exc:
        print("GIT_DIFF_FALLBACK", repr(exc))
    return sorted(targets)


def main():
    with open(README, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if HEADER_NEEDLE in line and line.lstrip().startswith("###"):
            header_idx = i
            break
    if header_idx is None:
        raise SystemExit("TODO section header not found")

    heading_idx = None
    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            heading_idx = i
            break
    if heading_idx is None:
        heading_idx = len(lines)

    existing = []
    malformed = []
    for idx in range(header_idx + 1, heading_idx):
        line = lines[idx]
        if not line.strip():
            continue
        match = ENTRY_RE.match(line)
        if not match:
            malformed.append((idx + 1, line))
            continue
        data = match.groupdict()
        data["line"] = int(data["line"])
        existing.append(data)

    print(
        f"HEADER_LINE={header_idx + 1} NEXT_HEADING_LINE={heading_idx + 1} "
        f"EXISTING_ENTRIES={len(existing)} MALFORMED={len(malformed)}"
    )
    if malformed:
        print("MALFORMED_SECTION_LINES:")
        for ln, content in malformed[:50]:
            print(ln, repr(content[:240]))

    targets = changed_py_targets()
    print("TARGETS", targets)

    baseline_by_path = defaultdict(list)
    for entry in existing:
        baseline_by_path[entry["path"]].append(entry)

    new_by_path = {}
    for path in targets:
        todos = extract_todos(path)
        bases = baseline_by_path.get(path, [])
        used = [False] * len(bases)
        entries = []
        for lineno, todo_text in todos:
            normalized = norm_text(todo_text)
            match_j = None
            for j, base in enumerate(bases):
                if not used[j] and norm_text(base["text"]) == normalized:
                    match_j = j
                    break
            if match_j is None:
                for j, base in enumerate(bases):
                    if used[j]:
                        continue
                    base_norm = norm_text(base["text"])
                    if normalized and base_norm and (base_norm in normalized or normalized in base_norm):
                        match_j = j
                        break
            if match_j is not None:
                used[match_j] = True
                display_text = bases[match_j]["text"]
                print(
                    f"MATCH {path} old={bases[match_j]['line']} new={lineno} "
                    f"text={display_text[:90]!r}"
                )
            else:
                display_text = todo_text
                print(f"NEW_OR_UNMATCHED {path}:{lineno} text={display_text[:120]!r}")
            entries.append({"path": path, "line": lineno, "text": display_text})

        for j, base in enumerate(bases):
            if not used[j]:
                print(
                    f"REMOVE {path}:{base['line']} "
                    f"text={base['text'][:120]!r}"
                )
        new_by_path[path] = entries

    final_entries = []
    for entry in existing:
        if entry["path"] in targets:
            continue
        final_entries.append(
            {"path": entry["path"], "line": entry["line"], "text": entry["text"]}
        )
    for path in targets:
        final_entries.extend(new_by_path.get(path, []))

    final_entries.sort(key=lambda item: (item["path"], item["line"]))

    previous_path = None
    previous_line = None
    for item in final_entries:
        if item["path"] == previous_path and item["line"] < previous_line:
            raise SystemExit("entries not sorted after construction")
        previous_path, previous_line = item["path"], item["line"]

    entry_lines = [
        f"- [ ] **{item['path']}:{item['line']}** - {item['text']}"
        for item in final_entries
    ]
    rebuilt = lines[: header_idx + 1] + [""] + entry_lines + [""] + lines[heading_idx:]
    new_text = "\n".join(rebuilt)
    if text.endswith("\n"):
        new_text += "\n"

    with open(README, "w", encoding="utf-8") as handle:
        handle.write(new_text)

    print(f"WROTE {README} FINAL_ENTRIES={len(final_entries)}")


if __name__ == "__main__":
    main()
