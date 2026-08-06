#!/usr/bin/env python3
"""Move OPEN PILANTRA's dialogue between OPIL-source.bas and JSON.

    extract  <bas> <json>   read the DATA blocks out to JSON
    inject   <bas> <json>   write JSON values back into the .bas, in place
    lint     <json>         check the authoring constraints
    verify   <bas>          prove the round trip is byte-exact

The correctness bar is `verify`: extract to JSON, inject that JSON back into a
scratch copy, and require the result to be byte-identical to the original. If
that holds, the extractor is not losing anything.

Injection is line-wise and conservative. A DATA line whose values are unchanged
is left exactly as the author wrote it, tabs and stray spaces included. Only
lines you actually edited get regenerated, and those are laid out in the
author's own style (commas on columns 20/36/52 at 4-column tab stops).
"""

import json
import re
import sys
from pathlib import Path

# --- the shape of the file --------------------------------------------------

LABEL_RE = re.compile(r"^([A-Za-z_]\w*):\s*$")
DATA_RE = re.compile(r"^DATA\s")
STRING_RE = re.compile(r'"([^"]*)"')
# "REM --- MANO COURIER (left)" - the author's own annotation above each label
HEADER_RE = re.compile(r"^REM\s*-+\s*(.+?)\s*\((left|right)\)\s*$", re.I)
# "IF ch1=0 THEN RESTORE manot" - authoritative slot mapping
RESTORE_RE = re.compile(r"^\s*IF\s+(ch[12])\s*=\s*(\d+)\s+THEN\s+RESTORE\s+(\w+)", re.I)

# Authoring constraints, documented in docs/MAKE-YOUR-OWN-STORY.md
DATA_LINES_PER_CHARACTER = 10
STRINGS_PER_DATA_LINE = 4
MAX_STRING_LEN = 13
BLANK = " "

# Column at which each comma lands in the author's layout, tab width 4.
COMMA_COLUMNS = (20, 36, 52)
TAB_WIDTH = 4


def read_source(path):
    """Return (text, had_bom). The source carries a UTF-8 BOM; preserve it."""
    raw = Path(path).read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    return raw.decode("ascii"), had_bom


def write_source(path, text, had_bom):
    data = text.encode("ascii")
    if had_bom:
        data = b"\xef\xbb\xbf" + data
    Path(path).write_bytes(data)


def slot_map(lines):
    """Derive label -> (side, slot) from the RESTORE chain rather than guessing."""
    out = {}
    for line in lines:
        m = RESTORE_RE.match(line)
        if m:
            var, slot, label = m.group(1).lower(), int(m.group(2)), m.group(3)
            out[label] = ("left" if var == "ch1" else "right", slot)
    return out


def find_blocks(lines):
    """Locate each dialogue block: label -> (label_index, [data line indices])."""
    slots = slot_map(lines)
    blocks = {}
    for i, line in enumerate(lines):
        m = LABEL_RE.match(line)
        if not m or m.group(1) not in slots:
            continue
        label = m.group(1)
        data_idx = []
        j = i + 1
        while j < len(lines) and DATA_RE.match(lines[j]):
            data_idx.append(j)
            j += 1
        blocks[label] = (i, data_idx)
    return blocks, slots


# --- extract ----------------------------------------------------------------


def extract(bas_path):
    text, _ = read_source(bas_path)
    lines = text.split("\n")
    blocks, slots = find_blocks(lines)

    characters = []
    for label, (label_idx, data_idx) in blocks.items():
        side, slot = slots[label]

        name = label
        for k in range(label_idx - 1, max(-1, label_idx - 4), -1):
            m = HEADER_RE.match(lines[k])
            if m:
                name = m.group(1).title()
                break

        strings = []
        for j in data_idx:
            strings.extend(STRING_RE.findall(lines[j]))

        balloons = [[strings[i], strings[i + 1]] for i in range(0, len(strings) - 1, 2)]

        characters.append(
            {
                "label": label,
                "name": name,
                "side": side,
                "slot": slot,
                "balloons": balloons,
            }
        )

    characters.sort(key=lambda c: (c["side"] != "left", c["slot"]))
    return {
        "_comment": (
            "Dialogue for OPEN PILANTRA. Each balloon is [line1, line2]; use "
            '" " (a single space) for a blank second line, not "". Constraints: '
            "20 balloons per character, max 13 characters per line. "
            "Edit here, then: python3 tools/dialogue.py inject OPIL-source.bas "
            "story/dialogue.json"
        ),
        "characters": characters,
    }


# --- inject -----------------------------------------------------------------


