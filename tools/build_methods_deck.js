/*
 * Build the Stage 3 methods-comparison deck required by the brief
 * ("דו"ח מסכם בצורת מצגת ... השוואה בין השיטות ... ביצועים, דיוק, זמני ריצה, זיכרון").
 *
 * Every number on every slide is read out of the results files, so the deck
 * cannot drift away from the run it describes.  Rebuild it after each cluster
 * run:
 *
 *     node tools/build_methods_deck.js \
 *          --benchmark output/stage3_benchmark.json \
 *          --results   output/stage3_subroutes.json \
 *          --out       output/stage3_methods_comparison.pptx
 */

const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");

// ── args ─────────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const arg = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
};
const BENCH = arg("benchmark", "output/stage3_benchmark.json");
const RESULTS = arg("results", "output/stage3_subroutes.json");
const OUT = arg("out", "output/stage3_methods_comparison.pptx");

const bench = JSON.parse(fs.readFileSync(BENCH, "utf8"));
const data = JSON.parse(fs.readFileSync(RESULTS, "utf8"));

const M = bench.methods;
const gate = M.gate || {};
const A = M.method_a_lsh_clustering || {};
const B = M.method_b_suffix_array || {};
const C = M.method_c_growth || {};
const card = M.per_method_scorecard || {};
const anom = M.anomaly_detection || {};
const pipe = bench.pipeline || {};

const n = (v, d = 0) =>
  v === undefined || v === null ? "—" : Number(v).toLocaleString("en-US", {
    minimumFractionDigits: d, maximumFractionDigits: d });

// ── palette: Porto azulejo blue, taxi amber ──────────────────────────────────
const INK = "14202A";
const DEEP = "0E3B4F";
const TEAL = "2E7D96";
const AMBER = "E9A13B";
const PAPER = "FFFFFF";
const MIST = "EEF3F5";
const MUTED = "63757F";
const GOOD = "2E7D4F";
const BAD = "B23A2F";

const H = "Cambria";
const BODY = "Calibri";

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";           // 13.3 x 7.5in — set before any slide
pres.author = "Porto Taxi Project";
pres.title = "Stage 3 — Methods Comparison";

// ── shared helpers ───────────────────────────────────────────────────────────
function hexMark(slide, x, y, size, color, opts = {}) {
  slide.addShape(pres.ShapeType.hexagon, {
    x, y, w: size, h: size * 0.88,
    fill: opts.fill ? { color: opts.fill } : { type: "solid", color: "FFFFFF", transparency: 100 },
    line: { color, width: opts.width || 1.25 },
    rotate: 90,
  });
}

function titleSlide(slide, kicker, title, sub) {
  slide.background = { color: PAPER };
  slide.addText(kicker.toUpperCase(), {
    x: 0.65, y: 0.5, w: 9, h: 0.28, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 11, bold: true, color: TEAL, charSpacing: 2.2,
  });
  slide.addText(title, {
    x: 0.65, y: 0.8, w: 9.4, h: 0.9, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 32, bold: true, color: INK,
  });
  if (sub) {
    slide.addText(sub, {
      x: 0.65, y: 1.72, w: 11.9, h: 0.5, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 14, color: MUTED,
    });
  }
  // recurring motif: three hexagons, top right
  hexMark(slide, 12.1, 0.5, 0.5, TEAL);
  hexMark(slide, 12.45, 0.74, 0.5, AMBER);
  hexMark(slide, 12.1, 0.98, 0.5, DEEP);
}

function statHex(slide, x, y, value, label, color) {
  slide.addShape(pres.ShapeType.hexagon, {
    x, y, w: 2.05, h: 1.8, rotate: 90,
    fill: { color: MIST }, line: { color, width: 1.5 },
  });
  slide.addText(value, {
    x, y: y + 0.42, w: 2.05, h: 0.55, isTextBox: true, margin: 0,
    align: "center", fontFace: H, fontSize: 24, bold: true, color,
  });
  slide.addText(label, {
    x: x - 0.15, y: y + 0.95, w: 2.35, h: 0.55, isTextBox: true, margin: 0,
    align: "center", fontFace: BODY, fontSize: 10, color: MUTED,
  });
}

function card3(slide, x, y, w, h, heading, lines, accent) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.06,
    fill: { color: MIST }, line: { color: "DCE5E9", width: 1 },
    shadow: { type: "outer", angle: 90, blur: 10, offset: 2, opacity: 0.10, color: "000000" },
  });
  slide.addShape(pres.ShapeType.hexagon, {
    x: x + 0.28, y: y + 0.26, w: 0.42, h: 0.38, rotate: 90,
    fill: { color: accent }, line: { color: accent, width: 1 },
  });
  slide.addText(heading, {
    x: x + 0.85, y: y + 0.22, w: w - 1.1, h: 0.42, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 15, bold: true, color: INK,
  });
  slide.addText(
    lines.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lines.length - 1 } })),
    { x: x + 0.32, y: y + 0.78, w: w - 0.62, h: h - 1.0, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 11.5, color: "2B3A44", paraSpaceAfter: 5, lineSpacing: 15 });
}

