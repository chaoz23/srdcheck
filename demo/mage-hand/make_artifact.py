#!/usr/bin/env python3
"""Generate the demo results page from results.jsonl + scenarios.jsonl."""

import html
import json
import pathlib
import sys

from srdcheck_mini import verdict

HERE = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path(sys.argv[1])

scenarios = [json.loads(l) for l in (HERE / "scenarios.jsonl").open()]
recs = [json.loads(l) for l in (HERE / "results.jsonl").open()]

CHIP = {
    "works": ("ok", "works"), "blocked": ("no", "blocked"),
    "gm-call": ("gm", "GM call"), "legal": ("ok", "legal · exit 0"),
    "illegal": ("no", "illegal · exit 1"),
    "cannot-adjudicate": ("gm", "cannot adjudicate · exit 2"),
}


def chip(kind):
    cls, label = CHIP[kind]
    return f'<span class="chip {cls}">{label}</span>'


def runs_html(sid, arm):
    rows = []
    for r in recs:
        if r["id"] == sid and r["arm"] == arm:
            a = r["answer"]
            rows.append(
                f'<div class="run">{chip(a["ruling"])}'
                f'<p class="mech">{html.escape(a.get("mechanics", ""))}</p>'
                f'<p class="narr">{html.escape(a.get("narration", ""))}</p></div>')
    return "\n".join(rows)


cards = []
for s in scenarios:
    v = verdict(s["proposal"])
    note = ""
    if s["id"] == "mh-5":
        note = ('<p class="note">The finding: every unrailed run presents '
                '"manipulate an object includes untying knots" as rules text. '
                'The railed runs make the same generous ruling — attributed as '
                'a ruling. The outcome didn\'t change; the claim to authority did.</p>')
    if s["id"] == "mh-8":
        note = ('<p class="note">The only run-to-run ruling inconsistency in '
                'all 48 records happened here, without rails.</p>')
    cards.append(f'''
<section class="card">
<p class="quote">&ldquo;{html.escape(s["nl"])}&rdquo;</p>
<p class="facts">{html.escape(s["facts"])}</p>
<div class="verdict">{chip(v["verdict"])}<span class="why">{html.escape(v["why"])}</span></div>
{note}
<div class="cols">
<div class="col"><h3>Without srdcheck</h3>{runs_html(s["id"], "no-rails")}</div>
<div class="col"><h3>With srdcheck</h3>{runs_html(s["id"], "rails")}</div>
</div>
</section>''')

page = '''<title>srdcheck — the Mage Hand test</title>
<style>
:root{--ground:#F7F8F5;--surface:#FFFFFF;--ink:#232827;--muted:#5D6764;--line:#DDE2DD;
--ok:#0E6B54;--ok-bg:#E3F2EC;--no:#A33230;--no-bg:#F9ECEB;--gm:#8A6209;--gm-bg:#F7EFDC;
--serif:"Iowan Old Style",Palatino,Georgia,serif;--mono:ui-monospace,"SF Mono",Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--ground:#151918;--surface:#1D2321;--ink:#E5EAE7;
--muted:#93A09A;--line:#313A36;--ok:#5CC7A0;--ok-bg:#12362B;--no:#E17F7A;--no-bg:#3C1D1B;
--gm:#DCAC45;--gm-bg:#372D12}}
:root[data-theme="dark"]{--ground:#151918;--surface:#1D2321;--ink:#E5EAE7;--muted:#93A09A;
--line:#313A36;--ok:#5CC7A0;--ok-bg:#12362B;--no:#E17F7A;--no-bg:#3C1D1B;--gm:#DCAC45;--gm-bg:#372D12}
:root[data-theme="light"]{--ground:#F7F8F5;--surface:#FFFFFF;--ink:#232827;--muted:#5D6764;
--line:#DDE2DD;--ok:#0E6B54;--ok-bg:#E3F2EC;--no:#A33230;--no-bg:#F9ECEB;--gm:#8A6209;--gm-bg:#F7EFDC}
body{background:var(--ground);color:var(--ink);font:16px/1.65 system-ui,sans-serif;margin:0}
.wrap{max-width:900px;margin:0 auto;padding:48px 24px 80px}
.eyebrow{font:12.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
h1{font:500 32px/1.15 var(--serif);margin:.35em 0 .3em;text-wrap:balance}
.dek{color:var(--muted);max-width:62ch;margin:0 0 28px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 36px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:10px;
padding:14px 18px;flex:1 1 180px}
.stat b{display:block;font:500 22px/1.2 var(--serif);font-variant-numeric:tabular-nums}
.stat span{font-size:13px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:22px 24px;margin:0 0 22px}
.quote{font:italic 500 19px/1.45 var(--serif);margin:0 0 4px;text-wrap:balance}
.facts{font-size:13.5px;color:var(--muted);margin:0 0 14px}
.verdict{display:flex;gap:10px;align-items:baseline;background:var(--ground);
border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:0 0 14px}
.verdict .why{font:12.5px/1.55 var(--mono);color:var(--muted)}
.chip{font:500 12px/1 var(--mono);letter-spacing:.04em;padding:4px 9px;border-radius:999px;
white-space:nowrap}
.chip.ok{background:var(--ok-bg);color:var(--ok)}
.chip.no{background:var(--no-bg);color:var(--no)}
.chip.gm{background:var(--gm-bg);color:var(--gm)}
.note{font-size:14px;border:1px solid var(--line);background:var(--ground);
border-radius:8px;padding:10px 14px;margin:0 0 14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media (max-width:640px){.cols{grid-template-columns:1fr}}
h3{font:500 13px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;
color:var(--muted);margin:0 0 10px}
.run{border-top:1px solid var(--line);padding:10px 0 6px}
.mech{font-size:13px;color:var(--muted);margin:8px 0 4px}
.narr{font:italic 14px/1.55 var(--serif);margin:0 0 4px}
h2{font:500 22px var(--serif);margin:40px 0 12px}
.foot{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);
padding-top:16px;margin-top:40px;max-width:72ch}
</style>
<div class="wrap">
<p class="eyebrow">srdcheck &middot; private staging &middot; 2026-07-16</p>
<h1>The Mage Hand test: one DM, with and without rails</h1>
<p class="dek">Eight player proposals for one squirrely cantrip. The same frontier model
adjudicates each three times as a free-form DM, and three times anchored by a deterministic
srdcheck verdict. 48 rulings total &mdash; every transcript below is real and unedited.</p>
<div class="stats">
<div class="stat"><b>36 / 36</b><span>agreement on codified rules &mdash; both arms, zero variance. Knowledge isn&rsquo;t the product.</span></div>
<div class="stat"><b>5 / 6</b><span>unrailed runs in the discretion zone claimed rules authority the text doesn&rsquo;t grant</span></div>
<div class="stat"><b>0 / 6</b><span>railed runs did &mdash; every one ruled as a GM, knowing it was ruling</span></div>
</div>
%%CARDS%%
<p class="foot">Model: Gemini 3.1 Pro (gemini-pro-latest), 2026-07-16. Verdicts:
srdcheck_mini prototype, rule atoms from the System Reference Document 5.2.1 &mdash;
this work includes material from the SRD 5.2.1 by Wizards of the Coast LLC, available at
dndbeyond.com/srd, licensed under CC-BY-4.0. srdcheck is unofficial and not affiliated
with or endorsed by Wizards of the Coast.</p>
</div>'''

OUT.write_text(page.replace("%%CARDS%%", "\n".join(cards)))
print(OUT, len(cards), "cards")
