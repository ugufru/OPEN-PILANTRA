#!/usr/bin/env python3
"""Render issues.jsonl as a single self-contained issues.html.

issues.jsonl stays the source of truth. This only ever reads it.

    render  <jsonl> <out.html>      the browsable view

The output has no external dependencies and reads nothing at runtime: each issue
is rendered into the markup here, so the page works from file:// with no server
and no network. A fetch of a local .jsonl would be blocked by CORS, which is why
the data is baked in rather than loaded.

The page is committed, so it can be read from a clone. That means it can fall
behind: run `make issues` after editing the tracker and commit the two together.
"""

import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Order matters: it drives the sort, the filter bar and the colour assignment.
STATUS_ORDER = ["open", "in-progress", "done", "deferred", "wontfix"]
PRIORITY_ORDER = ["high", "medium", "low"]

# `original/OPIL-source.bas:471-492` and bare `tools/art.py` both get linked to
# nothing, but they read as code and are worth setting in a monospace face.
PATH_RE = re.compile(r"\b((?:[\w.-]+/)*[\w.-]+\.(?:jsonl|json|bas|py|md|html|dsk|png))(:\d+(?:-\d+)?)?")
ISSUE_RE = re.compile(r"\bissues?\s+(\d+(?:\s*,\s*\d+)*(?:\s+and\s+\d+)?)", re.I)


def field(issue, *names, default=""):
    """Tolerate the field-name drift the tracker documents (summary/title)."""
    for n in names:
        if issue.get(n) not in (None, ""):
            return issue[n]
    return default


def rank(value, order):
    return order.index(value) if value in order else len(order)


def markup(text):
    """Escape, then set file paths in monospace and keep paragraph breaks."""
    out = []
    for para in html.escape(text).split("\n\n"):
        para = PATH_RE.sub(lambda m: "<code>%s</code>" % m.group(0), para)
        out.append("<p>%s</p>" % para.replace("\n", "<br>"))
    return "".join(out)


def render(issues):
    for i in issues:
        i["_summary"] = field(i, "summary", "title", default="(untitled)")
        i["_tags"] = field(i, "tags", "labels", default=[])
    issues.sort(key=lambda i: (rank(i.get("status"), STATUS_ORDER),
                               rank(i.get("priority"), PRIORITY_ORDER),
                               i.get("id", 0)))

    counts = Counter(i.get("status", "?") for i in issues)
    tags = sorted({t for i in issues for t in i["_tags"]})
    types = sorted({i.get("type", "?") for i in issues})

    cards = []
    for i in issues:
        status, priority = i.get("status", "?"), i.get("priority", "?")
        chips = "".join(
            '<span class="chip %s">%s</span>' % (cls, html.escape(str(v)))
            for cls, v in (("st-" + status, status), ("pr-" + priority, priority),
                           ("ty", i.get("type", "?")))
        )
        tagchips = "".join('<span class="tag">%s</span>' % html.escape(t) for t in i["_tags"])
        cards.append(
            '<article class="card" data-status="{status}" data-priority="{priority}" '
            'data-type="{type}" data-tags="{tagattr}" data-id="{id}" id="i{id}">'
            '<header><button class="row" aria-expanded="false">'
            '<span class="id">#{id}</span>'
            '<span class="summary">{summary}</span>'
            '<span class="chips">{chips}</span>'
            '<span class="caret" aria-hidden="true"></span>'
            "</button></header>"
            '<div class="body" hidden><div class="desc">{desc}</div>'
            '<footer>{tagchips}<span class="meta"><code>{file}</code> &middot; '
            "created {created} &middot; updated {updated}</span></footer></div></article>".format(
                status=html.escape(status), priority=html.escape(priority),
                type=html.escape(str(i.get("type", "?"))),
                tagattr=html.escape(" ".join(i["_tags"])), id=i.get("id", 0),
                summary=html.escape(i["_summary"]), chips=chips,
                desc=markup(field(i, "description", default="(no description)")),
                tagchips=tagchips, file=html.escape(str(i.get("file", "-"))),
                created=html.escape(str(i.get("created", "?"))),
                updated=html.escape(str(i.get("updated", "?"))),
            )
        )

    status_buttons = "".join(
        '<button class="pill" data-filter="status" data-value="%s">%s <span class="n">%d</span></button>'
        % (s, s, counts[s]) for s in STATUS_ORDER if counts[s]
    )
    type_buttons = "".join(
        '<button class="pill" data-filter="type" data-value="%s">%s</button>' % (t, html.escape(t))
        for t in types
    )
    tag_buttons = "".join(
        '<button class="pill" data-filter="tag" data-value="%s">%s</button>' % (t, html.escape(t))
        for t in tags
    )

    return TEMPLATE.format(
        cards="\n".join(cards), status_buttons=status_buttons,
        type_buttons=type_buttons, tag_buttons=tag_buttons,
        total=len(issues), open_n=counts["open"] + counts["in-progress"],
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OPEN PILANTRA issues</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #fbfaf7; --panel: #fff; --ink: #1b1a17; --dim: #6b6862; --line: #e3ded4;
  --accent: #8a4b2a; --accent-ink: #fff;
  --open: #b4541f; --inprog: #8a6d1f; --done: #3f6b3a; --defer: #4a5a75; --wont: #6b6862;
  --high: #a8322a; --med: #8a6d1f; --low: #6b6862;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16151a; --panel: #1e1d23; --ink: #ece8e1; --dim: #9b968d; --line: #32303a;
    --accent: #d98a5a; --accent-ink: #16151a;
    --open: #e08b52; --inprog: #d4b95e; --done: #8fc182; --defer: #93aad6; --wont: #9b968d;
    --high: #e5776c; --med: #d4b95e; --low: #9b968d;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
}}
.wrap {{ max-width: 60rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
h1 {{ font-size: 1.5rem; margin: 0 0 .2rem; letter-spacing: -.01em; }}
.lede {{ color: var(--dim); margin: 0 0 1.5rem; font-size: .9rem; }}
.controls {{
  position: sticky; top: 0; z-index: 5; background: var(--bg);
  padding: .75rem 0; border-bottom: 1px solid var(--line); margin-bottom: 1.25rem;
}}
#q {{
  width: 100%; padding: .6rem .75rem; font: inherit; color: var(--ink);
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
}}
#q:focus {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
.pills {{ display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .6rem; align-items: center; }}
.pills .label {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .06em;
  color: var(--dim); margin-right: .15rem; }}