def format_data_line(four):
    """Lay out one DATA line in the author's style, commas on fixed columns."""
    out = 'DATA "%s"' % four[0]
    for value, target in zip(four[1:], COMMA_COLUMNS):
        col = len(out.expandtabs(TAB_WIDTH))
        while col < target:
            out += "\t"
            col = len(out.expandtabs(TAB_WIDTH))
        out += ',"%s"' % value
    return out


def inject(bas_path, doc):
    text, had_bom = read_source(bas_path)
    lines = text.split("\n")
    blocks, _ = find_blocks(lines)
    by_label = {c["label"]: c for c in doc["characters"]}

    changed = 0
    for label, (_, data_idx) in blocks.items():
        char = by_label.get(label)
        if char is None:
            continue
        flat = [s for balloon in char["balloons"] for s in balloon]
        if len(flat) != len(data_idx) * STRINGS_PER_DATA_LINE:
            raise SystemExit(
                "%s: expected %d strings, JSON has %d"
                % (label, len(data_idx) * STRINGS_PER_DATA_LINE, len(flat))
            )
        for n, j in enumerate(data_idx):
            want = flat[n * STRINGS_PER_DATA_LINE : (n + 1) * STRINGS_PER_DATA_LINE]
            if STRING_RE.findall(lines[j]) == want:
                continue  # untouched by the author - leave the line byte-identical
            lines[j] = format_data_line(want)
            changed += 1

    write_source(bas_path, "\n".join(lines), had_bom)
    return changed


# --- lint -------------------------------------------------------------------


def lint(doc):
    problems = []
    expected = DATA_LINES_PER_CHARACTER * STRINGS_PER_DATA_LINE // 2
    for char in doc["characters"]:
        who = char["label"]
        n = len(char["balloons"])
        if n != expected:
            problems.append(
                "%s: %d balloons, needs exactly %d - the picker rolls RND(20)*2 "
                "and short blocks yield blank balloons" % (who, n, expected)
            )
        for i, balloon in enumerate(char["balloons"]):
            if len(balloon) != 2:
                problems.append("%s balloon %d: needs exactly 2 lines" % (who, i))
                continue
            for line in balloon:
                if len(line) > MAX_STRING_LEN:
                    problems.append(
                        '%s balloon %d: "%s" is %d chars, max %d'
                        % (who, i, line, len(line), MAX_STRING_LEN)
                    )
                if line == "":
                    problems.append(
                        '%s balloon %d: empty string - use " " for a blank line'
                        % (who, i)
                    )
                if '"' in line:
                    problems.append('%s balloon %d: contains a double quote' % (who, i))
    return problems


# --- verify -----------------------------------------------------------------


def verify(bas_path):
    import shutil
    import tempfile

    original = Path(bas_path).read_bytes()
    doc = extract(bas_path)

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "scratch.bas"
        shutil.copy(bas_path, scratch)
        inject(scratch, doc)
        rebuilt = scratch.read_bytes()

    balloons = sum(len(c["balloons"]) for c in doc["characters"])
    if rebuilt == original:
        print(
            "round trip OK - %d characters, %d balloons, %d bytes identical"
            % (len(doc["characters"]), balloons, len(original))
        )
        return 0

    print("ROUND TRIP FAILED - regenerated file differs from the original")
    o = original.decode("utf-8-sig").split("\n")
    r = rebuilt.decode("utf-8-sig").split("\n")
    for n, (a, b) in enumerate(zip(o, r), 1):
        if a != b:
            print("  line %d:\n    was: %r\n    got: %r" % (n, a, b))
    return 1


# --- cli --------------------------------------------------------------------


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]

    if cmd == "extract" and len(argv) == 4:
        doc = extract(argv[2])
        Path(argv[3]).parent.mkdir(parents=True, exist_ok=True)
        Path(argv[3]).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        balloons = sum(len(c["balloons"]) for c in doc["characters"])
        print(
            "extracted %d characters, %d balloons -> %s"
            % (len(doc["characters"]), balloons, argv[3])
        )
        return 0

    if cmd == "inject" and len(argv) == 4:
        doc = json.loads(Path(argv[3]).read_text())
        problems = lint(doc)
        if problems:
            print("refusing to inject - fix these first:")
            for p in problems:
                print("  " + p)
            return 1
        changed = inject(argv[2], doc)
        print("injected into %s - %d DATA lines rewritten" % (argv[2], changed))
        return 0

    if cmd == "lint" and len(argv) == 3:
        doc = json.loads(Path(argv[2]).read_text())
        problems = lint(doc)
        for p in problems:
            print(p)
        print("%d problem(s)" % len(problems))
        return 1 if problems else 0

    if cmd == "verify" and len(argv) == 3:
        return verify(argv[2])

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