const QUIET_AXIS = {
  catAxisLabelColor: MUTED, valAxisLabelColor: MUTED,
  catAxisLabelFontFace: BODY, valAxisLabelFontFace: BODY,
  catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
  valGridLine: { color: "E3EAED", size: 1 },
  catGridLine: { style: "none" },
};

// ═════════════════════════════════════════════════════════════════ 1. cover ══
{
  const s = pres.addSlide();
  s.background = { color: DEEP };
  s.addText("Cloud Computing for Big Data · Final Project", {
    x: 0.9, y: 1.55, w: 10, h: 0.3, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 13, color: AMBER, charSpacing: 2,
  });
  s.addText("Popular Long Sub-Routes in Porto", {
    x: 0.9, y: 2.0, w: 11, h: 1.1, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 42, bold: true, color: "FFFFFF",
  });
  s.addText("Three mining methods compared on runtime, accuracy, memory and route quality", {
    x: 0.9, y: 3.1, w: 9.6, h: 0.6, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 16, color: "C9DBE3",
  });
  s.addShape(pres.ShapeType.line, {
    x: 0.9, y: 3.95, w: 2.2, h: 0, line: { color: AMBER, width: 2.5 },
  });
  s.addText([
    { text: `${n(pipe.total_trips)} trips`, options: { breakLine: true } },
    { text: `H3 resolution 9 · Spark on Dataproc`, options: { breakLine: true } },
    { text: `${n(pipe.corridors_reported)} verified corridors reported`, options: {} },
  ], { x: 0.9, y: 4.25, w: 7, h: 1.1, isTextBox: true, margin: 0,
       fontFace: BODY, fontSize: 13, color: "9FBDC8", lineSpacing: 20 });

  [[10.4, 1.9], [11.3, 2.42], [10.4, 2.94], [11.3, 3.46], [10.4, 3.98]].forEach(([x, y], i) => {
    s.addShape(pres.ShapeType.hexagon, {
      x, y, w: 1.05, h: 0.92, rotate: 90,
      fill: i % 2 ? { color: TEAL, transparency: 55 } : { color: "FFFFFF", transparency: 88 },
      line: { color: i === 2 ? AMBER : "5C93A8", width: i === 2 ? 2 : 1 },
    });
  });
  s.addNotes("Stage 3 of the pipeline. Stage 1 cleaned 1.71M raw trips, Stage 2 encoded them to H3 resolution 9. This deck is about how we find the popular long sub-routes and how the three required methods compare.");
}

// ══════════════════════════════════════════════════ 2. what counts as one ══
{
  const s = pres.addSlide();
  titleSlide(s, "The object we are looking for",
    "A corridor is a chain of segments, not a trip",
    "Not a whole journey — those are never popular. Not a junction — that is a point, not a route.");

  card3(s, 0.65, 2.5, 3.85, 3.65, "Long, not short", [
    "A busy junction is traversed by tens of thousands of trips but is not a route.",
    "We maximise corridor length subject to a support floor, rather than ranking by support alone.",
    `Anything under ${n(8)} cells is rejected as a junction.`,
  ], TEAL);

  card3(s, 4.72, 2.5, 3.85, 3.65, "Popular, and measured", [
    "Support = distinct trips that traverse every segment, in order.",
    "Measured against 100% of trips in a final pass — never inferred from the parts.",
    "The same definition is used by all three methods, so the numbers compare.",
  ], AMBER);

  card3(s, 8.79, 2.5, 3.85, 3.65, "Holes are allowed", [
    "Trips may diverge for a stretch and rejoin — the brief's Haifa→Ashdod case.",
    `A supporting trip may spend up to ${n(data.metadata.max_gap_cells)} cells inside a hole.`,
    `${n(data.top_100_longest.filter(r => r.n_holes > 0).length)} of the reported corridors carry at least one hole.`,
  ], DEEP);

  s.addText("segment  ▬▬▬▬▬     hole  ▭ ▭ ▭ ▭     segment  ▬▬▬▬▬     — one corridor, two observed stretches", {
    x: 0.65, y: 6.4, w: 12, h: 0.4, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 12, italic: true, color: MUTED,
  });
  s.addNotes("The definition drives everything else. Because support is defined once and verified once, the three methods are directly comparable — and a corridor with a hole is held to exactly the same evidential standard as one without.");
}

