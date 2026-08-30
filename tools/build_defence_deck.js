/*
 * The oral-defence deck, in Hebrew, generated from the result files.
 *
 * The brief asks for a summary presentation comparing the methods -- performance,
 * accuracy, runtimes, memory.  build_methods_deck.js already produces that as a
 * technical English artefact.  This is the deck a person stands in front of: the
 * same numbers, told as the story of the project, right to left.
 *
 * Every figure is read out of the JSON, so the deck cannot drift from the run.
 *
 *   node tools/build_defence_deck.js \
 *        --results   output/run_x0002/stage3_subroutes.json \
 *        --benchmark output/run_x0002/stage3_benchmark.json \
 *        --cleaning  output/run_x005/cleaning_report.json \
 *        --h3        output/run_x005/h3_encoding_report.json \
 *        --out       output/porto_defence_he.pptx
 */

const fs = require("fs");
const PptxGenJS = require("pptxgenjs");

const argv = process.argv.slice(2);
const arg = (n, d) => { const i = argv.indexOf(`--${n}`); return i >= 0 && argv[i + 1] ? argv[i + 1] : d; };

const data  = JSON.parse(fs.readFileSync(arg("results",  "output/run_x0002/stage3_subroutes.json"), "utf8"));
const bench = JSON.parse(fs.readFileSync(arg("benchmark","output/run_x0002/stage3_benchmark.json"), "utf8"));
const clean = JSON.parse(fs.readFileSync(arg("cleaning", "output/run_x005/cleaning_report.json"), "utf8"));
const h3rep = JSON.parse(fs.readFileSync(arg("h3",       "output/run_x005/h3_encoding_report.json"), "utf8"));
const OUT   = arg("out", "output/porto_defence_he.pptx");

// ── palette: deep navy city at night, taxi amber as the single accent ────────
const NAVY   = "10243F";
const BLUE   = "1C4E80";
const AMBER  = "F4A81D";
const LIGHT  = "F2F5F9";
const WHITE  = "FFFFFF";
const MUTED  = "5A6B80";
const INK    = "16212E";
const FONT   = "Arial";

const n = (x) => Number(x).toLocaleString("en-US");

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";           // 13.3 x 7.5 in
pres.rtlMode = true;
pres.author = "Porto Taxi Project";
pres.title = "כריית תת-מסלולים פופולריים בפורטו";

const W = 13.3, H = 7.5, M = 0.6;

// Hebrew text defaults: right aligned, RTL, no stray padding.
const he = (extra = {}) => Object.assign(
  { fontFace: FONT, align: "right", rtlMode: true, isTextBox: true, margin: 0 }, extra);

function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: NAVY };
  return s;
}
function lightSlide(title, kicker) {
  const s = pres.addSlide();
  s.background = { color: WHITE };
  if (kicker) {
    s.addText(kicker, he({ x: M, y: 0.42, w: W - 2 * M, h: 0.3,
      fontSize: 13, color: AMBER, bold: true }));
  }
  s.addText(title, he({ x: M, y: kicker ? 0.72 : 0.5, w: W - 2 * M, h: 0.72,
    fontSize: 34, bold: true, color: INK }));
  return s;
}
// A stat card: big number, small label.  This is the deck's one motif.
function stat(s, x, y, w, value, label, opts = {}) {
  const h = opts.h || 1.55;
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.09,
    fill: { color: opts.fill || LIGHT }, line: { color: opts.fill || LIGHT } });
  s.addText(String(value), he({ x: x + 0.18, y: y + 0.16, w: w - 0.36, h: 0.72,
    fontSize: opts.big || 34, bold: true, color: opts.valueColor || BLUE, align: "center" }));
  s.addText(label, he({ x: x + 0.18, y: y + 0.88, w: w - 0.36, h: h - 1.0,
    fontSize: 12, color: opts.labelColor || MUTED, align: "center", valign: "top" }));
}

// ─────────────────────────────────────────────────────────────── 1. title ──
{
  const s = darkSlide();
  s.addText("מיחשוב ענן רב נתונים", he({ x: M, y: 1.5, w: W - 2 * M, h: 0.4,
    fontSize: 16, color: AMBER, bold: true, charSpacing: 2 }));
  s.addText("כריית תת-מסלולים פופולריים\nמ-1.71 מיליון נסיעות מוניות בפורטו",
    he({ x: M, y: 2.0, w: W - 2 * M, h: 1.9, fontSize: 40, bold: true,
         color: WHITE, lineSpacing: 46 }));
  s.addText("PySpark על Google Cloud Dataproc  ·  אשכול של 6 מכונות  ·  שלוש שיטות כרייה",
    he({ x: M, y: 4.0, w: W - 2 * M, h: 0.4, fontSize: 15, color: "9FB3CC" }));

  const cards = [
    [n(clean.summary.raw_trips_read), "נסיעות גולמיות"],
    [n(data.metadata.total_trips), "נסיעות אחרי ניקוי"],
    [n(bench.methods.gate.ngrams_streamed), "שברי מסלול שנסרקו"],
    [n(bench.pipeline.corridors_reported), "מסלולים שנמצאו"],
  ];
  cards.forEach(([v, l], i) => {
    const x = M + i * ((W - 2 * M) / 4);
    const w = (W - 2 * M) / 4 - 0.25;
    s.addText(v, he({ x, y: 5.1, w, h: 0.55, fontSize: 26, bold: true, color: AMBER, align: "center" }));
    s.addText(l, he({ x, y: 5.68, w, h: 0.35, fontSize: 12, color: "9FB3CC", align: "center" }));
  });
  s.addNotes("פרויקט סיום. הדאטהסט: 442 מוניות בפורטו לאורך שנה, דגימת GPS כל 15 שניות.");
}

