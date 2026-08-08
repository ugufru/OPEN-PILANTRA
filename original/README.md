# OPEN PILANTRA — the original

Everything in this directory is **Erico Patricio Monteiro's** work, released as
**FUED.NET**, 2026 — <https://fued.net/open-pilantra/>. It is kept here
unmodified as reference, together with the analysis of how it works.

See [`../NOTICE`](../NOTICE) for provenance and the terms this is mirrored
under. If you want to *build* the demo or write your own story with it, start
from [the repository README](../README.md).

| File | What it is |
| --- | --- |
| `OPIL-source.bas` | The complete ugBASIC source, 873 lines. |
| `OPIL-EN.dsk` | English build, RS-DOS disk image. |
| `OPIL_BR.dsk` | Brazilian Portuguese build — the original. |
| `OPEN PILANTRA.pdf` | The author's manual: setup, tooling, code structure. |
| `figures/` | Figures clipped from that manual. |

> One deliberate change: `OPIL-source.bas` carries the two-line fix to the
> dialogue phrase counter described under
> [The `z` counter](#the-z-counter) — the bug the author flagged in his own
> closing `REM`. Everything else is as published.

**The build does not read these files.** Dialogue comes from
`../story/dialogue.json` and graphics from `../art/*.png`; this source is
reference only. It still compiles standalone, which is what makes it the copy
worth offering upstream.

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
- **8 real colors, no artifacting.** No color fringing to design around, and the
  palette is identical on NTSC and PAL. (The *timing* is not — see the run
  notes above.)
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
IF c=10 THEN GOTO intro                                 :REM reset (see below)
```

Objects almost always hand off to dialogue; dialogue leans back toward a
cutscene. The result reads like edited film rather than a shuffle.

**The three `IF`s fall through within a single iteration.** They're sequential
tests, not an `ELSE` chain, so when the cutscene block sets `sc=1` the *very
next* `IF sc=1` fires in the same pass. One trip round the loop can therefore
play cutscene → dialogue → object back-to-back. That's almost certainly
deliberate — it's what produces multi-beat sequences instead of one isolated
scene per iteration — but it does mean `c` counts **iterations, not scenes**, so
`IF c=10 THEN GOTO intro` comes around considerably sooner than "ten scenes".

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

Confirmed empirically: a captured run put Isac on the right saying
"PROCEDURAL / OLD WAY", which is exactly the `DATA` pair at line 225 of
`OPIL-source.bas`.

### The `z` counter

The author's last line in the source flags a known bug: *"DEFEITO NO CONTADOR DE
FRASE, CORTA RAPIDO E NAO TERMINA"* — the phrase counter cuts short and doesn't
finish. Tracing `z` (with `RND(n)` returning `0..n-1`, confirmed by `ch1=RND(5)`
being tested against `IF ch1=0..4`):

| `z` initial | path through the scene loop | sentences |
| --- | --- | --- |
| 1 | `DEC`→0, print, `EXIT IF z=0` | 1 |
| 2–6 | counts down to 0 | 2–6 |
| 7 | `DEC`→6, print, `IF z=6` → 3 s wait, exit | 1 (solo) |

The arithmetic is sound — `z` initial *is* the sentence count. The symptom came
from two separate defects, both now fixed:

**"CORTA RAPIDO".** The original read:

```basic
z=RND(8)+1
IF z>7 THEN z=7
```

`RND(8)+1` gives 1..8, and the clamp folds 8 onto 7 — but **7 is the one-line
solo sentinel**, so it collected 2/8 of the probability mass. With `z=1` also
yielding one line, 3 in 8 dialogue scenes were a single sentence. Changing it to
`z=RND(7)+1` and dropping the clamp makes 1..7 uniform: single-line scenes fall
from 37.5% to 28.6%, and mean length rises from 2.88 to 3.14 sentences.

**"NAO TERMINA".** The scene loop was followed by:

```basic
LOOP
x=352:DO:POKE 1024+x,128:INC x:EXIT IF x=512:LOOP   :REM CLS dialog area
WAIT #1500 MILLISECONDS
CLS
```

The dialogue area was wiped *before* the closing wait, so the last sentence was
erased the instant the loop exited and the scene sat blank for 1.5 s. Every
other line got a reading beat; the final one got none. Removing that clear lets
the last line stand — and since `CLS` follows immediately, it was redundant
anyway.

![Patched build running](../docs/screens/zfix-verify.png)

*The fix running: a full-length scene reaching its last line.*

Note the *range* 1..6 is a tuning decision, not a defect — if scenes still feel
short, that's the knob, and it's the author's call.

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