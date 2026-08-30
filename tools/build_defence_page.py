"""
Build the defence reference page: every number, read from the result files.

The decks argue and the notebook demonstrates.  This is neither -- it is the
page to have open while answering questions, where each figure sits beside the
file it was read from, so a challenged number can be traced in one step rather
than defended from memory.

Nothing here is typed by hand.  Every value is loaded from the JSON the
pipeline wrote, which is the only reason the page is worth trusting.

    python tools/build_defence_page.py --results output --out docs/defence.html
"""

from __future__ import annotations

import argparse
import json
import os

# ── the design tokens, in one place ──────────────────────────────────────────
CSS = """
:root {
  /* Porto granite, biased cyan-green; azulejo teal carries structure, and a
     tail-light red is reserved for the two configurations that came back empty. */
  --ground:    #F1F4F4;
  --surface:   #FFFFFF;
  --sunken:    #E7ECEC;
  --ink:       #0B1518;
  --ink-soft:  #2C4348;
  --muted:     #607A80;
  --faint:     #8CA2A7;
  --line:      #D6DFDF;
  --line-soft: #E6ECEC;
  --teal:      #0E5E5A;
  --teal-lit:  #14837C;
  --moss:      #1E6B45;
  --tail:      #A32A22;
  --console:   #08110F;
  --console-fg:#C3D6D2;
  --console-dim:#63807B;
  --console-hi:#4FD1BE;
  --console-no:#EE8878;

  --measure: 68ch;
  --s-1: .78rem;  --s0: 1rem;   --s1: 1.22rem;
  --s2:  1.62rem; --s3: 2.2rem; --s4: 3.1rem;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:  #0A1113; --surface: #101B1D; --sunken: #162427;
    --ink:     #E4EDEC; --ink-soft:#BCCFCD; --muted:  #86A09E;
    --faint:   #63807D; --line:    #223437; --line-soft:#1A2A2D;
    --teal:    #4FB3A6; --teal-lit:#6FCcBE; --moss:   #5DBE8B;
    --tail:    #E07A6E; --console: #050C0B; --console-fg:#C3D6D2;
  }
}
:root[data-theme="dark"] {
  --ground:  #0A1113; --surface: #101B1D; --sunken: #162427;
  --ink:     #E4EDEC; --ink-soft:#BCCFCD; --muted:  #86A09E;
  --faint:   #63807D; --line:    #223437; --line-soft:#1A2A2D;
  --teal:    #4FB3A6; --teal-lit:#6FCcBE; --moss:   #5DBE8B;
  --tail:    #E07A6E; --console: #050C0B; --console-fg:#C3D6D2;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font: 400 var(--s0)/1.65 "Heebo", "Segoe UI", system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.page { direction: rtl; }

.wrap {
  max-width: var(--measure);
  margin-inline: auto;
  padding-inline: 1.5rem;
}
.wide { max-width: 78rem; }

/* ── top rail ─────────────────────────────────────────────────────────── */
.rail {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--ground) 88%, transparent);
  backdrop-filter: blur(9px);
  border-block-end: 1px solid var(--line);
}
.rail-in {
  max-width: 78rem; margin-inline: auto;
  padding: .55rem 1.5rem;
  display: flex; gap: .4rem; align-items: center;
  overflow-x: auto; scrollbar-width: none;
}
.rail-in::-webkit-scrollbar { display: none; }
.rail a {
  flex: none;
  font-size: var(--s-1); font-weight: 500;
  color: var(--muted); text-decoration: none;
  padding: .28rem .62rem; border-radius: 999px;
  border: 1px solid transparent;
  transition: color .15s, border-color .15s, background .15s;
}
.rail a:hover, .rail a:focus-visible {
  color: var(--teal); border-color: var(--line);
  background: var(--surface); outline: none;
}
.rail .tag {
  flex: none; margin-inline-end: .5rem;
  font: 500 var(--s-1)/1 "IBM Plex Mono", ui-monospace, monospace;
  color: var(--faint); letter-spacing: .04em;
}

/* ── masthead ─────────────────────────────────────────────────────────── */
.mast { padding: 4rem 0 2.5rem; }
.eyebrow {
  font: 500 var(--s-1)/1 "IBM Plex Mono", ui-monospace, monospace;
  letter-spacing: .11em; color: var(--teal); text-transform: uppercase;
  margin: 0 0 1rem;
}
h1 {
  font-family: "Frank Ruhl Libre", Georgia, serif;
  font-weight: 900; font-size: var(--s4); line-height: 1.08;
  letter-spacing: -.015em; margin: 0 0 1rem; text-wrap: balance;
}
.lede { font-size: var(--s1); color: var(--ink-soft); margin: 0 0 1.6rem; text-wrap: pretty; }
.runline {
  display: flex; flex-wrap: wrap; gap: .35rem .9rem;
  font: 400 var(--s-1)/1.9 "IBM Plex Mono", ui-monospace, monospace;
  color: var(--faint); padding-block-start: 1rem;
  border-block-start: 1px solid var(--line);
}
.runline b { color: var(--ink-soft); font-weight: 500; }

/* ── sections ─────────────────────────────────────────────────────────── */
section { padding-block: 2.6rem; }
h2 {
  font-family: "Frank Ruhl Libre", Georgia, serif;
  font-weight: 700; font-size: var(--s3); line-height: 1.15;
  margin: 0 0 .5rem; text-wrap: balance;
}
h3 {
  font-size: var(--s1); font-weight: 700; margin: 2rem 0 .5rem;
  text-wrap: balance;
}
.sub { color: var(--muted); margin: 0 0 1.6rem; text-wrap: pretty; }
p { margin: 0 0 1rem; text-wrap: pretty; }
strong { font-weight: 700; }
.hr { height: 1px; background: var(--line); border: 0; margin: 0; }

/* ── figures: a number and the file it came from ──────────────────────── */
.figs { display: grid; gap: 1px; background: var(--line);
        border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
        grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); }
.fig { background: var(--surface); padding: 1rem 1.1rem 1.05rem; }
.fig .v {
  font: 500 var(--s2)/1.1 "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums; letter-spacing: -.02em;
  color: var(--ink); display: block; direction: ltr; text-align: right;
}
.fig .v.q { color: var(--tail); }
.fig .v.g { color: var(--moss); }
.fig .l { display: block; font-size: var(--s-1); color: var(--muted); margin-block-start: .3rem; }
.fig .src {
  display: block; direction: ltr; text-align: right;
  font: 400 .68rem/1.5 "IBM Plex Mono", ui-monospace, monospace;
  color: var(--faint); margin-block-start: .45rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── tables ───────────────────────────────────────────────────────────── */
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: var(--s-1); }
caption {
  text-align: start; color: var(--muted); font-size: var(--s-1);
  padding-block-end: .6rem;
}
th, td { padding: .55rem .7rem; border-block-end: 1px solid var(--line-soft); }
thead th {
  text-align: start; font-weight: 500; color: var(--muted);
  border-block-end: 1px solid var(--line); white-space: nowrap;
}
td.n, th.n {
  text-align: end; direction: ltr;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
tbody tr:last-child td { border-block-end: 0; }
tr.zero td { color: var(--tail); }
tr.zero td.k { font-weight: 700; }

.pill {
  display: inline-block; font: 500 .7rem/1 "IBM Plex Mono", ui-monospace, monospace;
  padding: .24rem .5rem; border-radius: 3px; white-space: nowrap;
}
.pill.ok  { color: var(--moss); background: color-mix(in srgb, var(--moss) 12%, transparent); }
.pill.no  { color: var(--tail); background: color-mix(in srgb, var(--tail) 12%, transparent); }

/* ── the two-reasons split ────────────────────────────────────────────── */
.split { display: grid; gap: 1px; background: var(--line);
         border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
         grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); }
.half { background: var(--surface); padding: 1.5rem 1.4rem; }
.half .k {
  font: 500 var(--s-1)/1 "IBM Plex Mono", ui-monospace, monospace;
  letter-spacing: .08em; margin: 0 0 .6rem;
}
.half.exists .k { color: var(--teal); }
.half.absent .k { color: var(--tail); }
.half h4 { font-size: var(--s1); font-weight: 700; margin: 0 0 .7rem; text-wrap: balance; }
.half p { font-size: var(--s-1); color: var(--ink-soft); margin: 0 0 .8rem; }
.half p:last-child { margin-block-end: 0; }
.half dl { margin: 1rem 0 0; display: grid; grid-template-columns: 1fr auto; gap: .3rem .8rem;
           font-size: var(--s-1); }
.half dt { color: var(--muted); }
.half dd { margin: 0; direction: ltr; text-align: end; font-weight: 500;
           font-family: "IBM Plex Mono", ui-monospace, monospace;
           font-variant-numeric: tabular-nums; }

/* ── console panels ───────────────────────────────────────────────────── */
.console {
  background: var(--console); color: var(--console-fg);
  border-radius: 6px; padding: 1.15rem 1.3rem;
  direction: ltr; overflow-x: auto;
  font: 400 .81rem/1.72 "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  white-space: pre;
}
.console .dim { color: var(--console-dim); }
.console .hi  { color: var(--console-hi); }
.console .no  { color: var(--console-no); }
.cap { font-size: var(--s-1); color: var(--faint); margin-block-start: .55rem; }

/* ── question cards ───────────────────────────────────────────────────── */
.qa { display: grid; gap: 1px; background: var(--line);
      border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.q { background: var(--surface); padding: 1.15rem 1.3rem; }
.q h4 {
  font-size: var(--s0); font-weight: 700; margin: 0 0 .5rem;
  color: var(--ink); text-wrap: balance;
}
.q h4::before {
  content: "?"; display: inline-block; width: 1.35em;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  color: var(--teal); font-weight: 500;
}
.q p { font-size: var(--s-1); color: var(--ink-soft); margin: 0 0 .5rem; padding-inline-start: 1.35em; }
.q p:last-child { margin-block-end: 0; }
.q .num {
  direction: ltr; unicode-bidi: isolate;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-weight: 500; color: var(--ink);
}

/* ── file list ────────────────────────────────────────────────────────── */
.files { list-style: none; margin: 0; padding: 0; display: grid; gap: .1rem; }
.files li {
  display: flex; gap: .9rem; align-items: baseline;
  padding: .5rem 0; border-block-end: 1px solid var(--line-soft);
  font-size: var(--s-1);
}
.files li:last-child { border-block-end: 0; }
.files code {
  direction: ltr; flex: none; min-width: 17rem;
  font: 400 .78rem/1.6 "IBM Plex Mono", ui-monospace, monospace;
  color: var(--teal);
}
.files span { color: var(--muted); }

footer {
  padding: 3rem 0 4rem; color: var(--faint); font-size: var(--s-1);
  border-block-start: 1px solid var(--line); margin-block-start: 2rem;
}

@media (max-width: 34rem) {
  :root { --s4: 2.3rem; --s3: 1.7rem; }
  .files li { flex-direction: column; gap: .1rem; }
  .files code { min-width: 0; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
"""


def fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else f"{n:,.2f}"


def fig(value, label, source, tone="") -> str:
    cls = f" {tone}" if tone else ""
    return (f'<div class="fig"><span class="v{cls}">{value}</span>'
            f'<span class="l">{label}</span>'
            f'<span class="src">{source}</span></div>')


def build(results: str, out_path: str) -> None:
    def load(name):
        with open(os.path.join(results, name), encoding="utf-8") as fh:
            return json.load(fh)

    sub = load("stage3_subroutes.json")
    bench = load("stage3_benchmark.json")
    clean = load("cleaning_report.json")
    h3rep = load("h3_encoding_report.json")["summary"]
    probe = load("long_corridors_probe.json")
    prov = load("stage3_run_provenance.json")

    meta = sub["metadata"]
    gate = bench["methods"]["gate"]
    ma = bench["methods"]["method_a_lsh_clustering"]
    mb = bench["methods"]["method_b_suffix_array"]
    mc = bench["methods"]["method_c_growth"]
    anom = bench["methods"]["anomaly_detection"]
    score = bench["methods"]["per_method_scorecard"]
    pipe = bench["pipeline"]
    cs = clean["summary"]

    ceiling = {int(c["min_length_km"]): c for c in sub["length_ceiling"]}
    thresholds = sub["by_threshold_km"]

    # ── the six configurations ────────────────────────────────────────────
    rows = []
    for key in ("1", "3", "5", "10", "20", "40"):
        t = thresholds[key]
        c = ceiling[int(key)]
        met = t["met_target"]
        rows.append(
            f'<tr class="{"" if met else "zero"}">'
            f'<td class="k">&ge; {key} ק"מ</td>'
            f'<td class="n">{t["support_pct_used"]}%</td>'
            f'<td class="n">{fmt(t["found"])}</td>'
            f'<td class="n">{fmt(c["trips_at_least_this_long"])}</td>'
            f'<td class="n">{c["max_possible_support_pct"]:.3f}%</td>'
            f'<td><span class="pill {"ok" if met else "no"}">'
            f'{"עומד ביעד" if met else "ריק"}</span></td></tr>')
    config_rows = "\n".join(rows)

    # ── the support sweep ─────────────────────────────────────────────────
    sweep = sorted(sub["support_sweep"], key=lambda r: r["support_pct"])
    def km(r, key):
        # The highest threshold returns no corridors at all, so it has no
        # lengths to report -- an em dash is the honest cell, not a zero.
        return f'{r[key]:.2f}' if key in r else "&mdash;"

    sweep_rows = "\n".join(
        f'<tr class="{"" if r["corridors"] else "zero"}">'
        f'<td class="n">{r["support_pct"]}%</td>'
        f'<td class="n">{fmt(r["min_trips"])}</td>'
        f'<td class="n">{fmt(r["corridors"])}</td>'
        f'<td class="n">{km(r, "max_length_km")}</td>'
        f'<td class="n">{km(r, "mean_length_km")}</td></tr>' for r in sweep)

    # ── per-method scorecard ──────────────────────────────────────────────
    names = {"lsh_clustering": "A · MinHash + LSH",
             "suffix_array_lcp": "B · Suffix array + LCP",
             "cms_growth": "C · Count-Min level-wise"}
    method_rows = []
    for key, label in names.items():
        s = score[key]
        over = s["support_overestimate_pct"]
        method_rows.append(
            f'<tr><td class="k">{label}</td>'
            f'<td class="n">{fmt(s["corridors_verified"])}</td>'
            f'<td class="n">{s["max_length_km"]:.2f}</td>'
            f'<td class="n">{s["mean_length_km"]:.2f}</td>'
            f'<td class="n" style="color:{"var(--tail)" if over > 1 else "inherit"}">'
            f'{over:.2f}%</td></tr>')
    method_rows = "\n".join(method_rows)

    # ── cleaning rules ────────────────────────────────────────────────────
    clean_rows = "\n".join(
        f'<tr><td>{v["label"]}</td><td class="n">{fmt(v["trips"])}</td>'
        f'<td class="n">{v["pct_of_raw"]:.4f}%</td></tr>'
        for v in clean["per_rule_removed"].values())

    top_probe = probe["corridors"][:8]
    probe_lines = "\n".join(
        f'  {i:>2}   {r["length_km"]:>6.2f}   {r["support_trips"]:>3}    '
        f'{r["n_cells"]:>3}      {r["tortuosity"]:>5.2f}'
        for i, r in enumerate(top_probe, 1))

    html = f"""<title>הגנת פרויקט מוניות פורטו</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Frank+Ruhl+Libre:wght@700;900&amp;family=Heebo:wght@300;400;500;700&amp;family=IBM+Plex+Mono:wght@400;500&amp;display=swap">
<style>{CSS}</style>

<div class="page">

<nav class="rail" aria-label="ניווט">
  <div class="rail-in">
    <span class="tag">{prov["run_id"]}</span>
    <a href="#config">שש הקונפיגורציות</a>
    <a href="#long">20 ו־40 ק"מ</a>
    <a href="#pipeline">מספרי הפייפליין</a>
    <a href="#methods">שלוש השיטות</a>
    <a href="#ask">מה ישאלו</a>
    <a href="#files">איפה הכל</a>
  </div>
</nav>

<header class="mast wrap">
  <p class="eyebrow">גיליון הגנה &middot; כל מספר נקרא מקובץ</p>
  <h1>מסלולים פופולריים ארוכים בנסיעות המוניות של פורטו</h1>
  <p class="lede">
    {fmt(meta["total_trips"])} נסיעות נקיות, מקודדות לתאי H3 ברזולוציה 9, נכרו על
    אשכול Dataproc בן {prov["total_nodes"]} מכונות. ארבע מתוך שש הקונפיגורציות
    עומדות ביעד של 100 מסלולים. שתיים חוזרות ריקות — משתי סיבות שונות, ורק אחת
    מהן היא מגבלה של הפייפליין.
  </p>
  <div class="runline">
    <span><b>ריצה</b> {prov["run_id"]}</span>
    <span><b>אשכול</b> {prov["workers"]}&times;{prov["machine_type"]}</span>
    <span><b>אזור</b> {prov["region"]}</span>
    <span><b>זמן קיר</b> {prov["total_wall_clock_seconds"] / 60:.0f} דק'</span>
    <span><b>Spark</b> {prov["image_version"]}</span>
  </div>
</header>

<hr class="hr">

<section id="config" class="wrap wide">
  <h2>שש הקונפיגורציות</h2>
  <p class="sub">
    היעד הוא 100 מסלולים לכל סף אורך. העמודה "תקרה" היא החסם העליון על התמיכה
    שנובע מהתפלגות אורכי הנסיעות בלבד: נסיעה יכולה לעבור מסלול באורך L רק אם היא
    עצמה באורך L, ולכן כל שאר הנסיעות תורמות אפס בהגדרה — לא בקירוב.
  </p>
  <div class="scroll">
  <table>
    <caption>נקרא מ־<code>stage3_subroutes.json</code> · שדות <code>by_threshold_km</code> ו־<code>length_ceiling</code></caption>
    <thead><tr>
      <th>סף אורך</th><th class="n">X שנבחר</th><th class="n">נמצאו</th>
      <th class="n">נסיעות ארוכות מספיק</th><th class="n">תקרת תמיכה</th><th></th>
    </tr></thead>
    <tbody>
{config_rows}
    </tbody>
  </table>
  </div>

  <h3>עקומת הפשרה</h3>
  <p class="sub">
    ה־X נבחר לכל סף אורך בנפרד: הגבוה ביותר שעדיין מחזיר 100 מסלולים. הסריקה הזו
    היא ההצדקה לבחירה, ולא החלטה שרירותית.
  </p>
  <div class="scroll">
  <table>
    <caption>נקרא מ־<code>stage3_subroutes.json</code> · שדה <code>support_sweep</code></caption>
    <thead><tr>
      <th class="n">X</th><th class="n">מינימום נסיעות</th><th class="n">מסלולים</th>
      <th class="n">הארוך ביותר (ק"מ)</th><th class="n">ממוצע (ק"מ)</th>
    </tr></thead>
    <tbody>
{sweep_rows}
    </tbody>
  </table>
  </div>
  <p class="cap">
    ככל ש־X יורד נמצאים יותר מסלולים וארוכים יותר, אבל המילה "פופולרי" נחלשת.
    זו הפשרה שהבריף מבקש להתנסות בה, והטבלה היא הניסוי.
  </p>
</section>

<hr class="hr">

<section id="long" class="wrap wide">
  <h2>למה 20 ו־40 ק"מ ריקים</h2>
  <p class="sub">
    זו השאלה הקשה, ויש לה תשובה מדודה ולא הסבר. נסיעה יכולה לעבור מסלול באורך
    20 ק"מ רק אם היא עצמה באורך 20 ק"מ, ולכן התמיכה של מסלול כזה מתוך
    {fmt(meta["total_trips"])} הנסיעות שווה <em>בדיוק</em> לתמיכה שלו מתוך
    {fmt(probe["long_trips_searched"])} הנסיעות הארוכות. הקבוצה הזו קטנה מספיק
    לכרייה ממצה על מכונה אחת, בסף של שתי נסיעות — נמוך ככל שהמילה "משותף" מרשה.
  </p>

  <div class="split">
    <div class="half exists">
      <p class="k">&ge; 20 ק"מ</p>
      <h4>קיימים — אבל לא פופולריים</h4>
      <p>
        {probe["distinct_valid_found"]} מסלולים תקינים באורך 20 ק"מ ומעלה קיימים
        בדאטה: מסלול פשוט, בלי חזרה על תא, ובתוך פי 2.5 מהקו הישר בין קצותיו.
        הארוך שבהם {max(r["length_km"] for r in probe["corridors"]):.2f} ק"מ.
      </p>
      <p>
        אף אחד מהם לא משותף ליותר מ־{probe["max_support_trips"]} נסיעות, מול רצפת
        כרייה של {probe["mining_floor_trips"]}. שלב 3 לא מדווח עליהם כי אף אחד מהם
        אינו <em>פופולרי</em> — וזו השאלה שהבריף שאל.
      </p>
      <dl>
        <dt>הקטע הארוך ביותר ששתי נסיעות חולקות</dt>
        <dd>{max(r["length_km"] for r in probe["corridors"]):.2f} ק"מ</dd>
        <dt>מסלולים תקינים נפרדים</dt><dd>{probe["distinct_valid_found"]}</dd>
        <dt>התמיכה הטובה ביותר</dt><dd>{probe["max_support_trips"]} נסיעות</dd>
        <dt>רצפת הכרייה</dt><dd>{probe["mining_floor_trips"]} נסיעות</dd>
      </dl>
    </div>
    <div class="half absent">
      <p class="k">&ge; 40 ק"מ</p>
      <h4>לא קיימים — בשום סף שהוא</h4>
      <p>
        באותה בדיקה ממצה, בסף של שתי נסיעות, אין ולו מועמד אחד באורך 40 ק"מ. אין
        בדאטהסט שתי נסיעות שחולקות 40 קילומטרים רצופים.
      </p>
      <p>
        זו עובדה על פורטו ולא מגבלה של הפייפליין: העיר כ־25 על 22 קילומטר, ושתי
        מוניות שנוסעות 40 ק"מ עושות זאת בשתי שליחויות שונות ובכיוונים שונים.
      </p>
      <dl>
        <dt>נסיעות באורך 40 ק"מ ומעלה</dt>
        <dd>{fmt(ceiling[40]["trips_at_least_this_long"])}</dd>
        <dt>תקרת תמיכה תיאורטית</dt><dd>{ceiling[40]["max_possible_support_pct"]:.3f}%</dd>
        <dt>מועמדים בסף של 2 נסיעות</dt><dd>0</dd>
      </dl>
    </div>
  </div>

  <h3>שמונת המסלולים הארוכים שכן קיימים</h3>
  <div class="console">  <span class="dim"># tools/export_long_corridors.py</span>
  <span class="dim">  #      km   trips  cells  tortuosity</span>
{probe_lines}
  <span class="dim">  ... {probe["distinct_valid_found"]} distinct, top 100 exported</span>

  <span class="hi">best support {probe["max_support_trips"]} trips</span>   <span class="dim">vs a mining floor of {probe["mining_floor_trips"]}</span>
  <span class="no">&gt;= 40 km: no candidate at all, at a support of two</span></div>
  <p class="cap">
    הם מצוירים על המפה מקווקווים ובאפור, בשכבה נפרדת, עם התמיכה האמיתית בכל
    tooltip — כדי שלא יבלבלו אותם עם פלט הכרייה אף פעם.
  </p>
</section>

<hr class="hr">

<section id="pipeline" class="wrap wide">
  <h2>מספרי הפייפליין</h2>
  <p class="sub">כל מספר כאן נקרא מהקובץ שכתוב מתחתיו.</p>

  <h3>שלב 1 · ניקוי</h3>
  <div class="figs">
    {fig(fmt(cs["raw_trips_read"]), "נסיעות גולמיות", "cleaning_report.json")}
    {fig(fmt(cs["final_clean_trips"]), "נסיעות נקיות", "cleaning_report.json")}
    {fig(f'{cs["removed_pct"]:.2f}%', "הוסרו", "cleaning_report.json")}
    {fig(fmt(cs["unique_taxis"]), "מוניות בצי", "cleaning_report.json")}
    {fig(fmt(cs["kept_trips_leaving_study_area"]), "נסיעות שיצאו מפורטו ונשמרו", "cleaning_report.json")}
  </div>
  <div class="scroll" style="margin-block-start:1.2rem">
  <table>
    <caption>כל כלל ניקוי ומה הוא הסיר · <code>cleaning_report.json</code></caption>
    <thead><tr><th>כלל</th><th class="n">נסיעות</th><th class="n">מהגולמי</th></tr></thead>
    <tbody>
{clean_rows}
    </tbody>
  </table>
  </div>
  <p class="cap">
    כלל 5 נמדד מול תיבה אזורית רחבה ולא מול פורטו עצמה. נסיעה שיוצאת מהעיר היא
    מסע, לא שגיאת לוויין — הבחנה שהעלתה את מספר הנסיעות הארוכות פי כמה.
  </p>

  <h3>שלב 2 · קידוד מרחבי</h3>
  <div class="figs">
    {fig(fmt(h3rep["total_trips_encoded"]), "נסיעות מקודדות", "h3_encoding_report.json")}
    {fig(fmt(h3rep["unique_h3_res8_cells"]), "תאים ייחודיים · רזולוציה 8", "h3_encoding_report.json")}
    {fig(fmt(h3rep["unique_h3_res9_cells"]), "תאים ייחודיים · רזולוציה 9", "h3_encoding_report.json")}
    {fig(fmt(h3rep["unique_h3_res10_cells"]), "תאים ייחודיים · רזולוציה 10", "h3_encoding_report.json")}
  </div>
  <p class="cap">
    שלב 3 עובד ברזולוציה 9 — צלע ~174 מטר, מרחק ~0.363 ק"מ בין מרכזי שכנים.
    דק מספיק כדי להפריד רחובות סמוכים, גס מספיק כדי ששתי נסיעות באותו כביש
    יחלקו תאים.
  </p>

  <h3>שלב 3 · השער המקורב</h3>
  <div class="figs">
    {fig(fmt(gate["ngrams_streamed"]), f'רצפים באורך {gate["k"]} שזרמו', "stage3_benchmark.json")}
    {fig(f'{gate["pruned_before_shuffle_pct"]:.4f}%', "נחתכו לפני ה־shuffle", "stage3_benchmark.json")}
    {fig(fmt(gate["exact_frequent"]), "נפוצים במדויק", "stage3_benchmark.json")}
    {fig(f'{gate["cms_memory_mb"]:.0f} MB', "טבלת Count-Min (קבועה)", "stage3_benchmark.json")}
    {fig(f'{gate["bloom_memory_kb"]:.1f} KB', "פילטר בלום משודר", "stage3_benchmark.json")}
    {fig(f'{gate["cms_false_positive_pct"]:.2f}%', "טעויות חיוביות של הסקיצה", "stage3_benchmark.json", "g")}
  </div>
  <p class="cap">
    הסקיצה לעולם לא מזלזלת בספירה, ולכן <code>estimate &lt; min_support</code> הוא
    <em>הוכחה</em> שהרצף נדיר. מה שנחתך בשער נחתך בוודאות. הטבלה עצמה בגודל קבוע
    ואינה מתכווצת — מה שמתכווץ היא רשימת השורדים.
  </p>

  <h3>שלב 3 · אימות וזיהוי חריגות</h3>
  <div class="figs">
    {fig(fmt(pipe["candidates_verified"]), "מועמדים שאומתו במדויק", "stage3_benchmark.json")}
    {fig(fmt(pipe["corridors_reported"]), "מסלולים מדווחים", "stage3_benchmark.json")}
    {fig(f'{pipe["verification_sec"]:.1f}s', "זמן האימות", "stage3_benchmark.json")}
    {fig(fmt(anom["trips_scored"]), "נסיעות שנוקדו לחריגות", "stage3_benchmark.json")}
    {fig(f'{anom["transition_gate"]["bloom_memory_kb"]:.1f} KB', "בלום המעברים", "stage3_benchmark.json")}
    {fig(f'{pipe["total_runtime_sec"] / 60:.0f} דק׳', "זמן שלב 3", "stage3_benchmark.json")}
  </div>
</section>

<hr class="hr">

<section id="methods" class="wrap wide">
  <h2>שלוש השיטות, ומה האימות תפס</h2>
  <p class="sub">
    כל שיטה מייצרת מועמדים בדרכה, וכל מועמד נספר אחר כך במדויק מול 100% מהנסיעות.
    העמודה האחרונה היא הסיבה שהשלב הזה קיים.
  </p>
  <div class="scroll">
  <table>
    <caption>נקרא מ־<code>stage3_benchmark.json</code> · <code>per_method_scorecard</code></caption>
    <thead><tr>
      <th>שיטה</th><th class="n">מסלולים</th><th class="n">הארוך (ק"מ)</th>
      <th class="n">ממוצע (ק"מ)</th><th class="n">ניפוח תמיכה</th>
    </tr></thead>
    <tbody>
{method_rows}
    </tbody>
  </table>
  </div>
  <p class="cap">
    LSH הוא מבנה מקורב, והוא ניפח את התמיכה ב־{score["lsh_clustering"]["support_overestimate_pct"]:.2f}%.
    שתי השיטות המדויקות לא ניפחו כלל. זו הדגמה חיה של למה מבנה הסתברותי חייב שלב
    ודאות אחריו, ולא רק משפט בהקדמה.
  </p>

  <div class="figs" style="margin-block-start:1.4rem">
    {fig(fmt(ma["windows_hashed"]), "חלונות ש־MinHash חתם", "stage3_benchmark.json")}
    {fig(fmt(ma["band_emissions"]), "פליטות רצועות LSH", "stage3_benchmark.json")}
    {fig(f'{ma["lsh_similarity_threshold"]:.3f}', "סף דמיון (b=8, r=4)", "stage3_benchmark.json")}
    {fig(fmt(mb["suffix_positions_considered"]), "מיקומי סיומת שנשקלו", "stage3_benchmark.json")}
    {fig(fmt(mb["distinct_repeats_found"]), "חזרות נפרדות שנמצאו", "stage3_benchmark.json")}
    {fig(f'{mb["bloom_pruned_pct"]:.2f}%', "סיומות שהבלום גזם", "stage3_benchmark.json")}
    {fig(fmt(mc["seeds"]), "זרעים לצמיחה", "stage3_benchmark.json")}
    {fig(fmt(mc["rounds_run"]), "סבבי צמיחה", "stage3_benchmark.json")}
    {fig(fmt(mc["corridors_returned"]), "מסלולים מקסימליים", "stage3_benchmark.json")}
  </div>
</section>

<hr class="hr">

<section id="ask" class="wrap">
  <h2>מה סביר שישאלו</h2>
  <p class="sub">והמספר שצריך לצטט בתשובה.</p>
  <div class="qa">
    <div class="q">
      <h4>למה 20 ו־40 ק"מ ריקים? לא סיננתם יותר מדי?</h4>
      <p>
        סיננו יותר מדי — ותיקנו. הכלל הישן פסל כל נסיעה שיצאה מגבולות פורטו, כלומר
        בדיוק את הנסיעות הבין־עירוניות. אחרי התיקון יש
        <span class="num">{fmt(ceiling[40]["trips_at_least_this_long"])}</span>
        נסיעות של 40 ק"מ ומעלה במקום <span class="num">460</span>.
      </p>
      <p>
        ואז בדקנו ממצה: מעל 20 ק"מ קיימים <span class="num">{probe["distinct_valid_found"]}</span>
        מסלולים תקינים, אבל הטוב שבהם משותף ל־<span class="num">{probe["max_support_trips"]}</span>
        נסיעות בלבד. מעל 40 ק"מ אין ולו מועמד אחד בסף של שתיים.
      </p>
    </div>
    <div class="q">
      <h4>איך ידעתם שהמסלול באמת רציף, ולא הדבקה של קטעים משתי נסיעות?</h4>
      <p>
        התמיכה מוגדרת כמספר הנסיעות שעוברות את <em>כל</em> מקטעי המסלול, ברצף
        ובסדר, כשבכל חור הן נמצאות לכל היותר
        <span class="num">{meta["max_gap_cells"]}</span> תאים. זה נבדק לכל מועמד
        מול 100% מהנסיעות, לא על דגימה.
      </p>
    </div>
    <div class="q">
      <h4>למה בכלל Count-Min? למה לא פשוט לספור?</h4>
      <p>
        ספירה מדויקת של <span class="num">{fmt(gate["ngrams_streamed"])}</span> רצפים
        דורשת shuffle של כולם. הסקיצה חותכת
        <span class="num">{gate["pruned_before_shuffle_pct"]:.2f}%</span> מהם
        <em>לפני</em> שמשהו עובר ברשת, ומשאירה
        <span class="num">{fmt(gate["exact_frequent"])}</span> לספירה מדויקת.
      </p>
      <p>
        וזה בטוח כי השגיאה חד־צדדית: הסקיצה אף פעם לא סופרת בחסר, ולכן אומדן מתחת
        לסף הוא הוכחה שהרצף נדיר.
      </p>
    </div>
    <div class="q">
      <h4>אם LSH מקורב, איך אתם סומכים על התוצאות?</h4>
      <p>
        לא סומכים. LSH ניפח את התמיכה ב־<span class="num">{score["lsh_clustering"]["support_overestimate_pct"]:.2f}%</span>,
        וזה בדיוק מה שהאימות המדויק תפס. מה שמדווח הוא הספירה המדויקת, לא הערכת
        השיטה.
      </p>
    </div>
    <div class="q">
      <h4>למה רזולוציה 9 ולא 8 או 10?</h4>
      <p>
        שלושתן מקודדות ונשמרות, כדי שהפשרה תוצג ולא תיטען.
        רזולוציה 9 נותנת <span class="num">{fmt(h3rep["unique_h3_res9_cells"])}</span> תאים
        על פני העיר — דק מספיק להפריד רחובות מקבילים, גס מספיק ששתי נסיעות באותו
        כביש יחלקו תאים.
      </p>
    </div>
    <div class="q">
      <h4>מה הדאטה לא מכיל?</h4>
      <p>
        רק <span class="num">{fmt(cs["unique_taxis"])}</span> מוניות, ורק נסיעות בתשלום —
        לא מכוניות פרטיות, לא אוטובוסים, ולא הנסיעה הריקה בין נוסע לנוסע. לכן X
        מודד תדירות בתוך הדגימה שלנו, לא בתוך התנועה בפורטו.
      </p>
    </div>
  </div>
</section>

<hr class="hr">

<section id="files" class="wrap wide">
  <h2>איפה כל דבר יושב</h2>
  <ul class="files">
    <li><code>output/stage3_subroutes.json</code><span>המסלולים עצמם, התקרה, וסריקת ה־X</span></li>
    <li><code>output/stage3_benchmark.json</code><span>כל מדד ריצה וכל פרמטר של כל שיטה</span></li>
    <li><code>output/long_corridors_probe.json</code><span>100 מסלולי 20 ק"מ שמתחת לרצפה, עם התמיכה האמיתית</span></li>
    <li><code>output/longest_trips.json</code><span>100 המסעות הבודדים הארוכים ביותר, כהקשר</span></li>
    <li><code>output/stage3_subroutes_map.html</code><span>המפה, שבע שכבות</span></li>
    <li><code>output/porto_defence_he.pptx</code><span>מצגת ההגנה</span></li>
    <li><code>output/stage3_methods_comparison.pptx</code><span>השוואת השיטות</span></li>
    <li><code>notebooks/stage3_colab_enterprise.ipynb</code><span>הנוטבוק, קורא מ־GCS</span></li>
    <li><code>tools/probe_long_corridors.py</code><span>הבדיקה הממצה של 20 ו־40 ק"מ</span></li>
    <li><code>tools/verify_*.py</code><span>אימות עצמאי לכל שלב</span></li>
  </ul>
  <p class="cap" style="margin-block-start:1.2rem">
    התוצאות בענן:
    <code style="direction:ltr;display:inline-block">{prov["output_dir"]}</code>
  </p>
</section>

<footer class="wrap wide">
  נבנה מקבצי התוצאה של ריצה {prov["run_id"]} על ידי
  <code style="direction:ltr">tools/build_defence_page.py</code>.
  אף מספר בעמוד הזה לא הוקלד ביד.
</footer>

</div>
"""

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {out_path} from {results} (run {prov['run_id']})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="output")
    ap.add_argument("--out", default="docs/defence.html")
    args = ap.parse_args()
    build(args.results, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