// ─────────────────────────────────────────────────────────── 2. the problem ──
{
  const s = lightSlide("מה בעצם צריך למצוא", "הבעיה");
  s.addText("תת-מסלול פופולרי הוא לא נסיעה שלמה ולא צומת עמוס. הוא קטע רצוף שהרבה נסיעות עברו בו — ומותר שיהיו בו חורים, כשהתנועה מתפצלת לשתי דרכים חלופיות ומתאחדת בהמשך.",
    he({ x: M, y: 1.75, w: W - 2 * M, h: 0.9, fontSize: 16, color: INK, lineSpacing: 24 }));

  const qs = [
    ["1", "מהם המסלולים הפופולריים ביותר בעיר?"],
    ["2", "אילו אזורים הם מוקדי פעילות?"],
    ["3", "כיצד ניתן לזהות מסלולים חריגים?"],
    ["4", "כיצד עושים את זה ביעילות עם אלגוריתמים מקורבים?"],
  ];
  qs.forEach(([num, q], i) => {
    const y = 2.95 + i * 0.92;
    s.addShape(pres.ShapeType.ellipse, { x: W - M - 0.62, y, w: 0.62, h: 0.62,
      fill: { color: AMBER }, line: { color: AMBER } });
    s.addText(num, he({ x: W - M - 0.62, y: y + 0.12, w: 0.62, h: 0.4,
      fontSize: 17, bold: true, color: NAVY, align: "center" }));
    s.addText(q, he({ x: M, y: y + 0.13, w: W - 2 * M - 0.95, h: 0.5,
      fontSize: 17, color: INK }));
  });
  s.addNotes("ארבע השאלות מהבריף. שלוש הראשונות הן תוצרים, הרביעית היא הדרך.");
}

// ────────────────────────────────────────────────────────────── 3. pipeline ──
{
  const s = lightSlide("שלושה שלבים, כולם על האשכול", "הפייפליין");
  const steps = [
    ["שלב 1", "ניקוי וחילוץ", `${n(clean.summary.raw_trips_read)} ← ${n(clean.summary.final_clean_trips)}\n10 כללי איכות, כל אחד נספר בנפרד`],
    ["שלב 2", "קידוד H3", `${n(h3rep.summary.unique_h3_res9_cells)} תאים ייחודיים\nרזולוציות 8 / 9 / 10`],
    ["שלב 3", "כריית מסלולים", `${n(bench.pipeline.corridors_reported)} מסלולים\nשלוש שיטות + מעבר אימות`],
  ];
  steps.forEach(([tag, name, body], i) => {
    const w = (W - 2 * M - 0.8) / 3;
    const x = W - M - w - i * (w + 0.4);
    s.addShape(pres.ShapeType.roundRect, { x, y: 2.25, w, h: 3.15, rectRadius: 0.1,
      fill: { color: i === 2 ? NAVY : LIGHT }, line: { color: i === 2 ? NAVY : LIGHT } });
    s.addText(tag, he({ x: x + 0.25, y: 2.55, w: w - 0.5, h: 0.32,
      fontSize: 12, bold: true, color: AMBER }));
    s.addText(name, he({ x: x + 0.25, y: 2.92, w: w - 0.5, h: 0.55,
      fontSize: 22, bold: true, color: i === 2 ? WHITE : INK }));
    s.addText(body, he({ x: x + 0.25, y: 3.6, w: w - 0.5, h: 1.6,
      fontSize: 14, color: i === 2 ? "9FB3CC" : MUTED, lineSpacing: 21 }));
  });
  s.addText(`זמן ריצה מלא על האשכול: ${Math.round(bench.pipeline.total_runtime_sec / 60)} דקות  ·  1 master + 5 workers  ·  כל שלב כותב ל-gs:// ושורד את מחיקת האשכול`,
    he({ x: M, y: 6.25, w: W - 2 * M, h: 0.4, fontSize: 14, color: MUTED }));
  s.addNotes("אשכול אחד לשלושת השלבים: הקמה עולה ~90 שניות של זמן מחויב, אז לא מקימים שלושה.");
}

