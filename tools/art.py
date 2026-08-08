#!/usr/bin/env python3
"""Move OPEN PILANTRA's graphics between OPIL-source.bas and PNG files.

    extract <bas> <dir>    every DIM byte array -> dir/<name>.png + manifest

PNGs are written **indexed**, one pixel per SG4 quadrant. The pixel value is
the palette index, so a round trip never depends on matching RGB values and the
colours below can be retuned freely without invalidating any artwork.

    index 0      quadrant off (black)
    index 1..8   quadrant lit, in SG4 colour 0..7
    index 9      a literal byte that is not an SG4 tile (see the manifest)

An SG4 tile byte is `128 + colour*16 + quadrants`, where the low four bits light
the cell's 2x2 quadrants:

     bit 3 | bit 2        8 | 4
    -------+--------    ----+----
     bit 1 | bit 0        2 | 1

so each tile becomes 2x2 pixels and an array of W tiles by H rows becomes a
2W x 2H image.

The arrays do not carry their own shape - the stride lives in the draw loop
rather than the DIM - so STRIDES below is derived from reading those loops, and
is written into the manifest for the import side to use.
"""

import json
import re
import sys
from pathlib import Path

from PIL import Image

# Tile width of each array, read out of the POKE expressions in OPIL-source.bas.
# e.g. `POKE 1024+x+y*32, mano(x+y*16)` -> stride 16.
STRIDES = {
    "ugb": 32,      # FOR x=1152 TO 1408: POKE x, ugb(x-1152)  - linear, 32 wide
    "til": 14,      # POKE 1193+x+y*32, til(z)                 - x=0..13
    "mano": 16, "john": 16, "elec": 16, "capt": 16, "minh": 16,
    "chav": 16, "kuro": 16, "wolf": 16, "isac": 16, "shon": 16,
    "suitA": 32,    # POKE 1024+x+(y+1)*32, suitA(x+z*32)
    "suitB": 14,    # POKE 1033+x+(y+1)*32, suitB(x+z*14)
    "safe": 19,     # POKE 1057+x+y*32, safe(x+(y+1)*19)
    "midl": 64, "dock": 64, "citi": 64, "spac": 64,
}

# Only 15 of the 16 columns of a portrait are ever drawn (x=0..14); the last is
# padding. Recorded so the import side knows it is not art.
VISIBLE_WIDTH = {name: 15 for name in
                 ("mano john elec capt minh chav kuro wolf isac shon".split())}

# Sampled from XRoar's own output in docs/screens/ rather than guessed. Yellow
# is the one colour no capture happened to contain - it is an approximation,
# and because the PNGs are indexed it can be corrected without touching them.
PALETTE = [
    (0x00, 0x00, 0x00),  # 0  quadrant off
    (0x5E, 0xB9, 0x41),  # 1  SG4 0  green     measured
    (0xF0, 0xE2, 0x3A),  # 2  SG4 1  yellow    APPROXIMATE
    (0x2B, 0x25, 0x7C),  # 3  SG4 2  blue      measured
    (0x78, 0x24, 0x38),  # 4  SG4 3  red       measured
    (0xFF, 0xFF, 0xFF),  # 5  SG4 4  buff      measured
    (0x58, 0xAA, 0x78),  # 6  SG4 5  cyan      measured
    (0xEC, 0x66, 0xF8),  # 7  SG4 6  magenta   measured
    (0xEE, 0x79, 0x4A),  # 8  SG4 7  orange    measured
    (0xFF, 0x00, 0x00),  # 9  unknown literal byte, see manifest
]
LITERAL = 9

# Bytes below 128 are text-mode cells, not SG4 tiles. The only one the demo
# uses is 32 - a space - which makes up Captain Glord's coat. In text mode a
# space paints the background, i.e. green, which is how he appears in the
# author's own roster; rendering it as green rather than as an alarm colour
# keeps the preview honest. Every literal is still recorded in the manifest, so
# the round trip does not depend on this mapping.
LITERAL_RENDERS_AS = {32: 1}  # 1 = SG4 green

ARRAY_RE = re.compile(
    r"^DIM\s+(\w+)\((\d+)\)\s*(AS\s+BYTE\s*)?=#\{([^}]*)\}", re.M)


def parse_arrays(bas_path):
    """Return {name: (bytes, as_byte)} for every DIM byte array in the source.

    Two arrays - ugb and til - are declared without `AS BYTE`. Whether that
    matters to codegen is not worth guessing at, so the declaration form is
    preserved rather than normalised."""
    text = Path(bas_path).read_text(encoding="utf-8-sig").replace("_\n", "")
    arrays = {}
    for m in ARRAY_RE.finditer(text):
        name, declared, as_byte, body = (
            m.group(1), int(m.group(2)), bool(m.group(3)), m.group(4))
        values = [v.strip() for v in body.split(",") if v.strip()]
        nums = [int(v[1:], 16) if v.startswith("$") else int(v) for v in values]
        if len(nums) != declared:
            raise SystemExit(
                "%s: DIM says %d bytes, found %d" % (name, declared, len(nums))
            )
        arrays[name] = (nums, as_byte, len(arrays))
    return arrays