.pill {{
  font: inherit; font-size: .8rem; padding: .2rem .6rem; cursor: pointer;
  background: var(--panel); color: var(--ink);
  border: 1px solid var(--line); border-radius: 999px;
}}
.pill:hover {{ border-color: var(--accent); }}
.pill[aria-pressed="true"] {{ background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }}
.pill .n {{ opacity: .6; font-variant-numeric: tabular-nums; }}
.bar {{ display: flex; gap: .75rem; align-items: center; margin-top: .6rem;
  font-size: .8rem; color: var(--dim); }}
.bar button {{ font: inherit; background: none; border: 0; color: var(--accent);
  cursor: pointer; padding: 0; text-decoration: underline; }}
#count {{ margin-right: auto; font-variant-numeric: tabular-nums; }}
.card {{ background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; margin-bottom: .5rem; overflow: hidden; }}
.card:target {{ outline: 2px solid var(--accent); }}
.row {{
  width: 100%; display: flex; gap: .7rem; align-items: baseline; text-align: left;
  font: inherit; color: inherit; background: none; border: 0;
  padding: .7rem .9rem; cursor: pointer;
}}
.row:hover {{ background: color-mix(in srgb, var(--accent) 7%, transparent); }}
.id {{ color: var(--dim); font-variant-numeric: tabular-nums; font-size: .85rem; min-width: 2.2rem; }}
.summary {{ flex: 1; font-weight: 550; }}
.chips {{ display: flex; gap: .3rem; flex-wrap: wrap; }}
.chip {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .04em;
  padding: .1rem .45rem; border-radius: 4px; border: 1px solid currentColor; white-space: nowrap; }}
.st-open {{ color: var(--open); }} .st-in-progress {{ color: var(--inprog); }}
.st-done {{ color: var(--done); }} .st-deferred {{ color: var(--defer); }}
.st-wontfix {{ color: var(--wont); }}
.pr-high {{ color: var(--high); }} .pr-medium {{ color: var(--med); }} .pr-low {{ color: var(--low); }}
.ty {{ color: var(--dim); }}
.caret {{ width: .55rem; height: .55rem; border-right: 2px solid var(--dim);
  border-bottom: 2px solid var(--dim); transform: rotate(45deg); transition: transform .15s; }}
.row[aria-expanded="true"] .caret {{ transform: rotate(-135deg); }}
.body {{ padding: 0 .9rem .9rem; border-top: 1px solid var(--line); }}
.desc {{ max-width: 62ch; }}
.desc p {{ margin: .8rem 0; }}
code {{ font: .87em ui-monospace, SFMono-Regular, Menlo, monospace;
  background: color-mix(in srgb, var(--ink) 7%, transparent);
  padding: .05em .3em; border-radius: 3px; }}
footer {{ display: flex; gap: .4rem; flex-wrap: wrap; align-items: center;
  margin-top: .9rem; padding-top: .7rem; border-top: 1px dashed var(--line); }}
.tag {{ font-size: .72rem; color: var(--dim); border: 1px solid var(--line);
  border-radius: 999px; padding: .05rem .45rem; }}