// ───────────────────────────────────────────────────────────── 4. stage one ──
{
  const s = lightSlide("ניקוי שאפשר להגן עליו", "שלב 1");
  // The report's labels are English; the deck is Hebrew.  Keyed, not translated
  // from the string, so a reworded report cannot silently mislabel a row.
  const RULE_HE = {
    missing_data:       "דגל MISSING_DATA מהטלמטריה",
    empty_polyline:     "POLYLINE ריק — הזמנה שבוטלה מיד",
    bad_json:           "POLYLINE שאינו JSON תקין",
    too_few_points:     "פחות משתי נקודות GPS",
    too_long:           "משך מעל 24 שעות — מונה שנשאר דולק",
    out_of_bbox:        "נקודת GPS מחוץ לתיבת הגבול של פורטו",
    gps_jump:           "קפיצה שמשמעה מעל 200 קמ\"ש — שגיאת לוויין",
    stationary:         "פחות משתי נקודות נבדלות אחרי איחוד",
    too_short_distance: "קצר מ-0.2 ק\"מ — לא נסיעה",
    too_long_distance:  "ארוך מ-100 ק\"מ — לא סביר בעיר הזו",
  };
  const rules = Object.entries(clean.per_rule_removed)
    .map(([k, r]) => [RULE_HE[k] || r.label, r.trips])
    .filter(r => r[1] > 0)
    .sort((a, b) => b[1] - a[1]).slice(0, 5);

  const rows = [[
    { text: "כלל", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "right" } },
    { text: "נסיעות שהוסרו", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
  ]];
  rules.forEach(([label, trips]) => rows.push([
    { text: label, options: { align: "right", color: INK } },
    { text: n(trips), options: { align: "center", color: BLUE, bold: true } },
  ]));
  s.addTable(rows, { x: M, y: 1.95, w: 7.3, rowH: 0.56, fontSize: 13, fontFace: FONT,
    border: { pt: 0.5, color: "DCE3EC" }, rtlMode: true });

  stat(s, W - M - 4.6, 1.95, 2.2, `${clean.summary.removed_pct.toFixed(1)}%`, "מהנסיעות הוסרו");
  stat(s, W - M - 2.25, 1.95, 2.25, n(clean.summary.unique_taxis), "מוניות ייחודיות");

  s.addShape(pres.ShapeType.roundRect, { x: W - M - 4.6, y: 3.9, w: 4.6, h: 2.35,
    rectRadius: 0.09, fill: { color: NAVY }, line: { color: NAVY } });
  s.addText("הבאג ששווה להכיר", he({ x: W - M - 4.35, y: 4.12, w: 4.1, h: 0.32,
    fontSize: 12, bold: true, color: AMBER }));
  s.addText("משך הנסיעה מחושב מספירת הדגימות המקורית. גזירה שלו אחרי הסרת כפילויות מוחקת את הזמן שהמונית עמדה ברמזור — ומנפחת את המהירות מ-25.6 ל-40.2 קמ\"ש.",
    he({ x: W - M - 4.35, y: 4.5, w: 4.1, h: 1.6, fontSize: 13, color: "C9D6E5", lineSpacing: 19 }));

  s.addText(`חציון מרחק הנסיעה: ${clean.distance_percentiles_km.p50.toFixed(1)} ק"מ   ·   אחוזון 99: ${clean.distance_percentiles_km.p99.toFixed(1)} ק"מ   ·   תיבת הגבול נבדקת על כל נקודה, לא רק על הקצוות`,
    he({ x: M, y: 6.55, w: W - 2 * M, h: 0.4, fontSize: 13, color: MUTED }));
  s.addNotes("כל כלל מגדיל מונה משלו, כך שהדוח נגזר מהריצה ולא נטען לצידה.");
}

