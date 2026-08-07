#!/usr/bin/env python3
"""Move OPEN PILANTRA's dialogue between OPIL-source.bas and JSON.

story/dialogue.json is the source of truth for text. The build emits the DATA
blocks from it and has a stripped copy of the source INCLUDE them, so the
original OPIL-source.bas is only ever read, never written.

    emit     <json> <out.bas>            the ten label+DATA blocks, from JSON
    strip    <bas> <out.bas> <incpath>   the source minus DATA, plus one INCLUDE
    lint     <json>                      check the authoring constraints
    extract  <bas> <json>                re-derive the JSON from the .bas

`RESTORE` into a label defined inside an INCLUDEd file is safe: compiling the
same program with the DATA inline and with it included emits byte-identical
code (2056 instructions, differing only in `; L:n` source-line comments).
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
            "This file is the source of truth for text; the build emits the "
            "DATA blocks from it. Edit here, then run make."
        ),
        "characters": characters,
    }


# --- emit / strip: what the build actually uses ------------------------------


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


GENERATED_BANNER = (
    "REM =========================================================================\n"
    "REM  GENERATED FILE - DO NOT EDIT\n"
    "REM  Emitted from %s by tools/dialogue.py.\n"
    "REM  Edit the dialogue there; this file is rebuilt on every make.\n"
    "REM ========================================================================="
)


def emit(doc, source_name="story/dialogue.json"):
    """Render the ten label + DATA blocks as an INCLUDE-able .bas."""
    out = [GENERATED_BANNER % source_name, ""]
    for char in doc["characters"]:
        out.append("REM --- %s (%s)" % (char["name"].upper(), char["side"]))
        out.append("%s:" % char["label"])
        flat = [s for balloon in char["balloons"] for s in balloon]
        for n in range(0, len(flat), STRINGS_PER_DATA_LINE):
            out.append(format_data_line(flat[n : n + STRINGS_PER_DATA_LINE]))
        out.append("")
    return "\n".join(out) + "\n"


def strip(bas_path, include_path):
    """Return the source with every label+DATA block replaced by one INCLUDE."""
    text, had_bom = read_source(bas_path)
    lines = text.split("\n")
    blocks, _ = find_blocks(lines)

    drop = set()
    first = None
    for label, (label_idx, data_idx) in blocks.items():
        drop.add(label_idx)
        drop.update(data_idx)
        if first is None or label_idx < first:
            first = label_idx

    if first is None:
        raise SystemExit("%s: found no dialogue blocks to strip" % bas_path)

    out = []
    for i, line in enumerate(lines):
        if i == first:
            out.append('INCLUDE "%s"' % include_path)
        if i not in drop:
            out.append(line)
    return "\n".join(out), had_bom


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

    if cmd == "lint" and len(argv) == 3:
        doc = json.loads(Path(argv[2]).read_text())
        problems = lint(doc)
        for p in problems:
            print(p)
        print("%d problem(s)" % len(problems))
        return 1 if problems else 0

    if cmd == "emit" and len(argv) == 4:
        doc = json.loads(Path(argv[2]).read_text())
        problems = lint(doc)
        if problems:
            print("refusing to emit - fix these first:")
            for p in problems:
                print("  " + p)
            return 1
        Path(argv[3]).parent.mkdir(parents=True, exist_ok=True)
        Path(argv[3]).write_text(emit(doc, argv[2]))
        balloons = sum(len(c["balloons"]) for c in doc["characters"])
        print(
            "emitted %d characters, %d balloons -> %s"
            % (len(doc["characters"]), balloons, argv[3])
        )
        return 0

    if cmd == "strip" and len(argv) == 5:
        text, had_bom = strip(argv[2], argv[4])
        Path(argv[3]).parent.mkdir(parents=True, exist_ok=True)
        write_source(argv[3], text, had_bom)
        remaining = sum(1 for l in text.split("\n") if DATA_RE.match(l))
        print(
            'stripped %s -> %s (INCLUDE "%s", %d DATA lines left)'
            % (argv[2], argv[3], argv[4], remaining)
        )
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