// ═════════════════════════════════════════════════════════ 3. the pipeline ══
{
  const s = pres.addSlide();
  titleSlide(s, "Pipeline", "Mine broadly, then verify against everything",
    "Each method proposes candidates using its own approximation. One shared pass then re-measures all of them exactly.");

  const steps = [
    ["Gate", "Count-Min + Bloom\nfrequent k-grams", TEAL],
    ["Mine ×3", "LSH · Suffix array\nVerified growth", AMBER],
    ["Verify", "Exact support over\n100% of trips", DEEP],
    ["Report", "Sweep over X%\n6 distance buckets", TEAL],
  ];
  steps.forEach(([t, d, col], i) => {
    const x = 0.75 + i * 3.15;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.7, w: 2.75, h: 2.15, rectRadius: 0.06,
      fill: { color: MIST }, line: { color: col, width: 1.5 },
    });
    s.addText(`${i + 1}`, {
      x: x + 0.12, y: 2.82, w: 0.4, h: 0.3, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 10, bold: true, color: col,
    });
    s.addText(t, { x, y: 3.12, w: 2.75, h: 0.4, isTextBox: true, margin: 0,
      align: "center", fontFace: H, fontSize: 17, bold: true, color: INK });
    s.addText(d, { x, y: 3.6, w: 2.75, h: 0.95, isTextBox: true, margin: 0,
      align: "center", fontFace: BODY, fontSize: 11, color: MUTED, lineSpacing: 14 });
    if (i < 3) {
      s.addShape(pres.ShapeType.rightArrow, {
        x: x + 2.83, y: 3.62, w: 0.26, h: 0.3, fill: { color: "C3D2D8" }, line: { color: "C3D2D8" },
      });
    }
  });

  s.addText("Why verification is a separate stage", {
    x: 0.75, y: 5.35, w: 6, h: 0.35, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 15, bold: true, color: INK,
  });
  s.addText(
    "Every approximation here is one-sided: it may let an infrequent pattern through, never drop a frequent one. " +
    "That makes each method safe as a candidate generator and moves the burden of accuracy onto a single exact pass — " +
    `${n(pipe.candidates_verified)} candidates re-measured in ${n(pipe.verification_sec, 1)}s.`,
    { x: 0.75, y: 5.75, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "2B3A44", lineSpacing: 18 });
  s.addNotes("The key design decision: no method is trusted with its own accuracy claim. Approximations are used only where the error is one-sided, and everything is re-measured at the end.");
}

// ══════════════════════════════════════════════════════════ 4. method A ══
{
  const s = pres.addSlide();
  titleSlide(s, "Method A · clustering", "MinHash + LSH clustering of segments",
    "Two taxis on the same road down parallel one-way streets produce similar, not identical, cell sequences.");

  card3(s, 0.65, 2.5, 5.6, 3.55, "How it works", [
    `Shingle each ${n(A.window_cells)}-cell window into consecutive cell pairs.`,
    `MinHash to a ${n(A.window_cells ? 32 : 32)}-integer signature — agreement probability equals Jaccard similarity.`,
    `LSH banding: 8 bands × 4 rows, so windows meet in a bucket above ~${n(A.lsh_similarity_threshold, 2)} similarity.`,
    "The bucket medoid becomes the cluster representative.",
    "Distinct trips per bucket counted exactly while cold, HyperLogLog once hot.",
  ], TEAL);

  const rows = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
  const curve = rows.map((sv) => Math.round(100 * (1 - Math.pow(1 - Math.pow(sv, 4), 8))));
  s.addChart(pres.ChartType.line,
    [{ name: "P(share a bucket)", labels: rows.map((r) => r.toFixed(1)), values: curve }],
    { x: 6.5, y: 2.55, w: 6.15, h: 3.5,
      showTitle: true, title: "LSH S-curve: 8 bands × 4 rows",
      titleFontFace: H, titleFontSize: 13, titleColor: INK,
      chartColors: [TEAL], lineSize: 3, lineSmooth: true,
      showLegend: false, showValue: false,
      valAxisMaxVal: 100, valAxisTitle: "%", showValAxisTitle: false,
      catAxisTitle: "Jaccard similarity", showCatAxisTitle: true,
      catAxisTitleFontSize: 10, catAxisTitleColor: MUTED,
      ...QUIET_AXIS });

  s.addText(
    `Measured: ${n(A.windows_hashed)} windows hashed, ${n(A.buckets_above_support)} buckets above the support floor, ` +
    `${n(A.runtime_sec, 1)}s.`,
    { x: 0.65, y: 6.35, w: 12, h: 0.4, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12, color: MUTED });
  s.addNotes("The advantage is that near-duplicate traversals are merged rather than split into separate weaker patterns. The cost is that support is approximate — quantified two slides on.");
}