def tile_pixels(byte):
    """One tile -> ((tl, tr), (bl, br)) palette indices."""
    if byte < 128:
        shown = LITERAL_RENDERS_AS.get(byte, LITERAL)
        return ((shown, shown), (shown, shown))
    colour = ((byte >> 4) & 7) + 1
    q = byte & 0x0F
    return (
        (colour if q & 8 else 0, colour if q & 4 else 0),
        (colour if q & 2 else 0, colour if q & 1 else 0),
    )


def decode_tile(pixels):
    """((tl, tr), (bl, br)) palette indices -> the tile byte, or None."""
    (tl, tr), (bl, br) = pixels
    quad = [tl, tr, bl, br]
    lit = [q for q in quad if q]
    if not lit:
        return 128
    if len(set(lit)) != 1 or lit[0] == LITERAL:
        return None
    bits = sum(b for q, b in zip(quad, (8, 4, 2, 1)) if q)
    return 128 + (lit[0] - 1) * 16 + bits


def to_png(nums, stride):
    """Render an array as an indexed image, plus any literal bytes found."""
    rows = len(nums) // stride
    img = Image.new("P", (stride * 2, rows * 2))
    flat = []
    for entry in PALETTE:
        flat.extend(entry)
    img.putpalette(flat + [0] * (768 - len(flat)))

    literals = {}
    px = img.load()
    for i, byte in enumerate(nums):
        r, c = divmod(i, stride)
        # Record anything the pixel encoding cannot reproduce, rather than
        # trusting a rule about what is representable. Two cases arise in this
        # source: text-mode bytes below 128, and tiles that carry a colour but
        # light no quadrants (144, 192) which are indistinguishable from an
        # empty cell once drawn.
        if decode_tile(tile_pixels(byte)) != byte:
            literals["%d,%d" % (r, c)] = byte
        (tl, tr), (bl, br) = tile_pixels(byte)
        px[c * 2, r * 2] = tl
        px[c * 2 + 1, r * 2] = tr
        px[c * 2, r * 2 + 1] = bl
        px[c * 2 + 1, r * 2 + 1] = br
    return img, literals, rows


def extract(bas_path, out_dir):
    arrays = parse_arrays(bas_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "_comment": (
            "Shape and provenance for the PNGs beside this file. Indexed PNGs, "
            "one pixel per SG4 quadrant; index 0 is off, 1..8 are SG4 colours "
            "0..7, index 9 marks a literal non-SG4 byte listed under 'literals' "
            "as 'row,col': value. 'stride' is the tile width, which the DIM "
            "arrays do not record - it comes from the draw loops. "
            "'visible_width' is how many columns the demo actually draws. "
            "'order' preserves the declaration order of the original source, "
            "and 'as_byte' its DIM form - ugb and til omit AS BYTE and really "
            "are 16-bit arrays, so normalising them would change codegen."
        ),
        "arrays": {},
    }

    unknown = sorted(set(arrays) - set(STRIDES))
    if unknown:
        raise SystemExit("no stride known for: %s" % ", ".join(unknown))

    for name in sorted(arrays):
        stride = STRIDES[name]
        nums, as_byte, order = arrays[name]
        if len(nums) % stride:
            raise SystemExit(
                "%s: %d bytes is not a multiple of stride %d"
                % (name, len(nums), stride)
            )
        img, literals, rows = to_png(nums, stride)
        img.save(out / ("%s.png" % name))
        entry = {"order": order, "stride": stride, "rows": rows,
                 "bytes": len(nums), "as_byte": as_byte}
        if name in VISIBLE_WIDTH:
            entry["visible_width"] = VISIBLE_WIDTH[name]
        if literals:
            entry["literals"] = literals
        manifest["arrays"][name] = entry
        print(
            "  %-6s %3d bytes  %2dx%-2d tiles -> %sx%s px%s"
            % (name, len(nums), stride, rows, stride * 2, rows * 2,
               "  (%d literal)" % len(literals) if literals else "")
        )

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("%d arrays -> %s" % (len(arrays), out))


# --- emit / strip: what the build actually uses ------------------------------

GENERATED_BANNER = (
    "REM =========================================================================\n"
    "REM  GENERATED FILE - DO NOT EDIT\n"
    "REM  Emitted from %s by tools/art.py.\n"
    "REM  Edit the PNGs there; this file is rebuilt on every make.\n"
    "REM ========================================================================="
)

