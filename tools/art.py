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
    r"^DIM\s+(\w+)\((\d+)\)\s*(?:AS\s+BYTE\s*)?=#\{([^}]*)\}", re.M)


def parse_arrays(bas_path):
    """Return {name: [byte, ...]} for every DIM byte array in the source."""
    text = Path(bas_path).read_text(encoding="utf-8-sig").replace("_\n", "")
    arrays = {}
    for m in ARRAY_RE.finditer(text):
        name, declared, body = m.group(1), int(m.group(2)), m.group(3)
        values = [v.strip() for v in body.split(",") if v.strip()]
        nums = [int(v[1:], 16) if v.startswith("$") else int(v) for v in values]
        if len(nums) != declared:
            raise SystemExit(
                "%s: DIM says %d bytes, found %d" % (name, declared, len(nums))
            )
        arrays[name] = nums
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
        if byte < 128:
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
            "'visible_width' is how many columns the demo actually draws."
        ),
        "arrays": {},
    }

    unknown = sorted(set(arrays) - set(STRIDES))
    if unknown:
        raise SystemExit("no stride known for: %s" % ", ".join(unknown))

    for name in sorted(arrays):
        stride = STRIDES[name]
        nums = arrays[name]
        if len(nums) % stride:
            raise SystemExit(
                "%s: %d bytes is not a multiple of stride %d"
                % (name, len(nums), stride)
            )
        img, literals, rows = to_png(nums, stride)
        img.save(out / ("%s.png" % name))
        entry = {"stride": stride, "rows": rows, "bytes": len(nums)}
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


def main(argv):
    if len(argv) == 4 and argv[1] == "extract":
        extract(argv[2], argv[3])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
