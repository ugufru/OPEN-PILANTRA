# Contributing to OPEN PILANTRA

This describes how anyone — human or AI assistant — contributes to this
project. Read it before starting work. The same instructions apply whoever you
are; there is no separate track for automated contributors.

## Getting oriented
New here? Read the README and roadmap, skim the open issues, then pick up the
next thing. If you can't orient from the project's own docs, that's a
documentation gap worth surfacing — not a reason to invent context.

## Source of truth
This project's own documentation is canonical. For any question within the
project's scope, the in-repo docs are the authority — consult them before
searching the web. Don't keep project knowledge in private notes or assistant
memory files; if a fact matters, it belongs in the human-readable docs, kept
accurate. When docs are stale or wrong, fix the docs (or file an issue) rather
than routing around them.

## Before you start: file an issue
Work is tracked in `issues.jsonl` at the repo root — one JSON object per line,
with `id`, `summary`, `description`, `type`, `status`, `priority` and `file`.
Read it with `jq -c . issues.jsonl`. Status is one of `open`, `in-progress`,
`done`, `deferred` (worth doing, but not now — say what would trigger a
revisit) or `wontfix` (decided against — say why, and keep any findings that
would otherwise have to be re-derived).
- No substantive work without a matching issue. If none exists, propose one.
- Get the issue reviewed before starting — fairly documented, fairly considered.
- Record deferred alternatives with a revisit trigger ("try this if X"), and
  record rejected or forbidden paths with their rationale, so settled decisions
  aren't quietly relitigated.

## Doing the work
- **Don't invent — ask or verify.** Check any claim against the source first
  (grep the repo); when something can't be verified, ask rather than assert.
- **Build conservatively.** Write the minimum that satisfies the issue; make
  surgical changes that match existing style. Don't scaffold, restyle, or
  redesign unasked, and don't apply codebase reflexes to a repo that isn't one.
- **Stay in bounds.** Work within this project's tree; if a change seems to need
  something outside it, ask first.

## For automated / AI contributors
- **Bounded autonomy.** Proceed on your own through mechanical steps; stop for
  genuine decisions, visual or physical verification, and hard-to-reverse actions.
- **Be careful with side effects.** For repeated, expensive, or outward-facing
  actions (launching apps, hitting external services), act once, observe, then
  iterate — never fire them in a loop.

## Specific to this project

This repository holds someone else's demo plus a toolchain built around it.
Read [`NOTICE`](NOTICE) before reusing anything, and keep the two straight.

**Edit the right file.** The build reads `original/OPIL-source.bas` and never
writes it, re-supplying its `DATA` blocks and `DIM` arrays from elsewhere:

| Change | Goes in |
| --- | --- |
| Anything a character says | `story/dialogue.json` |
| Portraits, backgrounds, props | `art/*.png` |
| Code, timing, scene logic | `original/OPIL-source.bas` |

Editing the `DATA` blocks or `DIM` arrays still sitting in the `.bas` has no
effect — the build ignores them. `src/`, `generated/`, `build/` and
`.toolchain/` are generated and gitignored; never commit them.

**`original/` is the author's work.** It carries one deliberate change, the
phrase-counter fix. Keep further changes there small and upstreamable, and don't
tidy his code as a side effect of something else.

**Don't normalise the author's formatting.** The tools go out of their way to
preserve irregular whitespace, declaration order, and the `AS BYTE` form on the
two arrays that omit it. That isn't fussiness: `ugb` and `til` genuinely compile
to 16-bit arrays, and reordering declarations changes the emitted assembly.
Normalising also buries real changes in whitespace noise.

**Art PNGs are indexed.** One pixel per SG4 quadrant; the pixel value *is* the
palette index. An editor that saves back as RGB breaks the round trip. Whatever
the encoding can't represent is recorded in `art/manifest.json` — extend that
rather than inventing a second mechanism.

**Prove equivalence, don't eyeball it.** Where a change shouldn't alter the
program, show that: compile both ways and diff the generated assembly with
`; L:n` comments stripped. That is how the JSON and PNG pipelines were
validated, and it caught things a screenshot never would.

**Screen checks can be captured, but not judged, by a script.** The emulator
window can be grabbed from a script: `screencapture -x -o -l <window_id>
out.png` produces the same 640x512 frame as the shots in `docs/screens/`, and
issue 7 records the full procedure for sampling a running demo. So "there was
no way to check" is not a reason to skip visual verification. What a script
still cannot do is read the display as text (issue 14) or tell you whether what
it captured is correct, so anything that turns on how it looks is confirmed by
the maintainer. Say plainly what you did and didn't verify.

**A page is not tested until its JavaScript has run.** `issues.html` builds,
serves and returns HTTP 200 whether or not its script works, so none of those
things are evidence. Render it and look at the DOM:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --user-data-dir=/tmp/c \
  --virtual-time-budget=5000 --dump-dom http://127.0.0.1:8000/issues.html
```

Count what should be there, `<article class="card">` per issue, rather than
skimming for the absence of errors. Check both paths: served over HTTP the page
reads `issues.jsonl` live and shows no fallback note, while from `file://` the
fetch is blocked and the inlined snapshot renders with the note visible. That
note is what tells the two apart. This rule exists because the page shipped
once with a syntax error that made it render nothing at all, and every check
short of running it had passed.

## Finishing
- An issue isn't `done` until the change is tested and confirmed by a maintainer.
- Resolve related issues before pushing.
- Favor in-repo, diffable, vendor-neutral artifacts so the project stays
  comprehensible and reviewable no matter who contributed.
