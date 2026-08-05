# OPEN PILANTRA

A generative dialogue demo for the TRS-80 Color Computer, written in
[ugBASIC](https://ugbasic.iwashere.eu/) and compiled to native 6809.

> OPEN PILANTRA V0.3 — FUED.NET 2026

Ten characters meet in randomly chosen pairs, in randomly chosen locations, and
talk past each other in corporate-noir non-sequiturs. No two runs are the same.
The whole thing renders in **SG4 semigraphics** — 64×32 pixels, 8 colors, 512
bytes of screen RAM — and that single constraint is what makes every animation
in it affordable from a compiled BASIC.

## Contents

| File | What it is |
| --- | --- |
| `OPIL-source.bas` | ugBASIC source, 873 lines. The whole program. |
| `OPIL-EN.dsk` | English build, RS-DOS disk image. |
| `OPIL_BR.dsk` | Brazilian Portuguese build (the original). |
| `OPEN PILANTRA.pdf` | Design document / character art sheet. |
| `517989023_*.jpg` | Character portraits paired with their BR dialogue tables. |

## Running it

Requires [XRoar](https://www.6809.org.uk/xroar/). Both images are RS-DOS disks,
so you need a Disk BASIC machine:

```sh
xroar -m coco2b -load-fd0 OPIL-EN.dsk
```

Then at the `OK` prompt:

```basic
RUN"LOADER"
```

To skip the prompt, XRoar can type it for you:

```sh
xroar -m coco2b -load-fd0 OPIL-EN.dsk -type 'RUN"LOADER"\n'
```

### What's on the disk

Both images carry the same four-file ugBASIC build product:

| Entry | Type | Role |
| --- | --- | --- |
| `LOADER.BAS` | BASIC, tokenized | Stub that pulls in the machine-language segments |
| `P` | machine language | Main compiled 6809 binary |
| `P.00`, `P.01` | machine language | Overlay / data segments |

The BR and EN images are byte-identical in structure and differ only in segment
sizes — the English build is a translation of the `DATA` blocks, not a
re-architecture.

The demo loops forever: it plays 10 scenes, returns to the intro, and starts
over.

---

# How it works

## The core decision: everything is SG4 semigraphics

There is not a single `PMODE` in the source. Every visual — portraits,
backgrounds, props, the title card — is poked into the **32×16 text buffer at
$0400 (1024–1535)** as SG4 block characters.

An SG4 character byte is:

```
128 + (color × 16) + quadrant_bits
      ^ 0..7         ^ 0..15, one bit per 2×2 quadrant of the cell
```

You can read the palette straight out of the data arrays:

| Byte | Color | Byte | Color |
| --- | --- | --- | --- |
| `128` | black (blank cell) | `191` | red, solid |
| `143` | green, solid | `207` | white/buff, solid |
| `159` | yellow, solid | `223` | cyan, solid |
| `175` | blue, solid | `255` | orange, solid |

Partial values like `165`, `172`, `188` are the same colors with only some
quadrants lit — that's where the diagonal edges in the character art come from.

That one choice buys everything else:

- **512 bytes per screen**, against 6144 for PMODE 4. A full 64×28 background
  map is 896 bytes, so four backgrounds plus ten 15×10 portraits plus three
  props all fit in the program's data segment with room to spare.
- **8 real colors, no artifacting.** No color fringing to design around, and it
  looks identical on NTSC and PAL.
- **Redrawing is cheap enough to do from BASIC.** This is the whole game. At
  64×32 the art has to be bold silhouettes with one accent color per figure —
  and the art sheet leans into that rather than fighting it.

## Three animation techniques, each matched to its scene type

### 1. Partial-cell mouth animation — `dialog:` (line 671)

The smartest thing in the file. Portraits are drawn **once**, 15×10 tiles, via
`drawchrl` / `drawchrr` (lines 852, 861). During speech nothing redraws the
portrait. Instead, between 1 and 12 hardcoded addresses flip at 150 ms:

```basic
IF ch1=2 THEN:                       :REM ELEKTRA
    DO
        POKE 1255,188:WAIT #150 MILLISECONDS
        POKE 1255,191:WAIT #150 MILLISECONDS
        INC x:EXIT IF x=6
    LOOP
ENDIF
```

Elektra is a **single byte**. Captain Glord gets twelve, and reads as a whole
head turning:

```basic
POKE 1189,255:POKE 1190,156:POKE 1191,156:POKE 1192,128
POKE 1221,245:POKE 1254,252:POKE 1255,156:POKE 1256,152
POKE 1286,251:POKE 1287,157:POKE 1318,251:POKE 1319,157
```

The addresses are **literal, not computed** — no multiply, no array index, just
a store. That's what lets a compiled BASIC hold a steady 6–7 Hz mouth flap while
text is on screen. It is the classic sprite-animation economy — only touch the
cells that change — applied with real discipline.

### 2. Hardware-assisted scrolling — `cutscene:` (lines 617, 634)

`HSCROLL SCREEN LEFT` shifts the entire buffer, then the code pokes a single
fresh 14-tall column into the seam, read out of a 64-wide map:

```basic
HSCROLL SCREEN LEFT
DO
    IF sc=0 THEN POKE 1055+(y+1)*32,midl(x+y*64)
    ...
    POKE 1024+(y+1)*32,128
    INC y:EXIT IF y=14
LOOP
WAIT #50 MILLISECONDS
```

Fourteen pokes per frame at ~20 fps. Backgrounds are 64 columns wide and the
screen shows a 32-column window, so a scroll traverses exactly one screen-width
of new material. This is the same technique console hardware uses; it's
affordable here only because the buffer is 512 bytes.

The still (non-scrolling) variant picks a fixed mid-map window (`z=16`) instead,
and the scroll direction is itself randomized — `z=0` scrolls left, `z=32`
scrolls right, with a 10-in-15 chance of no scroll at all.

### 3. `CLS` as a full-screen flash — `object:` (line 505)

ugBASIC's `EMPTYTILE` sets the character `CLS` fills with. So a camera-flash cut
costs four `CLS` calls:

```basic
EMPTYTILE=175:CLS:WAIT 75 MILLISECONDS     :REM blue
EMPTYTILE=223:CLS:WAIT 75 MILLISECONDS     :REM cyan
EMPTYTILE=207:CLS:WAIT 400 MILLISECONDS    :REM white
EMPTYTILE=128:CLS                          :REM back to black
```

The safe scene runs the same idea vertically. "Lights down" and "lights up" are
not two sets of art — they're index arithmetic against one `safe()` sprite,
choosing whether a given screen row reads its lit row (`safe(x+(y+1)*19)`) or
the dark row (`safe(x)`):

```basic
POKE 1057+x+y*32,safe(x+(y+1)*19)          :REM DRAW SAFE
IF y>8 THEN POKE 1057+x+(y-11)*32,safe(x)  :REM DRAW DARK
```

Varying the `WAIT` between passes (30 ms down, 60 ms up, 80 ms down) gives the
sweep an ease that a constant delay wouldn't.

## The generative layer

### Scene director (lines 470–490)

A small weighted state machine, biased so the demo never gets monotonous:

```basic
IF sc=0 THEN: GOSUB cutscene : sc=RND(2)+1              :REM → dialog or object
IF sc=1 THEN: GOSUB dialog   : sc=RND(5)
              IF sc>=3 THEN sc=0                        :REM → prefers cutscene
IF sc=2 THEN: GOSUB object   : sc=RND(5)
              IF sc>=1 THEN sc=1                        :REM → prefers dialog
INC c
IF c=10 THEN GOTO intro                                 :REM reset every 10 scenes
```

Objects almost always hand off to dialogue; dialogue leans back toward a
cutscene. The result reads like edited film rather than a shuffle.

### Dialogue generation (lines 671–690)

```basic
ch1=RND(5):ch2=RND(5)   :REM left / right character
z=RND(8)+1              :REM scene length; >7 means solo, and clamps to 7
IF z>7 THEN z=7
w=RND(2)                :REM who speaks first
```

Lines are stored as `DATA` blocks behind per-character labels (`manot:`,
`johnt:`, `chavt:` …). Picking a random one is done by `RESTORE`-ing to the
label and reading forward a random number of pairs:

```basic
x=RND(20)*2
DO
    READ SAFE t1
    READ SAFE t2
    EXIT IF x=0
    x=x-2
LOOP
```

Five left characters × five right × 20 line-pairs each × random turn order and
scene length. The writing is deliberately non-sequitur, which is why it holds
together no matter what pairs up — every line is a plausible reply to every
other line.

### Speech vs. thought

`z=7` selects a **solo** scene: one character alone, thinking. The same
box-drawing routine runs, but three pokes swap the bubble tail from a speech
pointer to thought-bubble dots, and the mouth animation is suppressed
(`IF z<6 THEN` guards it):

```basic
IF z=6 THEN:POKE 1410,132:POKE 1411,133:POKE 1412,138   :REM DIALOG tail
ELSE:POKE 1411,133:POKE 1412,139:POKE 1444,141          :REM THOUGHT dots
ENDIF
```

Three bytes, entirely different narrative register. That's a good trade.

## Screen layout

```
row 0        unused — everything draws at (y+1)*32
rows 1..10   character portraits: left at col 0, right at col 16 (15×10 each)
rows 1..14   backgrounds and props
rows 12..15  dialogue box, cleared by poking 128 over offsets 352..511
```

Left portraits go to `1024+x+y*32`, right to `1040+x+y*32` — the `+16` is the
whole difference between the two draw routines.

---

# Known issues and unfinished work

Tracked in `issues.jsonl`. Highlights:

- **The sentence counter is broken.** The author's own last line in the source:
  *"DEFEITO NO CONTADOR DE FRASE, CORTA RAPIDO E NAO TERMINA"* — the phrase
  counter cuts off fast and doesn't finish. `DEC z` at the top of the scene loop
  interacts badly with the `EXIT IF z=0` at the bottom.
- **Three of four cutscene categories are dead.** Line 587 is
  `z=0 :'z=RND(3)` — the randomizer is commented out, so only the skyline
  branch ever runs. The four *backgrounds* (`midl`, `dock`, `citi`, `spac`) are
  all reachable via the `sc` chooser inside that branch; it's the three other
  scene categories the structure implies that were never written.
- **`object:` has room for more props.** Only the briefcase and safe exist;
  there's a conspicuous block of blank lines where more were planned.
- **Portrait arrays are over-dimensioned.** `DIM mano(176)` etc., but the draw
  loop only reaches index `14+9*16 = 158`.

## Credits

Original by FUED.NET, 2026. Built with ugBASIC.