.meta {{ margin-left: auto; font-size: .75rem; color: var(--dim); }}
.empty {{ color: var(--dim); padding: 2rem 0; text-align: center; }}
mark {{ background: color-mix(in srgb, var(--accent) 30%, transparent); color: inherit; }}
@media (max-width: 40rem) {{
  .row {{ flex-wrap: wrap; }} .summary {{ flex-basis: 100%; order: 2; }}
  .chips {{ order: 3; }} .meta {{ margin-left: 0; }}
}}
</style>
</head>
<body>
<div class="wrap">
<h1>OPEN PILANTRA issues</h1>
<p class="lede">{total} issues, {open_n} of them still open.
Generated from <code>issues.jsonl</code>, which stays the source of truth.
Run <code>make issues</code> to refresh.</p>

<div class="controls">
  <input id="q" type="search" placeholder="Search summaries and descriptions..." autocomplete="off">
  <div class="pills"><span class="label">status</span>{status_buttons}</div>
  <div class="pills"><span class="label">type</span>{type_buttons}</div>
  <div class="pills"><span class="label">tag</span>{tag_buttons}</div>
  <div class="bar">
    <span id="count"></span>
    <button id="expand">expand all</button>
    <button id="collapse">collapse all</button>
    <button id="reset">clear filters</button>
  </div>
</div>

<main id="list">
{cards}
<p class="empty" id="empty" hidden>Nothing matches those filters.</p>
</main>
</div>

<script>
(function () {{
  var cards = [].slice.call(document.querySelectorAll('.card'));
  var pills = [].slice.call(document.querySelectorAll('.pill'));
  var q = document.getElementById('q');
  var count = document.getElementById('count');
  var empty = document.getElementById('empty');
  var active = {{ status: [], type: [], tag: [] }};

  // Remember the view per browser. Never load-bearing: any failure just means
  // the page opens unfiltered.
  function save() {{
    try {{
      localStorage.setItem('opil-issues', JSON.stringify({{ active: active, q: q.value }}));
    }} catch (e) {{}}
  }}
  function load() {{
    try {{
      var s = JSON.parse(localStorage.getItem('opil-issues') || '{{}}');
      if (s.active) active = s.active;
      if (s.q) q.value = s.q;
    }} catch (e) {{}}
  }}

  function toggle(list, value) {{
    var i = list.indexOf(value);
    if (i === -1) list.push(value); else list.splice(i, 1);
  }}

  function apply() {{
    var needle = q.value.trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {{
      var ok =
        (!active.status.length || active.status.indexOf(card.dataset.status) !== -1) &&
        (!active.type.length || active.type.indexOf(card.dataset.type) !== -1) &&
        (!active.tag.length || active.tag.some(function (t) {{
          return card.dataset.tags.split(' ').indexOf(t) !== -1;
        }})) &&
        (!needle || card.textContent.toLowerCase().indexOf(needle) !== -1);
      card.hidden = !ok;
      if (ok) shown++;
    }});
    empty.hidden = shown !== 0;
    count.textContent = shown + ' of ' + cards.length + ' shown';
    pills.forEach(function (p) {{
      p.setAttribute('aria-pressed', active[p.dataset.filter].indexOf(p.dataset.value) !== -1);
    }});
    save();
  }}

  pills.forEach(function (p) {{
    p.addEventListener('click', function () {{
      toggle(active[p.dataset.filter], p.dataset.value);
      apply();
    }});
  }});
  q.addEventListener('input', apply);
  document.getElementById('reset').addEventListener('click', function () {{
    active = {{ status: [], type: [], tag: [] }};
    q.value = '';
    apply();
  }});

  function setOpen(card, open) {{
    card.querySelector('.row').setAttribute('aria-expanded', open);
    card.querySelector('.body').hidden = !open;
  }}
  cards.forEach(function (card) {{
    card.querySelector('.row').addEventListener('click', function () {{
      setOpen(card, card.querySelector('.body').hidden);
    }});
  }});
  document.getElementById('expand').addEventListener('click', function () {{
    cards.forEach(function (c) {{ if (!c.hidden) setOpen(c, true); }});
  }});
  document.getElementById('collapse').addEventListener('click', function () {{
    cards.forEach(function (c) {{ setOpen(c, false); }});
  }});

  // "/" focuses search, the way most trackers behave.
  document.addEventListener('keydown', function (e) {{
    if (e.key === '/' && document.activeElement !== q) {{ e.preventDefault(); q.focus(); }}
    if (e.key === 'Escape' && document.activeElement === q) {{ q.value = ''; apply(); }}
  }});

  load();
  apply();
  // A #i8 in the URL should win over a remembered filter that would hide it.
  if (location.hash) {{
    var target = document.querySelector(location.hash);
    if (target && target.classList.contains('card')) {{
      target.hidden = false;
      setOpen(target, true);
      target.scrollIntoView();
    }}
  }}
}})();
</script>
</body>
</html>
"""


def main(argv):
    if len(argv) == 4 and argv[1] == "render":
        issues = [json.loads(l) for l in Path(argv[2]).read_text().splitlines() if l.strip()]
        Path(argv[3]).write_text(render(issues))
        counts = Counter(i.get("status", "?") for i in issues)
        print("rendered %d issues (%d open) -> %s"
              % (len(issues), counts["open"] + counts["in-progress"], argv[3]))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