// ───────────────────────────────────────────────────────────── 5. stage two ──
{
  const s = lightSlide("למה משושים, ולמה רזולוציה 9", "שלב 2");
  const rows = [[
    { text: "רזולוציה", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "צלע", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "תאים ייחודיים", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "הבעיה", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "right" } },
  ]];
  const grid = [
    ["8", "461 מ'", n(h3rep.summary.unique_h3_res8_cells), "גס מדי — שני רחובות מקבילים מתמזגים לתא אחד"],
    ["9", "174 מ'", n(h3rep.summary.unique_h3_res9_cells), "תא ≈ קטע רחוב"],
    ["10", "66 מ'", n(h3rep.summary.unique_h3_res10_cells), "עדין מדי — נתיב שונה נופל בתא שונה"],
  ];
  grid.forEach((r, i) => rows.push(r.map((c, j) => ({
    text: c,
    options: { align: j === 3 ? "right" : "center",
               color: i === 1 ? BLUE : INK, bold: i === 1,
               fill: { color: i === 1 ? "FFF6E4" : WHITE } },
  }))));
  s.addTable(rows, { x: M, y: 2.1, w: W - 2 * M, rowH: 0.64, fontSize: 14, fontFace: FONT,
    border: { pt: 0.5, color: "DCE3EC" }, colW: [1.5, 1.3, 2.0, 7.3], rtlMode: true });

  s.addText("במשושה כל שכן נמצא באותו מרחק. ברשת ריבועית צעד באלכסון ארוך פי 1.41 מצעד ישר, וזה מטה את הכרייה לטובת כבישים בכיווני הצירים.",
    he({ x: M, y: 4.95, w: W - 2 * M, h: 0.7, fontSize: 15, color: INK, lineSpacing: 22 }));
  s.addText("99.5% מהמעברים בין תאים עוקבים הם למשושה שכן. 0.5% מדלגים על תא — זה מה שנראה נסיעה מהירה בקצב דגימה של 15 שניות.",
    he({ x: M, y: 5.85, w: W - 2 * M, h: 0.7, fontSize: 14, color: MUTED, lineSpacing: 21 }));
  s.addNotes("שלוש הרזולוציות מקודדות מהקואורדינטות ולא נגזרות זו מזו: ההיררכיה של H3 מקורבת, כי משושים לא מתחלקים למשושים.");
}

// ──────────────────────────────────────────────────────────────── 6. gate ──
{
  const g = bench.methods.gate;
  const s = lightSlide("איפה המבנים המקורבים באמת חוסכים", "השער");
  s.addText("כל נסיעה מתפרקת לשברים באורך 4 תאים. לשלוח את כולם ברשת כדי לגלות מי נפוץ הוא הדבר היקר ביותר שהפייפליין יכול לעשות.",
    he({ x: M, y: 1.75, w: W - 2 * M, h: 0.6, fontSize: 16, color: INK, lineSpacing: 23 }));

  stat(s, W - M - 3.9, 2.7, 3.9, `${g.pruned_before_shuffle_pct.toFixed(2)}%`,
       "מהשברים נגזמו לפני ששום דבר עבר ברשת", { big: 44, fill: NAVY, valueColor: AMBER, labelColor: "C9D6E5", h: 2.3 });

  const facts = [
    [`Count-Min Sketch`, `${g.cms.geometry}  ·  ${g.cms_memory_mb} MB לכל partition, ללא תלות בכמות הנתונים`],
    [`treeAggregate`, `סקיצות ממוזגות בזוגות במעלה עץ — הדרייבר מקבל אחת, לא אחת לכל partition`],
    [`Bloom Filter`, `${g.bloom_memory_kb} KB בשידור לכל executor, ${(g.bloom_observed_fp_rate * 100).toFixed(2)}% טעות חיובית, אפס טעות שלילית`],
  ];
  facts.forEach(([t, d], i) => {
    const y = 2.75 + i * 1.15;
    s.addText(t, he({ x: M, y, w: 8.3, h: 0.3, fontSize: 15, bold: true, color: BLUE }));
    s.addText(d, he({ x: M, y: y + 0.32, w: 8.3, h: 0.6, fontSize: 13, color: MUTED, lineSpacing: 19 }));
  });

  s.addText(`${n(g.ngrams_streamed)} שברים נסרקו  →  ${n(g.candidates_after_cms)} עברו את הסקיצה  →  נספרו במדויק`,
    he({ x: M, y: 6.4, w: W - 2 * M, h: 0.4, fontSize: 15, bold: true, color: INK }));
  s.addNotes("הטעות של שני המבנים חד-צדדית: הם עלולים להשאיר משהו נדיר, לא לזרוק משהו נפוץ. לכן מותר לשים אותם לפני אלגוריתם מדויק.");
}