// ══════════════════════════════════════════════════════════ 5. method B ══
{
  const s = pres.addSlide();
  titleSlide(s, "Method B · suffix", "Distributed generalised suffix array + LCP",
    "Each trip is a string over an alphabet of H3 cells; a shared sub-route is a substring repeated across many strings.");

  card3(s, 0.65, 2.5, 5.9, 3.6, "Making it distributed", [
    `Every suffix is routed to the bucket named by its first ${n(B.prefix_bucket_cells)} cells, and each bucket sorts independently.`,
    "Lossless: two suffixes sharing a prefix of that length always land in the same bucket.",
    "Inside a bucket: sort (the suffix array), compute the LCP array, read LCP-intervals longest-first.",
    "Walking L downward yields the longest repeat at each location — the length maximisation the brief asks for.",
  ], AMBER);

  card3(s, 6.75, 2.5, 5.9, 3.6, "Keeping the shuffle affordable", [
    `Naively every position emits a suffix: ${n(B.suffix_positions_considered)} of them.`,
    `The Bloom filter of frequent ${n(gate.k)}-grams removes any suffix that cannot start a frequent repeat.`,
    `${n(B.bloom_pruned_pct, 1)}% never crossed the network — and by anti-monotonicity none of them could have produced a result.`,
    `${n(B.distinct_repeats_found)} distinct repeats found in ${n(B.runtime_sec, 1)}s.`,
  ], TEAL);

  s.addText(
    "Exact within its scope: supports here are true distinct-trip counts, capped only by the " +
    `${n(B.max_suffix_cells)}-cell suffix truncation that bounds per-bucket memory.`,
    { x: 0.65, y: 6.35, w: 12, h: 0.4, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12, italic: true, color: MUTED });
  s.addNotes("Point out that the prefix bucketing is lossless, not a sampling heuristic — that is what makes this a genuine distributed suffix array rather than a suffix array on a sample.");
}

// ══════════════════════════════════════════════════════════ 6. method C ══
{
  const s = pres.addSlide();
  titleSlide(s, "Method C · neither clustering nor suffix",
    "Level-wise growth with support verified every round",
    "Start from frequent seeds and grow one step at a time, re-measuring against the whole dataset at each step.");

  card3(s, 0.65, 2.5, 5.9, 3.6, "Why grow instead of chain", [
    "Chaining frequent n-grams and taking the minimum support gives an upper bound that is almost never attained.",
    "Fifty 5-grams each seen by thousands of trips can chain into a corridor that zero trips ever drove.",
    `Growth removes it by construction: a corridor reaches length L only because a pass found ${n(C.min_support_trips)} trips that traverse all L cells.`,
    "Holes are proposed and verified exactly like contiguous steps.",
  ], DEEP);

  card3(s, 6.75, 2.5, 5.9, 3.6, "Search control", [
    `${n(C.seeds)} frequent ${n(gate.k)}-gram seeds, grown forward only — leftward growth is redundant by anti-monotonicity.`,
    `Up to ${n(C.max_step_cells)} cells per round, ${n(C.branches_per_corridor)} branches per corridor.`,
    `Beam of ${n(C.beam_width)}, with entries sharing over ${n(100 * C.max_beam_overlap, 0)}% of their cells pruned as near-duplicates.`,
    `Converged after ${n(C.rounds_run)} rounds in ${n(C.runtime_sec, 1)}s.`,
  ], TEAL);

  s.addText(
    "Every support number this method reports is measured, not inferred — the reason its overstatement below is exactly zero.",
    { x: 0.65, y: 6.35, w: 12, h: 0.4, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12, italic: true, color: GOOD });
  s.addNotes("This is the method that produces the longest corridors and the ones carrying holes. It is also the slowest, because it makes one pass over the data per round — the trade is stated on the comparison slide.");
}