PER_LINE = 16


def pixels_to_bytes(img, stride, rows, literals):
    """Indexed PNG -> the original tile bytes."""
    if img.mode != "P":
        raise SystemExit("expected an indexed PNG, got mode %s" % img.mode)
    if img.size != (stride * 2, rows * 2):
        raise SystemExit(
            "expected %dx%d px, got %dx%d"
            % (stride * 2, rows * 2, img.size[0], img.size[1])
        )
    px = img.load()
    out = []
    for r in range(rows):
        for c in range(stride):
            literal = literals.get("%d,%d" % (r, c))
            if literal is not None:
                out.append(literal)
                continue
            quad = [
                px[c * 2, r * 2],          # bit 3
                px[c * 2 + 1, r * 2],      # bit 2
                px[c * 2, r * 2 + 1],      # bit 1
                px[c * 2 + 1, r * 2 + 1],  # bit 0
            ]
            lit = [q for q in quad if q]
            if not lit:
                out.append(128)            # all quadrants off = empty cell
                continue
            if len(set(lit)) != 1:
                raise SystemExit(
                    "tile at row %d col %d mixes palette indices %s - an SG4 "
                    "cell can only hold one colour" % (r, c, sorted(set(lit)))
                )
            colour = lit[0] - 1
            bits = sum(b for q, b in zip(quad, (8, 4, 2, 1)) if q)
            out.append(128 + colour * 16 + bits)
    return out


def format_array(name, nums, as_byte):
    kind = " AS BYTE" if as_byte else ""
    head = "DIM %s(%d)%s =#{" % (name, len(nums), kind)
    lines = []
    for n in range(0, len(nums), PER_LINE):
        lines.append(",".join(str(v) for v in nums[n : n + PER_LINE]))
    pad = "\t" * 4
    body = (",_\n" + pad).join(lines)
    return head + body + "}"


def emit(art_dir):
    art = Path(art_dir)
    manifest = json.loads((art / "manifest.json").read_text())
    out = [GENERATED_BANNER % art_dir, ""]
    ordered = sorted(manifest["arrays"].items(),
                     key=lambda kv: kv[1].get("order", 0))
    for name, meta in ordered:
        img = Image.open(art / ("%s.png" % name))
        nums = pixels_to_bytes(
            img, meta["stride"], meta["rows"], meta.get("literals", {})
        )
        if len(nums) != meta["bytes"]:
            raise SystemExit(
                "%s: rebuilt %d bytes, manifest says %d"
                % (name, len(nums), meta["bytes"])
            )
        out.append(format_array(name, nums, meta.get("as_byte", True)))
        out.append("")
    return "\n".join(out) + "\n", len(manifest["arrays"])


def strip(bas_path, include_path):
    """Return the source with every DIM byte array replaced by one INCLUDE."""
    raw = Path(bas_path).read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("ascii") if had_bom else raw.decode("ascii")
    lines = text.split("\n")

    # An array declaration runs from its DIM line until a line without a
    # trailing continuation underscore.
    drop, first = set(), None
    i = 0
    while i < len(lines):
        if re.match(r"^DIM\s+\w+\(\d+\)\s*(AS\s+BYTE\s*)?=#\{", lines[i]):
            if first is None:
                first = i
            while i < len(lines):
                drop.add(i)
                if not lines[i].rstrip().endswith("_"):
                    break
                i += 1
        i += 1

    if first is None:
        raise SystemExit("%s: found no DIM byte arrays to strip" % bas_path)

    out = []
    for n, line in enumerate(lines):
        if n == first:
            out.append('INCLUDE "%s"' % include_path)
        if n not in drop:
            out.append(line)
    return "\n".join(out), had_bom


def main(argv):
    if len(argv) == 4 and argv[1] == "extract":
        extract(argv[2], argv[3])
        return 0

    if len(argv) == 4 and argv[1] == "emit":
        text, count = emit(argv[2])
        Path(argv[3]).parent.mkdir(parents=True, exist_ok=True)
        Path(argv[3]).write_text(text)
        print("emitted %d arrays -> %s" % (count, argv[3]))
        return 0

    if len(argv) == 5 and argv[1] == "strip":
        text, had_bom = strip(argv[2], argv[4])
        Path(argv[3]).parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("ascii")
        Path(argv[3]).write_bytes(b"\xef\xbb\xbf" + data if had_bom else data)
        left = sum(1 for l in text.split("\n") if re.match(r"^DIM\s+\w+\(\d+\)", l))
        print('stripped %s -> %s (INCLUDE "%s", %d DIM arrays left)'
              % (argv[2], argv[3], argv[4], left))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