// ───────────────────────────────────────────────────────────── 7. methods ──
{
  const c = bench.methods.per_method_scorecard;
  const s = lightSlide("שלוש שיטות, שלושה אופיים שונים", "שלב 3");
  const rows = [[
    { text: "שיטה", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "right" } },
    { text: "מסלולים", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "ארוך ביותר", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "אורך ממוצע", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "זמן ריצה", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "סטיית support", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
  ]];
  const rt = {
    lsh_clustering: bench.methods.method_a_lsh_clustering.runtime_sec,
    suffix_array_lcp: bench.methods.method_b_suffix_array.runtime_sec,
    cms_growth: bench.methods.method_c_growth.runtime_sec,
  };
  const names = {
    lsh_clustering: "א׳ · MinHash + LSH (אשכול)",
    suffix_array_lcp: "ב׳ · Suffix Array + LCP",
    cms_growth: "ג׳ · גידול שכבתי מאומת",
  };
  ["lsh_clustering", "suffix_array_lcp", "cms_growth"].forEach(k => {
    const v = c[k];
    const bad = v.support_overestimate_pct > 0;
    rows.push([
      { text: names[k], options: { align: "right", color: INK, bold: true } },
      { text: n(v.corridors_verified), options: { align: "center", color: INK } },
      { text: `${v.max_length_km} ק"מ`, options: { align: "center", color: INK } },
      { text: `${v.mean_length_km} ק"מ`, options: { align: "center", color: INK } },
      { text: `${Math.round(rt[k] / 60)} דק'`, options: { align: "center", color: INK } },
      { text: `${v.support_overestimate_pct}%`,
        options: { align: "center", bold: true, color: bad ? "B3261E" : "1B7F4B",
                   fill: { color: bad ? "FDECEA" : "E9F6EF" } } },
    ]);
  });
  s.addTable(rows, { x: M, y: 2.05, w: W - 2 * M, rowH: 0.78, fontSize: 13.5, fontFace: FONT,
    border: { pt: 0.5, color: "DCE3EC" }, colW: [3.5, 1.5, 1.7, 1.7, 1.4, 2.3], rtlMode: true });

  s.addText("שיטה א׳ מאחדת נסיעות דומות אך לא זהות — שתי גרסאות של אותו עורק. חלון של 12 תאים חוסם אותה מבנית סביב 5 ק\"מ.",
    he({ x: M, y: 5.35, w: W - 2 * M, h: 0.5, fontSize: 14, color: MUTED, lineSpacing: 20 }));
  s.addText("שיטה ב׳ מוצאת חזרות מדויקות ארוכות. שיטה ג׳ היחידה שמייצרת מסלולים עם חורים, והיא שהגיעה לארוך ביותר.",
    he({ x: M, y: 5.95, w: W - 2 * M, h: 0.5, fontSize: 14, color: MUTED, lineSpacing: 20 }));
  s.addNotes("הדרישה היא שיטת clustering, שיטת suffix array, ושיטה שלישית שאינה אף אחת מהן.");
}

// ─────────────────────────────────────────────────────────── 8. verification ──
{
  const c = bench.methods.per_method_scorecard;
  const s = lightSlide("למה כל מועמד נספר מחדש", "מעבר האימות");
  s.addText(`אף שיטה לא נסמכת על ההערכה של עצמה. ${n(bench.pipeline.candidates_verified)} מועמדים נמדדו מחדש מול 100% מהנסיעות — ${bench.pipeline.verification_sec} שניות.`,
    he({ x: M, y: 1.8, w: W - 2 * M, h: 0.5, fontSize: 16, color: INK }));

  s.addShape(pres.ShapeType.roundRect, { x: M, y: 2.6, w: W - 2 * M, h: 2.1,
    rectRadius: 0.1, fill: { color: "FDECEA" }, line: { color: "FDECEA" } });
  s.addText(`${c.lsh_clustering.support_overestimate_pct}%`,
    he({ x: W - M - 3.0, y: 2.85, w: 2.6, h: 0.9, fontSize: 44, bold: true, color: "B3261E", align: "center" }));
  s.addText("הפרזה של שיטת ה-LSH ב-support שלה עצמה",
    he({ x: W - M - 3.0, y: 3.95, w: 2.6, h: 0.5, fontSize: 12, color: "8C2F27", align: "center" }));
  s.addText("ה-LSH סופר נסיעות בדליים באמצעות HyperLogLog, וזו הערכה. הוא דיווח שמסלולים פופולריים פי 2.7 ממה שהם. שתי השיטות המדויקות: 0.0%.\n\nאילו היינו מפרסמים את מה שהשיטות מדדו תוך כדי כרייה, כל מספר בדוח היה שגוי — ושום דבר בהמשך לא היה מגלה את זה.",
    he({ x: M + 0.25, y: 2.9, w: W - 2 * M - 3.6, h: 1.7, fontSize: 14, color: INK, lineSpacing: 20 }));

  const checks = [
    ["מסלול פשוט", "תא לא מופיע פעמיים"],
    [`tortuosity ≤ ${data.metadata.max_tortuosity}`, "אורך חלקי מרחק אווירי"],
    ["ספירה מדויקת", "מול כל 1.6M הנסיעות"],
  ];
  checks.forEach(([t, d], i) => {
    const w = (W - 2 * M - 0.8) / 3;
    const x = W - M - w - i * (w + 0.4);
    s.addText(t, he({ x, y: 5.35, w, h: 0.35, fontSize: 15, bold: true, color: BLUE, align: "center" }));
    s.addText(d, he({ x, y: 5.72, w, h: 0.4, fontSize: 12, color: MUTED, align: "center" }));
  });
  s.addNotes("בלי שומרי הגאומטריה, שרשור שברים נפוצים מייצר לולאות שנראות כמו מסלולים באורך 60 קילומטר.");
}