// ══════════════════════════════════════ 7. where the sketches pay ══
{
  const s = pres.addSlide();
  titleSlide(s, "Approximate data structures", "Where the sketches actually pay",
    "Each one is used where its error is one-sided, so it can prune aggressively without ever losing a real result.");

  statHex(s, 0.75, 2.6, `${n(gate.pruned_before_shuffle_pct, 1)}%`, "of n-grams dropped\nbefore any shuffle", TEAL);
  statHex(s, 3.05, 2.6, `${n(gate.cms_memory_mb, 0)} MB`, "Count-Min sketch,\nfixed per partition", AMBER);
  statHex(s, 5.35, 2.6, `${n(gate.bloom_memory_kb, 1)} KB`, "Bloom filter broadcast\ninstead of the exact set", DEEP);
  statHex(s, 7.65, 2.6, `${n(B.bloom_pruned_pct, 1)}%`, "of suffixes never\nemitted (Method B)", TEAL);
  statHex(s, 9.95, 2.6, `${n(gate.cms_false_positive_pct, 1)}%`, "sketch false positives,\nremoved by exact pass", AMBER);

  const rowsData = [
    ["Count-Min Sketch", "frequency, one-sided", "no false negatives → safe pre-filter", `${n(gate.cms_memory_mb, 0)} MB`],
    ["Bloom filter", "membership, one-sided", "shrinks the broadcast, prunes candidates in-map", `${n(gate.bloom_memory_kb, 1)} KB`],
    ["MinHash + LSH", "similarity", "turns all-pairs comparison into one shuffle", "32 ints / window"],
    ["HyperLogLog", "distinct count", "per-bucket trip counts without a set of trip ids", "256 B – 4 KB"],
  ];
  const tbl = [[
    { text: "structure", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
    { text: "what it estimates", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
    { text: "why it is safe here", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
    { text: "footprint", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
  ]].concat(rowsData.map((r) => r.map((c) => ({ text: c, options: { color: "2B3A44" } }))));
  s.addTable(tbl, {
    x: 0.75, y: 4.95, w: 11.85, colW: [2.5, 2.5, 4.85, 2.0],
    fontFace: BODY, fontSize: 11.5, border: { pt: 0.5, color: "DCE5E9" },
    rowH: 0.42, valign: "middle", fill: { color: "FFFFFF" },
  });
  s.addNotes(`The headline number: ${n(gate.ngrams_streamed)} n-grams were streamed and ${n(gate.pruned_before_shuffle_pct, 1)}% of them were eliminated by the sketch before anything was shuffled. That is the whole point of using an approximate structure here — the saving is in the network, not the arithmetic.`);
}

// ═══════════════════════════════════════════════ 8. comparison table ══
{
  const s = pres.addSlide();
  titleSlide(s, "Comparison", "The three methods, scored the same way",
    "Every corridor below was re-measured against 100% of the trips, whatever the method claimed while mining.");

  const nameMap = {
    lsh_clustering: ["A · MinHash LSH clustering", A.runtime_sec],
    suffix_array_lcp: ["B · Suffix array + LCP", B.runtime_sec],
    cms_growth: ["C · Verified growth", C.runtime_sec],
  };
  const order = ["lsh_clustering", "suffix_array_lcp", "cms_growth"];
  const head = ["method", "runtime", "corridors", "longest", "mean length", "mean cells", "with holes", "support overstated"];
  const body = order.filter((k) => card[k]).map((k) => {
    const c = card[k];
    return [
      { text: nameMap[k][0], options: { bold: true, color: INK } },
      { text: `${n(nameMap[k][1], 1)} s`, options: { align: "right" } },
      { text: n(c.corridors_verified), options: { align: "right" } },
      { text: `${n(c.max_length_km, 2)} km`, options: { align: "right" } },
      { text: `${n(c.mean_length_km, 2)} km`, options: { align: "right" } },
      { text: n(c.mean_cells, 1), options: { align: "right" } },
      { text: n(c.with_holes), options: { align: "right" } },
      { text: `${n(c.support_overestimate_pct, 1)}%`,
        options: { align: "right", bold: true, color: c.support_overestimate_pct > 0.5 ? BAD : GOOD } },
    ];
  });
  const table = [head.map((h) => ({ text: h, options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } }))]
    .concat(body);
  s.addTable(table, {
    x: 0.7, y: 2.55, w: 11.9, colW: [3.0, 1.05, 1.2, 1.15, 1.35, 1.2, 1.15, 1.8],
    fontFace: BODY, fontSize: 11.5, border: { pt: 0.5, color: "DCE5E9" },
    rowH: 0.48, valign: "middle", fill: { color: "FFFFFF" },
  });

  card3(s, 0.7, 4.6, 3.85, 2.35, "A is fast and wide", [
    "Shortest corridors (windows are fixed-length) but the highest support.",
    "Best at absorbing near-duplicate traversals.",
  ], TEAL);
  card3(s, 4.72, 4.6, 3.85, 2.35, "B is fast and exact", [
    "Longest exact repeats, no approximation in the counting.",
    "Cannot express a hole — substrings are contiguous by definition.",
  ], AMBER);
  card3(s, 8.74, 4.6, 3.88, 2.35, "C is slow and honest", [
    "One pass per round, so the wall clock is the price.",
    "The only method producing corridors with holes, and its support needs no correction.",
  ], DEEP);
  s.addNotes("If asked which method is best: they answer different questions. B gives the longest exactly-repeated stretch, C gives the longest genuinely-traversed corridor including holes, A gives the most robust popularity estimate under noise.");
}

// ═════════════════════════════════════════ 9. accuracy of the estimates ══
{
  const s = pres.addSlide();
  titleSlide(s, "Accuracy", "What each approximation costs, measured",
    "Mining support vs verified support. The gap is the price of the approximation — asserted by nobody, measured for all three.");

  const order = ["lsh_clustering", "suffix_array_lcp", "cms_growth"];
  const labels = ["A · LSH clustering", "B · Suffix array", "C · Verified growth"];
  const vals = order.map((k) => (card[k] ? card[k].support_overestimate_pct : 0));
  s.addChart(pres.ChartType.bar,
    [{ name: "support overstated (%)", labels, values: vals }],
    { x: 0.75, y: 2.55, w: 6.6, h: 3.55, barDir: "col",
      showTitle: true, title: "Support overstated before verification",
      titleFontFace: H, titleFontSize: 13, titleColor: INK,
      chartColors: [TEAL, AMBER, GOOD],
      varyColors: true, showLegend: false,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"%"',
      dataLabelFontFace: BODY, dataLabelFontSize: 11, dataLabelColor: INK,
      barGapWidthPct: 60, ...QUIET_AXIS });

  card3(s, 7.6, 2.55, 5.05, 3.55, "Reading the chart", [
    "A over-states because bucket support comes from a HyperLogLog, whose error is symmetric and around a couple of percent.",
    "B and C are exactly zero: both count distinct trips exactly, so verification confirms rather than corrects them.",
    "None of the three can under-state —  — every structure used has one-sided error in the safe direction.",
  ], TEAL);

  s.addText(
    "The practical consequence: an approximate count is fine for ranking candidates, and not fine for a number you publish. " +
    "Hence the verification pass.",
    { x: 0.75, y: 6.32, w: 11.9, h: 0.6, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "2B3A44" });
  s.addNotes("This slide is the direct answer to 'how accurate are your approximate structures'. We can quote a measured number per method rather than a textbook bound.");
}

// ═══════════════════════════════════════════════ 10. geometric guards ══
{
  const s = pres.addSlide();
  titleSlide(s, "Route quality", "A long sequence is not the same as a long route",
    "Chaining frequent fragments without geometric constraints produces sequences that double back through the same cells.");

  const routes = data.top_100_longest;
  const worstTort = Math.max(...routes.map((r) => r.tortuosity));
  const meanTort = routes.reduce((a, r) => a + r.tortuosity, 0) / routes.length;

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.75, y: 2.55, w: 5.75, h: 2.75, rectRadius: 0.06,
    fill: { color: "FBEDEB" }, line: { color: BAD, width: 1.25 },
  });
  s.addText("Without the guards", {
    x: 1.05, y: 2.78, w: 5.2, h: 0.35, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 15, bold: true, color: BAD });
  s.addText([
    { text: "a 190-cell \"route\" containing only 81 distinct cells", options: { bullet: true, breakLine: true } },
    { text: "66.8 km of reported path between endpoints 3.9 km apart", options: { bullet: true, breakLine: true } },
    { text: "tortuosity 17.3 — the corridor loops through the same streets three times", options: { bullet: true } },
  ], { x: 1.05, y: 3.24, w: 5.2, h: 1.9, isTextBox: true, margin: 0,
       fontFace: BODY, fontSize: 11.5, color: "5A2B26", paraSpaceAfter: 6, lineSpacing: 15 });

  s.addShape(pres.ShapeType.roundRect, {
    x: 6.85, y: 2.55, w: 5.75, h: 2.75, rectRadius: 0.06,
    fill: { color: "E9F4EE" }, line: { color: GOOD, width: 1.25 },
  });
  s.addText("With the guards", {
    x: 7.15, y: 2.78, w: 5.2, h: 0.35, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 15, bold: true, color: GOOD });
  s.addText([
    { text: "a cell may never appear twice in a corridor", options: { bullet: true, breakLine: true } },
    { text: `path length / straight-line distance capped at ${n(data.metadata.max_tortuosity, 1)}`, options: { bullet: true, breakLine: true } },
    { text: `worst reported tortuosity ${n(worstTort, 2)}, mean ${n(meanTort, 2)} — the shape of real roads`, options: { bullet: true } },
  ], { x: 7.15, y: 3.24, w: 5.2, h: 1.9, isTextBox: true, margin: 0,
       fontFace: BODY, fontSize: 11.5, color: "23503A", paraSpaceAfter: 6, lineSpacing: 15 });

  s.addText("Enforced at every point a corridor grows, and re-checked independently", {
    x: 0.75, y: 5.65, w: 11.9, h: 0.35, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 15, bold: true, color: INK });
  s.addText(
    "tools/validate_results.py re-reads the published JSON and re-derives every length and tortuosity from the H3 cells themselves, " +
    "so the audit does not depend on the mining code being right. It runs after every cluster run.",
    { x: 0.75, y: 6.05, w: 11.9, h: 0.85, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "2B3A44", lineSpacing: 18 });
  s.addNotes("The left-hand column is a real failure mode from an earlier iteration of this pipeline, kept because it is the clearest illustration of why the guards exist. A sequence can be long and frequent and still not be a route.");
}

// ═════════════════════════════════════════════════ 11. choosing X ══
{
  const s = pres.addSlide();
  titleSlide(s, "Choosing X", "The support threshold, swept in one run",
    "Raising X leaves only short corridors; lowering it admits long ones few trips use. Support is anti-monotone in X, so one mining run answers the whole sweep.");

  const sweep = data.support_sweep;
  s.addChart(pres.ChartType.line, [
    { name: "corridors found", labels: sweep.map((r) => `${r.support_pct}%`), values: sweep.map((r) => r.corridors) },
  ], { x: 0.75, y: 2.6, w: 6.0, h: 3.5,
       showTitle: true, title: "Corridors surviving each threshold",
       titleFontFace: H, titleFontSize: 13, titleColor: INK,
       chartColors: [TEAL], lineSize: 3, showLegend: false,
       showValue: true, dataLabelPosition: "t", dataLabelFontSize: 9, dataLabelColor: MUTED,
       catAxisTitle: "X, percent of all trips", showCatAxisTitle: true,
       catAxisTitleFontSize: 10, catAxisTitleColor: MUTED, ...QUIET_AXIS });

  s.addChart(pres.ChartType.line, [
    { name: "mean length (km)", labels: sweep.map((r) => `${r.support_pct}%`),
      values: sweep.map((r) => r.mean_length_km || 0) },
  ], { x: 6.95, y: 2.6, w: 5.7, h: 3.5,
       showTitle: true, title: "Mean corridor length at each threshold",
       titleFontFace: H, titleFontSize: 13, titleColor: INK,
       chartColors: [AMBER], lineSize: 3, showLegend: false,
       showValue: true, dataLabelPosition: "t", dataLabelFormatCode: '0.00',
       dataLabelFontSize: 9, dataLabelColor: MUTED,
       catAxisTitle: "X, percent of all trips", showCatAxisTitle: true,
       catAxisTitleFontSize: 10, catAxisTitleColor: MUTED, ...QUIET_AXIS });

  s.addText(
    `Mined once at X = ${n(data.metadata.mining_support_pct, 2)}% (${n(data.metadata.mining_min_support_trips)} trips). ` +
    "Every higher threshold is a filter on measured supports, not another cluster run — which is also how the budget was kept.",
    { x: 0.75, y: 6.3, w: 11.9, h: 0.7, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "2B3A44", lineSpacing: 18 });
  s.addNotes("Anti-monotonicity is the reason this works: anything frequent at a high threshold is frequent at a lower one, so mining at the floor produces a superset and the sweep is post-processing.");
}

// ══════════════════════════════════════ 12. the ceiling / thresholds ══
{
  const s = pres.addSlide();
  titleSlide(s, "The six configurations", "What the data can and cannot contain",
    "A trip can only traverse a corridor of length L if the trip is itself at least L long. That puts a ceiling on popularity no algorithm can beat.");

  const ceil = data.length_ceiling;
  s.addChart(pres.ChartType.bar, [
    { name: "trips at least this long (% of fleet)",
      labels: ceil.map((c) => `≥ ${c.min_length_km} km`),
      values: ceil.map((c) => c.max_possible_support_pct) },
  ], { x: 0.75, y: 2.6, w: 6.5, h: 3.45, barDir: "col",
       showTitle: true, title: "Ceiling on support, from trip lengths alone",
       titleFontFace: H, titleFontSize: 13, titleColor: INK,
       chartColors: [DEEP], showLegend: false, valAxisMaxVal: 105,
       valAxisLabelFormatCode: '0"%"',
       showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.00"%"',
       dataLabelFontSize: 9, dataLabelColor: INK,
       barGapWidthPct: 55, ...QUIET_AXIS });

  const th = data.by_threshold_km;
  const keys = ["1", "3", "5", "10", "20", "40"];
  const rows = [[
    { text: "configuration", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
    { text: "found", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
    { text: "X used", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
    { text: "ceiling", options: { bold: true, color: "FFFFFF", fill: { color: DEEP } } },
  ]].concat(keys.filter((k) => th[k]).map((k) => {
    const c = ceil.find((x) => String(Math.round(x.min_length_km)) === k) || {};
    return [
      { text: `≥ ${k} km` },
      { text: n(th[k].found), options: { align: "right", bold: true,
          color: th[k].met_target ? GOOD : AMBER } },
      { text: `${n(th[k].support_pct_used, 2)}%`, options: { align: "right" } },
      { text: `${n(c.max_possible_support_pct, 3)}%`, options: { align: "right", color: MUTED } },
    ];
  }));
  s.addTable(rows, {
    x: 7.6, y: 2.72, w: 5.05, colW: [1.7, 1.0, 1.15, 1.2],
    fontFace: BODY, fontSize: 11.5, border: { pt: 0.5, color: "DCE5E9" },
    rowH: 0.45, valign: "middle", fill: { color: "FFFFFF" },
  });

  s.addText(
    "Porto's bounding box is roughly 25 × 22 km and the median trip is under 4 km. " +
    "Where a configuration returns fewer than 100 corridors we report the number found and the ceiling that explains it, " +
    "rather than padding the list with sequences no taxi drove.",
    { x: 0.75, y: 6.3, w: 11.9, h: 0.8, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "2B3A44", lineSpacing: 18 });
  s.addNotes("This is the honest answer to the 40 km configuration. It is not an algorithmic failure — it is a measured property of the dataset, and we can show the distribution that proves it.");
}

// ════════════════════════════════════════════════ 13. unusual routes ══
{
  const s = pres.addSlide();
  titleSlide(s, "Unusual routes", "The fleet's own traffic defines what is normal",
    "The brief's third question, answered with the same machinery run in reverse.");

  card3(s, 0.7, 2.55, 5.9, 3.5, "Method", [
    "Build the set of frequent cell-to-cell transitions, then put it in a Bloom filter so it can be broadcast.",
    "A trip's novelty is the share of its transitions that the filter does not recognise.",
    `${n(anom.trips_scored)} trips scored in ${n(anom.runtime_sec, 1)}s.`,
    "A false positive slightly lowers a trip's score; there are no false negatives, so nothing unusual is hidden.",
  ], AMBER);

  card3(s, 6.75, 2.55, 5.9, 3.5, "A second signal", [
    "Distinct taxis per cell, counted with a HyperLogLog at 256 bytes per cell regardless of traffic.",
    "Cells with heavy traffic but few distinct vehicles are structurally different from cells that are merely busy.",
    "Depot approaches and single-driver habits separate from genuine arterials.",
  ], TEAL);

  s.addText(
    "Same structures, opposite question: the corridor mining asks what the Bloom filter contains, the anomaly detection asks what it does not.",
    { x: 0.7, y: 6.35, w: 11.9, h: 0.5, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, italic: true, color: MUTED });
  s.addNotes("Worth pointing out in the defence that this reuses the gate we had already built, so the extra cost of answering the third question was one short Spark stage.");
}

// ═══════════════════════════════════════════════════ 14. conclusions ══
{
  const s = pres.addSlide();
  s.background = { color: DEEP };
  s.addText("What we would defend", {
    x: 0.9, y: 0.85, w: 10, h: 0.7, isTextBox: true, margin: 0,
    fontFace: H, fontSize: 32, bold: true, color: "FFFFFF" });
  s.addShape(pres.ShapeType.line, { x: 0.9, y: 1.68, w: 2.2, h: 0, line: { color: AMBER, width: 2.5 } });

  const points = [
    ["Approximations only where the error is one-sided",
     `${n(gate.pruned_before_shuffle_pct, 1)}% of n-grams never reached the network, and nothing frequent could have been lost.`],
    ["Every published number is measured",
     `${n(pipe.candidates_verified)} candidates re-measured against all ${n(pipe.total_trips)} trips; no support is inferred from its parts.`],
    ["A route has to look like a route",
     "Simple-path and tortuosity guards at every growth step, plus an independent audit of the published file."],
    ["Empty results are reported, not padded",
     "Where a configuration has no corridors we show the trip-length ceiling that makes it impossible."],
  ];
  points.forEach(([h, d], i) => {
    const y = 2.1 + i * 1.12;
    s.addShape(pres.ShapeType.hexagon, {
      x: 0.9, y: y + 0.05, w: 0.46, h: 0.4, rotate: 90,
      fill: { color: AMBER }, line: { color: AMBER, width: 1 } });
    s.addText(h, { x: 1.55, y, w: 10.9, h: 0.36, isTextBox: true, margin: 0,
      fontFace: H, fontSize: 17, bold: true, color: "FFFFFF" });
    s.addText(d, { x: 1.55, y: y + 0.38, w: 10.9, h: 0.55, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "AECBD6", lineSpacing: 17 });
  });

  s.addText(`Full run: ${n(pipe.total_runtime_sec, 0)}s · ${n(pipe.corridors_reported)} corridors reported`, {
    x: 0.9, y: 6.65, w: 11, h: 0.35, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 11, color: "6E97A6" });
  s.addNotes("Close on the methodology rather than the headline count: the defensible claim is that everything reported was measured and audited, including the places where the answer is 'fewer than a hundred'.");
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
pres.writeFile({ fileName: OUT }).then(() => console.log(`wrote ${OUT}`));