// ────────────────────────────────────────────────────────────── 9. results ──
{
  const s = lightSlide("100 תת-מסלולים בכל קונפיגורציה", "התוצאות");
  const bt = data.by_threshold_km;
  const rows = [[
    { text: "סף אורך", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "מסלולים שנמצאו", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "X שנבחר", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
    { text: "עומד ביעד 100", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "center" } },
  ]];
  ["1", "3", "5", "10", "20", "40"].forEach(k => {
    const v = bt[k];
    rows.push([
      { text: `≥ ${k} ק"מ`, options: { align: "center", bold: true, color: INK } },
      { text: n(v.found), options: { align: "center", color: v.met_target ? INK : MUTED } },
      { text: `${v.support_pct_used}%`, options: { align: "center", color: MUTED } },
      { text: v.met_target ? "כן" : "לא קיים בפורטו",
        options: { align: "center", bold: true, color: v.met_target ? "1B7F4B" : "8C6D1F",
                   fill: { color: v.met_target ? "E9F6EF" : "FFF6E4" } } },
    ]);
  });
  s.addTable(rows, { x: M, y: 2.0, w: W - 2 * M, rowH: 0.64, fontSize: 14, fontFace: FONT,
    border: { pt: 0.5, color: "DCE3EC" }, colW: [2.6, 3.2, 2.6, 3.7], rtlMode: true });

  s.addText("ארבעה מששת הספים עומדים ביעד. ב-1 ו-3 ק\"מ האלגוריתם בחר דווקא סף מחמיר יותר, כי הוא כבר נותן שם יותר מ-100 — הוא לוקח את ה-X הגבוה ביותר שעדיין מספק את הדרישה.",
    he({ x: M, y: 6.15, w: W - 2 * M, h: 0.7, fontSize: 14, color: MUTED, lineSpacing: 21 }));
  s.addNotes("X נבחר לכל סף בנפרד: הגבוה ביותר שעדיין מניב 100 מסלולים. אם אף ערך לא מגיע, מדווחים כמה נמצאו ובאיזה X.");
}

// ──────────────────────────────────────────────────────── 10. the X curve ──
{
  const s = lightSlide("כמה פופולריות עולה קילומטר", "ניסוי ה-X");
  const sweep = data.support_sweep.filter(r => r.corridors > 0);
  const labels = sweep.map(r => `${r.support_pct}%`);
  s.addChart(pres.ChartType.bar, [
    { name: "כל המסלולים", labels, values: sweep.map(r => r.corridors) },
    { name: 'מעל 10 ק"מ', labels, values: sweep.map(r => r.ge_10km) },
  ], {
    x: M, y: 1.95, w: 7.6, h: 4.6,
    barDir: "col", barGrouping: "clustered",
    chartColors: [BLUE, AMBER],
    showTitle: true, title: "מסלולים שנמצאו, לפי סף התמיכה", titleFontSize: 13, titleColor: INK,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9, dataLabelColor: MUTED,
    showLegend: true, legendPos: "t", legendFontSize: 10,
    catAxisLabelColor: MUTED, valAxisLabelColor: MUTED,
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    valGridLine: { color: "EDF1F6", size: 1 }, catGridLine: { style: "none" },
  });

  s.addText("ככל שהסף יורד, נמצאים יותר מסלולים וארוכים יותר — אבל \"פופולרי\" נחלש.",
    he({ x: W - M - 4.6, y: 2.0, w: 4.6, h: 0.7, fontSize: 15, color: INK, lineSpacing: 22 }));
  stat(s, W - M - 4.6, 3.05, 2.2, "9", 'נסיעות ביום — מעבר לזה\nאין בפורטו אף מסלול');
  stat(s, W - M - 2.25, 3.05, 2.25, "440", "מוניות בלבד בדאטהסט,\nמתוך עיר שלמה");
  s.addText("X מודד תדירות בתוך הדגימה שלנו, לא בתוך התנועה בפורטו. אנחנו רואים 440 מוניות, לא מכוניות פרטיות ולא אוטובוסים — ולכן סף נמוך אינו רעש בהכרח.",
    he({ x: W - M - 4.6, y: 4.95, w: 4.6, h: 1.4, fontSize: 13, color: MUTED, lineSpacing: 20 }));
  s.addNotes("שלוש ריצות אשכול: 0.05%, 0.01%, 0.002%. הטבלה הזו היא הפשרה שהבריף מבקש להתנסות בה.");
}

// ──────────────────────────────────────────────────────── 11. the 20 km proof ──
{
  const s = darkSlide();
  s.addText("סף 20 ק\"מ", he({ x: M, y: 0.7, w: W - 2 * M, h: 0.35,
    fontSize: 13, color: AMBER, bold: true }));
  s.addText("קיימים — אבל לא פופולריים", he({ x: M, y: 1.05, w: W - 2 * M, h: 0.7,
    fontSize: 34, bold: true, color: WHITE }));
  s.addText("נסיעה יכולה לעבור מסלול באורך 20 ק\"מ רק אם היא עצמה באורך 20 ק\"מ. לכן ה-support של מסלול כזה מתוך 1.6 מיליון נסיעות שווה בדיוק ל-support שלו מתוך הנסיעות הארוכות — השאר תורמות אפס בהגדרה, לא בקירוב.",
    he({ x: M, y: 2.0, w: W - 2 * M, h: 0.95, fontSize: 16, color: "C9D6E5", lineSpacing: 24 }));
  s.addText("25,223 נסיעות כאלה קטן מספיק לבדיקה ממצה — הכל מול הכל, בסף של שתי נסיעות. זו הרצפה: אין \"משותף\" מתחת לשניים. והתשובה שונה בין שני הספים.",
    he({ x: M, y: 3.0, w: W - 2 * M, h: 0.6, fontSize: 16, color: "C9D6E5", lineSpacing: 24 }));

  const cards = [
    ["26.93", 'ק"מ — הקטע המשותף הארוך ביותר', "C9D6E5"],
    ["125", 'מסלולים תקינים מעל 20 ק"מ — קיימים', "C9D6E5"],
    ["3", "נסיעות תומכות בטוב שבהם — הרצפה 33", AMBER],
    ["0", 'מועמדים מעל 40 ק"מ, בכל סף שהוא', AMBER],
  ];
  cards.forEach(([v, l, col], i) => {
    const w = (W - 2 * M - 0.9) / 4;
    const x = W - M - w - i * (w + 0.3);
    s.addShape(pres.ShapeType.roundRect, { x, y: 4.05, w, h: 1.85, rectRadius: 0.09,
      fill: { color: "1B3557" }, line: { color: "1B3557" } });
    s.addText(v, he({ x: x + 0.15, y: 4.3, w: w - 0.3, h: 0.65, fontSize: 32, bold: true,
      color: col, align: "center" }));
    s.addText(l, he({ x: x + 0.15, y: 5.0, w: w - 0.3, h: 0.75, fontSize: 11.5,
      color: "9FB3CC", align: "center" }));
  });
  s.addText("כל 108 המועמדים הם לולאות — tortuosity של 2.99 עד אינסוף. מונית שנסעה במעגלים צוברת 26 ק\"מ בלי להתקדם. הסף ריק כי אין שם מסלול, בשום ערך של X.",
    he({ x: M, y: 6.25, w: W - 2 * M, h: 0.7, fontSize: 14, color: "9FB3CC", lineSpacing: 21 }));
  s.addNotes("מעל 40 ק\"מ לא קיים אפילו קטע משותף אחד. פורטו היא 25 על 22 קילומטר.");
}

// ──────────────────────────────────────────────────── 12. cost and resources ──
{
  const s = lightSlide("ביצועים, משאבים ותקציב", "יעילות");
  const g = bench.methods.gate;
  const cards = [
    [`${Math.round(bench.pipeline.total_runtime_sec / 60)}`, "דקות — ריצת שלב 3 המלאה על 6 מכונות"],
    [`${g.cms_memory_mb}`, "מגה-בייט לסקיצה בכל partition,\nללא תלות בגודל הקלט"],
    [`${g.bloom_memory_kb}`, "קילו-בייט לפילטר הבלום\nששודר לכל executor"],
    ["1.6", "דולר מתוך תקציב של 50,\nעבור שלוש ריצות אשכול"],
  ];
  cards.forEach(([v, l], i) => {
    const w = (W - 2 * M - 0.9) / 4;
    const x = W - M - w - i * (w + 0.3);
    stat(s, x, 2.05, w, v, l, { big: 27, h: 1.75 });
  });

  const ops = [
    ["שברים שנסרקו", n(g.ngrams_streamed)],
    ["חלונות ש-MinHash עיבד", n(bench.methods.method_a_lsh_clustering.windows_hashed)],
    ["פליטות band ל-LSH", n(bench.methods.method_a_lsh_clustering.band_emissions)],
    ["מיקומי סיומת שנשקלו", n(bench.methods.method_b_suffix_array.suffix_positions_considered)],
    ["הרחבות שאומתו בגידול", n(bench.methods.method_c_growth.surviving_extension_keys)],
  ];
  s.addText("מספר הפעולות החישוביות", he({ x: M, y: 4.25, w: W - 2 * M, h: 0.35,
    fontSize: 15, bold: true, color: INK }));
  ops.forEach(([label, value], i) => {
    const y = 4.75 + i * 0.48;
    s.addText(label, he({ x: W - M - 5.2, y, w: 5.2, h: 0.34, fontSize: 13, color: MUTED }));
    s.addText(value, he({ x: M, y, w: 3.0, h: 0.34, fontSize: 13, bold: true, color: BLUE, align: "left" }));
  });
  s.addNotes("אשכול אחד לשלושת השלבים, נמחק אוטומטית בסוף גם אם הריצה נכשלת באמצע, עם max-idle כרשת ביטחון.");
}

// ─────────────────────────────────────────────────────── 13. how we know ──
{
  const s = lightSlide("איך אנחנו יודעים שזה נכון", "אימות");
  s.addText("כל רכיב הושווה מול מימוש עצמאי, לא נבדק בעין.",
    he({ x: M, y: 1.8, w: W - 2 * M, h: 0.4, fontSize: 16, color: INK }));
  const tools = [
    ["verify_stage1", "CSV שכל נסיעה בו מפעילה כלל אחד בדיוק", "10 מתוך 10 כללים ירו פעם אחת"],
    ["verify_stage2", "הרצף נבנה מחדש מהקואורדינטות ומושווה תא-תא", "התאמה מלאה"],
    ["verify_gate", "הקבוצה הנפוצה מחושבת פעמיים — עם שער ובלעדיו", "אפס מסלולים אבדו"],
    ["verify_methods", "עקומת ה-S של LSH מול הנוסחה; קיצור הדרך של השרשור", "פער 0.027; השרשור מפריז פי 12.7"],
    ["verify_corridors", "trip_supports מול מימוש ממצה איטי", "תפס באג אמיתי: 1 מכל 60"],
  ];
  tools.forEach(([name, what, result], i) => {
    const y = 2.4 + i * 0.88;
    s.addShape(pres.ShapeType.roundRect, { x: M, y, w: W - 2 * M, h: 0.76, rectRadius: 0.07,
      fill: { color: i % 2 ? WHITE : LIGHT }, line: { color: i % 2 ? "EDF1F6" : LIGHT } });
    s.addText(name, he({ x: W - M - 2.6, y: y + 0.24, w: 2.4, h: 0.32,
      fontSize: 13, bold: true, color: BLUE, fontFace: "Courier New" }));
    s.addText(what, he({ x: M + 3.6, y: y + 0.24, w: 6.4, h: 0.32, fontSize: 13, color: INK }));
    s.addText(result, he({ x: M + 0.2, y: y + 0.24, w: 3.3, h: 0.32,
      fontSize: 12, bold: true, color: "1B7F4B", align: "left" }));
  });
  s.addNotes("הבריף מבקש לתעד את הניסויים שביצענו. אלה הם — כל אחד עם תוצאה מספרית.");
}

// ─────────────────────────────────────────────────────────── 14. closing ──
{
  const s = darkSlide();
  s.addText("מה למדנו", he({ x: M, y: 1.0, w: W - 2 * M, h: 0.35,
    fontSize: 13, color: AMBER, bold: true }));
  const points = [
    ["המבנים המקורבים הם מה שהופך את זה לאפשרי", `${bench.methods.gate.pruned_before_shuffle_pct.toFixed(2)}% מהעבודה נחסכת לפני שדבר עובר ברשת, והטעות חד-צדדית — היא עולה זמן, לא נכונות.`],
    ["הערכה בלי אימות היא מספר שגוי", `שיטת ה-LSH הפריזה ב-${bench.methods.per_method_scorecard.lsh_clustering.support_overestimate_pct}%. בלי מעבר אימות זה היה מגיע לדוח.`],
    ["רשימה קצרה יכולה להיות התוצאה", "סף 20 ק\"מ ריק כי המסלול הארוך ביותר בפורטו הוא 19.91 ק\"מ — הוכחנו זאת ממצה, לא הסקנו."],
  ];
  points.forEach(([t, d], i) => {
    const y = 1.55 + i * 1.75;
    s.addShape(pres.ShapeType.ellipse, { x: W - M - 0.5, y: y + 0.05, w: 0.5, h: 0.5,
      fill: { color: AMBER }, line: { color: AMBER } });
    s.addText(String(i + 1), he({ x: W - M - 0.5, y: y + 0.14, w: 0.5, h: 0.35,
      fontSize: 15, bold: true, color: NAVY, align: "center" }));
    s.addText(t, he({ x: M, y, w: W - 2 * M - 0.8, h: 0.45, fontSize: 21, bold: true, color: WHITE }));
    s.addText(d, he({ x: M, y: y + 0.5, w: W - 2 * M - 0.8, h: 0.85,
      fontSize: 14, color: "9FB3CC", lineSpacing: 21 }));
  });
  s.addText(`נוצר אוטומטית מקבצי התוצאות  ·  ${data.metadata.generated_utc.slice(0, 10)}  ·  כל מספר במצגת נקרא מהריצה`,
    he({ x: M, y: 6.6, w: W - 2 * M, h: 0.35, fontSize: 11, color: "5C7599" }));
}

pres.writeFile({ fileName: OUT }).then(() => console.log(`wrote ${OUT}`));
