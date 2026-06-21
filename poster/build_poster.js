'use strict';

// ══════════════════════════════════════════════════════════════
//  AI TALENT MATCH — 3ft × 4ft Academic Poster (PptxGenJS)
//  Light / White Academic Theme  ·  Georgia + Calibri fonts
//  ULAB 2025
// ══════════════════════════════════════════════════════════════

(async () => {

const pptxgen = require("pptxgenjs");

// ── PALETTE ──────────────────────────────────────────────────
const C = {
  white:   "FFFFFF",
  pageBg:  "EFF4FB",   // very light blue-gray
  card:    "FFFFFF",
  navy:    "1B3A6B",   // deep navy — primary
  blue:    "2563EB",   // accent blue
  teal:    "0D9488",   // secondary accent
  sky:     "0EA5E9",
  text:    "1E293B",   // near-black body
  muted:   "64748B",
  subtle:  "94A3B8",
  border:  "D1D9E6",
  divider: "E2E8F0",
  green:   "059669",
  red:     "DC2626",
  amber:   "D97706",
  purple:  "7C3AED",
  formBg:  "F0F9FF",
  formBd:  "BAE6FD",
  formAcc: "0EA5E9",
  formTxt: "0C4A6E",
};

// ── FONTS ────────────────────────────────────────────────────
const F = {
  serif:  "Georgia",
  sans:   "Calibri",
  light:  "Calibri Light",
  mono:   "Courier New",
};

// ── PRESENTATION SETUP ───────────────────────────────────────
const pres = new pptxgen();
pres.defineLayout({ name: "POSTER_3x4", width: 36, height: 48 });
pres.layout  = "POSTER_3x4";
pres.author  = "Redwan Ahamad Samir · Samia Rahman · Bahadur Zaman Shezan";
pres.title   = "AI Talent Match — Academic Research Poster 2025 | ULAB";

const slide = pres.addSlide();
slide.background = { color: C.pageBg };

// ── LAYOUT GRID ──────────────────────────────────────────────
const LM     = 0.72;          // left/right margin
const GAP    = 0.55;          // column gap
const CW     = (36 - 2*LM - 2*GAP) / 3;   // ≈ 11.15"
const X      = [LM, LM+CW+GAP, LM+2*CW+2*GAP];
const HDR_H  = 5.5;           // header height
const STR_H  = 1.5;           // strip height
const BODY_Y = HDR_H + STR_H + 0.22;  // = 7.22
const FTR_Y  = 46.0;
const CP     = 0.38;          // card outer padding
const CX     = 0.44;          // card inner x padding
const CGAP   = 0.28;          // gap between cards in column

// ── HELPERS ──────────────────────────────────────────────────
const mkS  = () => ({ type:"outer", color:"000000", blur:10, offset:4, angle:135, opacity:0.07 });

function card(x, y, w, h, accentColor) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill:{color:C.card},
    line:{color:C.border, width:0.5}, shadow:mkS(),
  });
  if (accentColor) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w, h:0.13, fill:{color:accentColor},
      line:{color:accentColor, width:0},
    });
  }
}

function secTitle(x, y, w, label) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y:y+0.05, w:0.10, h:0.37,
    fill:{color:C.blue}, line:{color:C.blue, width:0},
  });
  slide.addText(label, {
    x:x+0.17, y, w:w-0.17, h:0.46,
    fontFace:F.sans, fontSize:20, bold:true,
    color:C.navy, margin:0, valign:"middle", charSpacing:0.5,
  });
}

function txt(x, y, w, h, content, opts={}) {
  slide.addText(content, {
    x, y, w, h,
    fontFace: opts.face  || F.sans,
    fontSize: opts.size  || 17,
    color:    opts.color || C.text,
    bold:     opts.bold  || false,
    italic:   opts.ital  || false,
    align:    opts.align || "justify",
    valign:   "top",
    wrap:     true,
    margin:   0,
    lineSpacingMultiple: opts.ls || 1.35,
  });
}

function formula(x, y, w, h, lines) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill:{color:C.formBg},
    line:{color:C.formBd, width:0.75},
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w:0.09, h,
    fill:{color:C.formAcc}, line:{color:C.formAcc, width:0},
  });
  slide.addText(lines, {
    x:x+0.18, y:y+0.12, w:w-0.28, h:h-0.2,
    fontFace:F.mono, fontSize:13.5, color:C.formTxt,
    align:"left", valign:"top", wrap:true, margin:0,
    lineSpacingMultiple:1.55,
  });
}

function hrule(x, y, w) {
  slide.addShape(pres.shapes.LINE, {
    x, y, w, h:0, line:{color:C.divider, width:0.75},
  });
}

function subHead(x, y, w, label, color) {
  slide.addText(label, {
    x, y, w, h:0.44,
    fontFace:F.sans, fontSize:15.5, bold:true, italic:true,
    color:color||C.blue, margin:0, valign:"middle",
  });
}

// ══════════════════════════════════════════════════════════════
//  HEADER
// ══════════════════════════════════════════════════════════════

// White header bg
slide.addShape(pres.shapes.RECTANGLE, {
  x:0, y:0, w:36, h:HDR_H,
  fill:{color:C.white}, line:{color:C.white, width:0},
});
// Navy top bar
slide.addShape(pres.shapes.RECTANGLE, {
  x:0, y:0, w:36, h:0.20,
  fill:{color:C.navy}, line:{color:C.navy, width:0},
});
// Blue bottom accent on header
slide.addShape(pres.shapes.RECTANGLE, {
  x:0, y:HDR_H-0.09, w:36, h:0.09,
  fill:{color:C.blue}, line:{color:C.blue, width:0},
});

// ULAB logo box
slide.addShape(pres.shapes.RECTANGLE, {
  x:LM, y:0.34, w:0.82, h:0.82,
  fill:{color:C.navy}, line:{color:C.navy, width:0},
});
slide.addText("ULAB", {
  x:LM, y:0.34, w:0.82, h:0.82,
  fontFace:F.sans, fontSize:15, bold:true,
  color:C.white, align:"center", valign:"middle", margin:0,
});
// Institution name
slide.addText("University of Liberal Arts Bangladesh", {
  x:LM+0.93, y:0.35, w:12, h:0.42,
  fontFace:F.sans, fontSize:19, bold:true,
  color:C.navy, margin:0, valign:"middle",
});
slide.addText("Department of Computer Science & Engineering  ·  Dhaka-1209, Bangladesh", {
  x:LM+0.93, y:0.78, w:14, h:0.32,
  fontFace:F.sans, fontSize:13, color:C.muted, margin:0, valign:"middle",
});

// Tech badges (top right)
const badges = [
  { label:"Django 4.x",               color:C.navy   },
  { label:"Gemini 2.5 Flash",          color:C.blue   },
  { label:"Reinforcement Learning",     color:C.teal   },
  { label:"Anti-Cheat AI",             color:C.purple },
  { label:"Multi-Agent System",         color:C.red    },
];
const BW = 2.48, BH = 0.40, BX0 = 36 - LM - badges.length*(BW+0.12) + 0.12;
badges.forEach((b, i) => {
  const bx = BX0 + i*(BW+0.12);
  slide.addShape(pres.shapes.RECTANGLE, {
    x:bx, y:0.37, w:BW, h:BH,
    fill:{color:b.color}, line:{color:b.color, width:0},
  });
  slide.addText(b.label, {
    x:bx, y:0.37, w:BW, h:BH,
    fontFace:F.sans, fontSize:12.5, bold:true,
    color:C.white, align:"center", valign:"middle", margin:0,
  });
});

// MAIN TITLE — Georgia serif, two lines
slide.addText("AI Talent Match: A Multi-Agent Intelligent Recruitment Platform", {
  x:1.5, y:1.08, w:33, h:1.08,
  fontFace:F.serif, fontSize:60, bold:true,
  color:C.navy, align:"center", valign:"middle", margin:0,
});
slide.addText("with Reinforcement Learning & AI-Proctored Interview Verification", {
  x:2.0, y:2.15, w:32, h:0.72,
  fontFace:F.serif, fontSize:38, bold:false, italic:true,
  color:C.blue, align:"center", valign:"middle", margin:0,
});

// Subtitle pills
const pills = [
  "🤖 Autonomous 7-Step Agent", "🔁 RL Adaptive Weight Optimization",
  "🛡️ Anti-Cheat AI Proctoring", "📊 Gemini 2.5 Flash Reasoning",
  "🔍 6-Dimensional Feature Matching",
];
const PW = 5.68;
const pillsTotal = pills.length * PW + (pills.length-1)*0.22;
const pilStartX = (36 - pillsTotal) / 2;
pills.forEach((p, i) => {
  const px = pilStartX + i*(PW+0.22);
  slide.addShape(pres.shapes.RECTANGLE, {
    x:px, y:2.98, w:PW, h:0.38,
    fill:{color:"EFF6FF"}, line:{color:"BFDBFE", width:0.75},
  });
  slide.addText(p, {
    x:px, y:2.98, w:PW, h:0.38,
    fontFace:F.sans, fontSize:13, bold:true,
    color:C.blue, align:"center", valign:"middle", margin:0,
  });
});

// Authors
const authors = [
  { name:"Redwan Ahamad Samir",   init:"RS", role:"Lead Developer", bg:C.blue   },
  { name:"Samia Rahman",           init:"SR", role:"System Design",  bg:C.purple },
  { name:"Bahadur Zaman Shezan",   init:"BZ", role:"AI Integration", bg:C.teal   },
];
const AW = 7.8, AX0 = (36 - authors.length*AW - (authors.length-1)*0.8) / 2;
authors.forEach((a, i) => {
  const ax = AX0 + i*(AW+0.8);
  slide.addShape(pres.shapes.OVAL, {
    x:ax, y:3.52, w:0.62, h:0.62,
    fill:{color:a.bg}, line:{color:a.bg, width:0},
  });
  slide.addText(a.init, {
    x:ax, y:3.52, w:0.62, h:0.62,
    fontFace:F.sans, fontSize:13.5, bold:true,
    color:C.white, align:"center", valign:"middle", margin:0,
  });
  slide.addText(a.name, {
    x:ax+0.72, y:3.53, w:AW-0.8, h:0.35,
    fontFace:F.sans, fontSize:16.5, bold:true,
    color:C.text, margin:0, valign:"middle",
  });
  slide.addText(a.role + "  ·  ULAB CSE", {
    x:ax+0.72, y:3.88, w:AW-0.8, h:0.26,
    fontFace:F.sans, fontSize:12, color:C.muted, margin:0, valign:"top",
  });
  if (i < authors.length-1) {
    slide.addShape(pres.shapes.LINE, {
      x:ax+AW+0.08, y:3.54, w:0, h:0.58,
      line:{color:C.divider, width:0.75},
    });
  }
});

// Affiliation line
hrule(3, 4.32, 30);
slide.addText("University of Liberal Arts Bangladesh (ULAB)  ·  Department of CSE  ·  Dhaka-1209, Bangladesh  ·  redwansamir90@gmail.com", {
  x:1.5, y:4.37, w:33, h:0.34,
  fontFace:F.sans, fontSize:13, color:C.muted,
  align:"center", valign:"middle", margin:0,
});

// ══════════════════════════════════════════════════════════════
//  METRICS STRIP
// ══════════════════════════════════════════════════════════════

const SY = HDR_H;
slide.addShape(pres.shapes.RECTANGLE, {
  x:0, y:SY, w:36, h:STR_H,
  fill:{color:C.navy}, line:{color:C.navy, width:0},
});

const metrics = [
  { val:"40",       lbl:"Match Pairs Scored" },
  { val:"15",       lbl:"Live Agent Runs" },
  { val:"17 ms",    lbl:"Per-Match Speed" },
  { val:"7",        lbl:"Pipeline Steps" },
  { val:"8",        lbl:"Fraud Rules" },
  { val:"5",        lbl:"Career Tracks" },
  { val:"~4 s",     lbl:"Full Pipeline Cycle" },
  { val:"3-Strike", lbl:"Anti-Cheat Policy" },
];
const MW = 36 / metrics.length;
metrics.forEach((m, i) => {
  const mx = i * MW;
  if (i > 0) {
    slide.addShape(pres.shapes.LINE, {
      x:mx, y:SY+0.2, w:0, h:STR_H-0.4,
      line:{color:"2D5BA3", width:0.5},
    });
  }
  slide.addShape(pres.shapes.RECTANGLE, {
    x:mx+MW/2-0.45, y:SY, w:0.9, h:0.07,
    fill:{color:"60A5FA"}, line:{color:"60A5FA", width:0},
  });
  slide.addText(m.val, {
    x:mx, y:SY+0.08, w:MW, h:0.82,
    fontFace:F.sans, fontSize:34, bold:true,
    color:"93C5FD", align:"center", valign:"middle", margin:0,
  });
  slide.addText(m.lbl, {
    x:mx+0.05, y:SY+0.92, w:MW-0.1, h:0.45,
    fontFace:F.sans, fontSize:12, color:"64748B",
    align:"center", valign:"top", margin:0,
  });
});

// ══════════════════════════════════════════════════════════════
//  LEFT COLUMN
// ══════════════════════════════════════════════════════════════

const cx0 = X[0];
const cw  = CW;
let cy = BODY_Y;

// ── Abstract (h=9.5) ──────────────────────────────────────────
const A_H = 9.5;
card(cx0, cy, cw, A_H, C.navy);
secTitle(cx0+CP, cy+0.28, cw-2*CP, "ABSTRACT");
txt(cx0+CX, cy+0.88, cw-2*CX, 8.28,
  "Conventional Applicant Tracking Systems (ATS) rely on static keyword-matching, systematically filtering out up to 75% of qualified candidates before human review (Gallup, 2023). AI Talent Match addresses this fundamental gap with a fully integrated multi-agent intelligent recruitment platform built on Django 4.x, powered by Google Gemini 2.5 Flash, and continuously optimized through Reinforcement Learning weight adaptation.\n\nThe platform computes multi-dimensional compatibility scores across six normalized feature axes — CGPA, skills, experience, projects, activity, and trust — executes a 7-step Autonomous Recruitment Agent per application with explainable natural-language reasoning, conducts AI-proctored interviews with per-answer live scoring, and continuously re-weights feature importance from real hiring signals. Zero external data labeling is required.\n\nEmpirical evaluation across 5 candidate profiles, 3 companies, and 8 active job postings demonstrates 17 ms per match score, sub-100 ms full job ranking, and reliable anti-cheat enforcement under fullscreen lock with 3-strike violation policy.",
  { size:17, ls:1.45 }
);
cy += A_H + CGAP;

// ── Introduction (h=8.0) ──────────────────────────────────────
const I_H = 8.0;
card(cx0, cy, cw, I_H, C.teal);
secTitle(cx0+CP, cy+0.28, cw-2*CP, "1. INTRODUCTION");
txt(cx0+CX, cy+0.88, cw-2*CX, 4.0,
  "The global talent mismatch costs employers $50 B+ annually in poor hiring decisions (SHRM, 2022). Keyword-based ATS systems ignore academic trajectory, portfolio depth, and trust signals. Existing AI recruitment tools either lack explainability or require large proprietary labeled datasets unavailable to most organizations.",
  { size:17, ls:1.42 }
);
// Stat boxes
const sbW = (cw - 2*CX - 0.18) / 2;
const sbY = cy + 5.1;
const statBoxes = [
  { val:"75%",  desc:"Candidates eliminated by ATS before human review", bg:"FEF2F2", bd:"FECACA", fc:C.red },
  { val:"6×",   desc:"Feature dimensions vs. 1D keyword-only ATS scoring", bg:"EFF6FF", bd:"BFDBFE", fc:C.blue },
];
statBoxes.forEach((sb, i) => {
  const sbx = cx0+CX + i*(sbW+0.18);
  slide.addShape(pres.shapes.RECTANGLE, {
    x:sbx, y:sbY, w:sbW, h:2.55,
    fill:{color:sb.bg}, line:{color:sb.bd, width:0.75}, shadow:mkS(),
  });
  slide.addText(sb.val, {
    x:sbx, y:sbY+0.1, w:sbW, h:1.0,
    fontFace:F.serif, fontSize:44, bold:true,
    color:sb.fc, align:"center", valign:"middle", margin:0,
  });
  slide.addText(sb.desc, {
    x:sbx+0.12, y:sbY+1.12, w:sbW-0.24, h:1.32,
    fontFace:F.sans, fontSize:13.5, color:sb.fc,
    align:"center", valign:"top", margin:0, lineSpacingMultiple:1.3,
  });
});
cy += I_H + CGAP;

// ── Materials & Stack (h=9.0) ─────────────────────────────────
const M_H = 9.0;
card(cx0, cy, cw, M_H, C.teal);
secTitle(cx0+CP, cy+0.28, cw-2*CP, "2. MATERIALS & TECHNOLOGY STACK");
const techs = [
  { e:"🐍", n:"Django 4.x",        r:"Backend MVC Framework"     },
  { e:"✨", n:"Gemini 2.5 Flash",   r:"LLM Reasoning & Scoring"   },
  { e:"🗄️", n:"PostgreSQL",         r:"Data Persistence Layer"    },
  { e:"🔁", n:"RL Weight Agent",    r:"Adaptive Weight Learning"   },
  { e:"🛡️", n:"Anti-Cheat Engine",  r:"JS Proctoring System"      },
  { e:"📊", n:"Chart.js / PPTX",   r:"Data Visualization Layer"  },
];
const TW = (cw - 2*CX - 0.18) / 3;
techs.forEach((t, i) => {
  const col = i%3, row = Math.floor(i/3);
  const tx = cx0+CX + col*(TW+0.09);
  const ty = cy+0.95 + row*2.18;
  slide.addShape(pres.shapes.RECTANGLE, {
    x:tx, y:ty, w:TW, h:2.02,
    fill:{color:"F8FAFC"}, line:{color:C.border, width:0.75}, shadow:mkS(),
  });
  slide.addText(t.e, {
    x:tx, y:ty+0.1, w:TW, h:0.65,
    fontSize:20, align:"center", valign:"middle", margin:0,
  });
  slide.addText(t.n, {
    x:tx+0.07, y:ty+0.76, w:TW-0.14, h:0.48,
    fontFace:F.sans, fontSize:13, bold:true,
    color:C.navy, align:"center", margin:0, lineSpacingMultiple:1.1,
  });
  slide.addText(t.r, {
    x:tx+0.06, y:ty+1.26, w:TW-0.12, h:0.68,
    fontFace:F.sans, fontSize:11, color:C.muted,
    align:"center", margin:0, lineSpacingMultiple:1.2,
  });
});
txt(cx0+CX, cy+5.45, cw-2*CX, 3.22,
  "Dataset: 5 synthetic student profiles (CSE, BBA, EEE, Data Science, CS-junior) across 3 companies — TechCorp, DataMinds, GreenTech — and 8 active job postings. Zero external labeling required: all RL feedback signals derive from in-platform hire/reject decisions stored in AIFeedbackLog.",
  { size:16, ls:1.38 }
);
cy += M_H + CGAP;

// ── Trust Score + Chart (h=11.2) ──────────────────────────────
const T_H = 11.2;
card(cx0, cy, cw, T_H, C.navy);
secTitle(cx0+CP, cy+0.28, cw-2*CP, "TRUST SCORE DISTRIBUTION");
txt(cx0+CX, cy+0.88, cw-2*CX, 1.9,
  "Trust T ∈ [0, 100] computed by 8-rule Fraud Detection Engine. Penalties pₖ ∈ {5, 10, 20} applied per severity. Threshold: T ≥ 70 = Low Risk  ·  T 50–69 = Medium  ·  T < 50 = High Risk",
  { size:16.5, ls:1.35 }
);
slide.addChart(pres.charts.BAR, [{
  name:"Trust Score",
  labels:["Karim","Rahim","Tasnim","Mehedi","Nadia"],
  values:[94, 84, 71, 68, 42],
}], {
  x:cx0+CX, y:cy+2.95, w:cw-2*CX, h:6.0,
  barDir:"bar",
  chartColors:["059669","059669","D97706","D97706","DC2626"],
  showValue:true,
  dataLabelFontFace:F.sans, dataLabelFontSize:15, dataLabelColor:"FFFFFF", dataLabelFontBold:true,
  catAxisLabelFontFace:F.sans, catAxisLabelFontSize:15, catAxisLabelColor:C.text, catAxisLabelFontBold:true,
  valAxisLabelFontFace:F.sans, valAxisLabelFontSize:12, valAxisLabelColor:C.muted,
  valAxisMaxVal:100,
  chartArea:{ fill:{color:C.white}, border:{color:C.border, pt:0.5} },
  plotArea:{ fill:{color:C.white} },
  valGridLine:{ color:"E2E8F0", size:0.5 },
  catGridLine:{ style:"none" },
  showLegend:false,
});
const tpills = [
  { l:"Low Risk  ≥ 70", c:C.green,  bg:"F0FDF4", bd:"BBF7D0" },
  { l:"Medium  50–69",  c:C.amber,  bg:"FFFBEB", bd:"FDE68A" },
  { l:"High Risk  < 50",c:C.red,    bg:"FEF2F2", bd:"FECACA" },
];
const tpW = (cw-2*CX-0.24)/3;
tpills.forEach((tp, i) => {
  const tpx = cx0+CX + i*(tpW+0.12);
  const tpy = cy + T_H - 0.72;
  slide.addShape(pres.shapes.RECTANGLE, {
    x:tpx, y:tpy, w:tpW, h:0.54,
    fill:{color:tp.bg}, line:{color:tp.bd, width:0.75},
  });
  slide.addText(tp.l, {
    x:tpx, y:tpy, w:tpW, h:0.54,
    fontFace:F.sans, fontSize:12.5, bold:true,
    color:tp.c, align:"center", valign:"middle", margin:0,
  });
});
cy += T_H + CGAP;

// ══════════════════════════════════════════════════════════════
//  CENTER COLUMN
// ══════════════════════════════════════════════════════════════

const cx1 = X[1];
let cy1 = BODY_Y;

// ── Methodology Part 1 — Feature Vector (h=11.5) ─────────────
const MH1 = 11.5;
card(cx1, cy1, cw, MH1, C.blue);
secTitle(cx1+CP, cy1+0.28, cw-2*CP, "3. METHODOLOGY");
subHead(cx1+CX, cy1+0.9, cw-2*CX, "3.1  Feature Vector & Weighted Match Score");
txt(cx1+CX, cy1+1.42, cw-2*CX, 1.4,
  "Each student–job pair is encoded as a 6-dimensional normalized vector φ = [f₁…f₆], fᵢ ∈ [0, 1]:",
  { size:16.5, ls:1.35 }
);
formula(cx1+CX, cy1+2.98, cw-2*CX, 4.45,
  "f₁ = cgpa / 4.0             // CGPA normalised to [0,1]\n" +
  "f₂ = |skills ∩ job_req| / |job_req|  // Skill coverage ratio\n" +
  "f₃ = min(years_exp, 5) / 5  // Work experience (cap 5 yrs)\n" +
  "f₄ = min(n_projects, 5) / 5 // Portfolio depth (cap 5)\n" +
  "f₅ = applications / 10      // Platform activity signal\n" +
  "f₆ = trust_score / 100      // Fraud / trust index"
);
formula(cx1+CX, cy1+7.6, cw-2*CX, 1.62,
  "S(s, j) = 100 × Σᵢ₌₁⁶ wᵢ · fᵢ        where  Σwᵢ = 1"
);
txt(cx1+CX, cy1+9.32, cw-2*CX, 0.72,
  "Initial uniform weights:  w = [0.20, 0.20, 0.20, 0.15, 0.10, 0.15]",
  { size:14.5, ital:true, color:C.muted }
);
hrule(cx1+CX, cy1+10.18, cw-2*CX);
subHead(cx1+CX, cy1+10.35, cw-2*CX, "3.2  Reinforcement Learning Weight Adaptation");
txt(cx1+CX, cy1+10.88, cw-2*CX, 0.52,
  "After each hire / reject signal, feature weights update via policy gradient:",
  { size:15.5, ls:1.3 }
);
cy1 += MH1 + CGAP;

// ── Methodology Part 2 — RL + Trust + Anticheat (h=10.5) ─────
const MH2 = 10.5;
card(cx1, cy1, cw, MH2, C.blue);
formula(cx1+CX, cy1+0.3, cw-2*CX, 4.0,
  "wᵢᵗ⁺¹ = wᵢᵗ + α · δ · (fᵢ − 0.5)\n\n" +
  "  α = 0.05        // Learning rate (step size)\n" +
  "  δ = +1          // Hire signal  → reinforce feature\n" +
  "  δ = −1          // Reject signal → penalise feature\n" +
  "  (fᵢ − 0.5)      // Neutral threshold: 0.5"
);
formula(cx1+CX, cy1+4.45, cw-2*CX, 2.12,
  "wᵢ ← max(wᵢ, 0.02)      // Floor clamp — no weight fully dies\n" +
  "wᵢ ← wᵢ / Σwⱼ           // Re-normalise so that Σwᵢ = 1"
);
hrule(cx1+CX, cy1+6.72, cw-2*CX);
subHead(cx1+CX, cy1+6.88, cw-2*CX, "3.3  Trust Score & Fraud Detection (8 Rules)");
formula(cx1+CX, cy1+7.42, cw-2*CX, 1.62,
  "T = 100 − Σₖ pₖ · sₖ      pₖ ∈ {5, 10, 20}    sₖ = severity"
);
hrule(cx1+CX, cy1+9.18, cw-2*CX);
subHead(cx1+CX, cy1+9.34, cw-2*CX, "3.4  AI Interview Anti-Cheat Protocol");
formula(cx1+CX, cy1+9.88, cw-2*CX, 0.52,
  "V = tab_switches + fullscreen_exits + copy_pastes    →    if V ≥ 3: auto_submit(CHEATING)"
);
cy1 += MH2 + CGAP;

// ── 7-Step Pipeline (h=15.8) ──────────────────────────────────
const PH = FTR_Y - CGAP - cy1;   // fill remainder
card(cx1, cy1, cw, PH, C.purple);
secTitle(cx1+CP, cy1+0.28, cw-2*CP, "4. 7-STEP RECRUITMENT AGENT PIPELINE");
txt(cx1+CX, cy1+0.88, cw-2*CX, 0.85,
  "Each application triggers a fully autonomous 7-step agent. All decisions are explainable via Gemini-generated reasoning steps persisted to RecruitmentAgentRun.",
  { size:16.5, ls:1.35 }
);
const steps = [
  { n:1, name:"Profile Ingestion",    desc:"Load student → compute φ = [f₁…f₆] from PostgreSQL",                         time:"~2 ms",  bar:C.green  },
  { n:2, name:"AI Match Scoring",     desc:"S(s,j) = 100 × Σ wᵢ·fᵢ  with company-specific learned weights",              time:"~17 ms", bar:C.green  },
  { n:3, name:"Eligibility Gate",     desc:"CGPA ≥ minimum  ·  Trust ≥ 40  ·  Employment type validation",                time:"~1 ms",  bar:C.teal   },
  { n:4, name:"Skill Gap Analysis",   desc:"Gap = job_requirements ∖ student_skills  (case-normalised set difference)",    time:"~3 ms",  bar:C.teal   },
  { n:5, name:"Fraud & Trust Check",  desc:"FraudDetectionEngine: 8 rules → penalty-weighted T score computed",            time:"~5 ms",  bar:C.amber  },
  { n:6, name:"Gemini Fit Report",    desc:"LLM generates natural-language fit narrative + step-by-step reasoning log",    time:"~35 ms", bar:C.amber  },
  { n:7, name:"Decision & Persist",   desc:"Shortlist / Review / Reject → RecruitmentAgentRun saved to database",          time:"~7 ms",  bar:C.red    },
];
const stepH = (PH - 2.05 - 0.65) / steps.length;
steps.forEach((s, i) => {
  const sy = cy1 + 1.88 + i*stepH;
  const sh = stepH - 0.1;
  slide.addShape(pres.shapes.RECTANGLE, {
    x:cx1+CX, y:sy, w:cw-2*CX, h:sh,
    fill:{color:"F8FAFC"}, line:{color:C.border, width:0.75}, shadow:mkS(),
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x:cx1+CX, y:sy, w:0.08, h:sh,
    fill:{color:s.bar}, line:{color:s.bar, width:0},
  });
  slide.addShape(pres.shapes.OVAL, {
    x:cx1+CX+0.15, y:sy+(sh-0.50)/2, w:0.50, h:0.50,
    fill:{color:s.bar}, line:{color:s.bar, width:0},
  });
  slide.addText(String(s.n), {
    x:cx1+CX+0.15, y:sy+(sh-0.50)/2, w:0.50, h:0.50,
    fontFace:F.sans, fontSize:16, bold:true,
    color:C.white, align:"center", valign:"middle", margin:0,
  });
  const textW = cw - 2*CX - 1.85;
  slide.addText(s.name, {
    x:cx1+CX+0.76, y:sy+0.10, w:textW, h:0.40,
    fontFace:F.sans, fontSize:15, bold:true,
    color:C.navy, margin:0, valign:"middle",
  });
  slide.addText(s.desc, {
    x:cx1+CX+0.76, y:sy+0.50, w:textW, h:sh-0.58,
    fontFace:F.mono, fontSize:11.5, color:C.muted,
    align:"left", valign:"top", wrap:true, margin:0, lineSpacingMultiple:1.2,
  });
  // time badge
  slide.addShape(pres.shapes.RECTANGLE, {
    x:cx1+cw-CX-1.15, y:sy+(sh-0.38)/2, w:1.08, h:0.38,
    fill:{color:"EFF6FF"}, line:{color:"BFDBFE", width:0.75},
  });
  slide.addText(s.time, {
    x:cx1+cw-CX-1.15, y:sy+(sh-0.38)/2, w:1.08, h:0.38,
    fontFace:F.sans, fontSize:13, bold:true,
    color:C.blue, align:"center", valign:"middle", margin:0,
  });
});
slide.addText("Total wall-time (excl. LLM):  ~70 ms   ·   Full pipeline with Gemini:  ~4 seconds", {
  x:cx1+CX, y:cy1+PH-0.58, w:cw-2*CX, h:0.45,
  fontFace:F.sans, fontSize:13.5, bold:true,
  color:C.navy, align:"center", valign:"middle", margin:0,
});
cy1 += PH + CGAP;

// ══════════════════════════════════════════════════════════════
//  RIGHT COLUMN
// ══════════════════════════════════════════════════════════════

const cx2 = X[2];
let cy2 = BODY_Y;

// ── Agent Decisions  (h=8.0) ──────────────────────────────────
const RH1 = 8.0;
card(cx2, cy2, cw, RH1, C.navy);
secTitle(cx2+CP, cy2+0.28, cw-2*CP, "5. RESULTS — AGENT DECISIONS (15 Runs)");
txt(cx2+CX, cy2+0.88, cw-2*CX, 1.05,
  "15 live runs across 5 students × 3 companies. All decisions include Gemini fit reports & reasoning steps.",
  { size:16.5, ls:1.3 }
);
slide.addChart(pres.charts.DOUGHNUT, [{
  name:"Decisions",
  labels:["Rejected","Under Review","Shortlisted"],
  values:[9, 5, 1],
}], {
  x:cx2+CX, y:cy2+2.1, w:cw-2*CX, h:5.3,
  chartColors:["DC2626","D97706","059669"],
  showPercent:true,
  dataLabelFontFace:F.sans, dataLabelFontSize:14, dataLabelFontBold:true, dataLabelColor:"FFFFFF",
  showLegend:true, legendPos:"b",
  legendFontFace:F.sans, legendFontSize:14, legendColor:C.text,
  chartArea:{ fill:{color:C.white}, border:{color:C.border, pt:0.5} },
  holeSize:52,
});
cy2 += RH1 + CGAP;

// ── Match Heatmap Table  (h=7.0) ──────────────────────────────
const RH2 = 7.0;
card(cx2, cy2, cw, RH2, C.blue);
secTitle(cx2+CP, cy2+0.28, cw-2*CP, "5.2  MATCH SCORE MATRIX  (5 × 8)");
const jLabels = ["Django","ML Eng.","Data Anlst","Frontend","Full Stack","Embedded","Marketing","Biz Anlst"];
const sLabels = ["Karim","Rahim","Tasnim","Mehedi","Nadia"];
const sMat    = [
  [49,70,68,38,52,43,67,70],
  [63,58,47,55,68,41,62,65],
  [30,30,38,30,30,36,72,65],
  [34,34,34,29,33,63,48,48],
  [14,19,19,39,22, 7,15,18],
];
function hc(v) {
  if (v>=65) return { fill:"D1FAE5", text:"065F46", bold:true  };
  if (v>=50) return { fill:"DBEAFE", text:"1E40AF", bold:true  };
  if (v>=35) return { fill:"FEF3C7", text:"92400E", bold:false };
  return            { fill:"FEE2E2", text:"991B1B", bold:false };
}
const hmRows = [];
// Header
hmRows.push([
  { text:"", options:{ fill:{color:C.navy}, color:C.white, fontFace:F.sans, fontSize:8.5, bold:true, align:"center" } },
  ...jLabels.map(j => ({ text:j, options:{ fill:{color:C.navy}, color:C.white, fontFace:F.sans, fontSize:8.5, bold:true, align:"center" } }))
]);
// Data
sMat.forEach((row, ri) => {
  hmRows.push([
    { text:sLabels[ri], options:{ fill:{color:"F1F5F9"}, color:C.navy, fontFace:F.sans, fontSize:11, bold:true, align:"left" } },
    ...row.map(v => {
      const cl = hc(v);
      return { text:String(v), options:{ fill:{color:cl.fill}, color:cl.text, fontFace:F.sans, fontSize:11, bold:cl.bold, align:"center" } };
    })
  ]);
});
slide.addTable(hmRows, {
  x:cx2+CX, y:cy2+0.92, w:cw-2*CX, h:4.88,
  border:{ pt:0.5, color:"E2E8F0" }, rowH:0.72,
});
const lgItems = [
  { t:"≥65 Excellent", f:"D1FAE5", c:"065F46" },
  { t:"50–64 Good",    f:"DBEAFE", c:"1E40AF" },
  { t:"35–49 Fair",    f:"FEF3C7", c:"92400E" },
  { t:"<35 Weak",      f:"FEE2E2", c:"991B1B" },
];
const lgW = (cw-2*CX-0.3)/4;
lgItems.forEach((lg, i) => {
  const lgx = cx2+CX + i*(lgW+0.10);
  const lgy = cy2 + RH2 - 0.60;
  slide.addShape(pres.shapes.RECTANGLE, {
    x:lgx, y:lgy, w:lgW, h:0.42,
    fill:{color:lg.f}, line:{color:"E2E8F0", width:0.5},
  });
  slide.addText(lg.t, {
    x:lgx, y:lgy, w:lgW, h:0.42,
    fontFace:F.sans, fontSize:10, bold:true,
    color:lg.c, align:"center", valign:"middle", margin:0,
  });
});
cy2 += RH2 + CGAP;

// ── RL Weights  (h=8.0) ───────────────────────────────────────
const RH3 = 8.0;
card(cx2, cy2, cw, RH3, C.teal);
secTitle(cx2+CP, cy2+0.28, cw-2*CP, "5.3  RL WEIGHT ADAPTATION");
txt(cx2+CX, cy2+0.88, cw-2*CX, 1.05,
  "DataMinds Co. weights after ML Engineer hire / reject signals. CGPA, Trust, and Activity all increased post-hire.",
  { size:16.5, ls:1.3 }
);
slide.addChart(pres.charts.BAR, [
  { name:"Before RL",      labels:["CGPA","Skills","Exp.","Projects","Activity","Trust"], values:[20,20,20,15,10,15] },
  { name:"After Hire ▲",   labels:["CGPA","Skills","Exp.","Projects","Activity","Trust"], values:[26,17,21,16,13,18] },
  { name:"After Reject ▼", labels:["CGPA","Skills","Exp.","Projects","Activity","Trust"], values:[18,23,19,14, 9,13] },
], {
  x:cx2+CX, y:cy2+2.1, w:cw-2*CX, h:4.55,
  barDir:"col",
  chartColors:["94A3B8","059669","DC2626"],
  showValue:true,
  dataLabelFontFace:F.sans, dataLabelFontSize:10, dataLabelColor:C.text,
  catAxisLabelFontFace:F.sans, catAxisLabelFontSize:12.5, catAxisLabelColor:C.text, catAxisLabelFontBold:true,
  valAxisLabelFontFace:F.sans, valAxisLabelFontSize:10, valAxisLabelColor:C.muted,
  valAxisMaxVal:32,
  chartArea:{ fill:{color:C.white}, border:{color:C.border, pt:0.5} },
  plotArea:{ fill:{color:C.white} },
  valGridLine:{ color:"E2E8F0", size:0.5 }, catGridLine:{ style:"none" },
  showLegend:true, legendPos:"b",
  legendFontFace:F.sans, legendFontSize:12, legendColor:C.text,
});
slide.addText("▲ CGPA +6%  ·  ▲ Trust +3%  ·  ▲ Activity +3%  after hire reinforcement", {
  x:cx2+CX, y:cy2+6.82, w:cw-2*CX, h:0.40,
  fontFace:F.sans, fontSize:13, bold:true,
  color:C.green, align:"center", valign:"middle", margin:0,
});
slide.addText("▼ Skills −3%  (fᵢ < 0.5 neutral threshold for Intermediate proficiency — technically correct RL behaviour)", {
  x:cx2+CX, y:cy2+7.26, w:cw-2*CX, h:0.55,
  fontFace:F.sans, fontSize:11.5, italic:true,
  color:C.muted, align:"center", valign:"top", wrap:true, margin:0, lineSpacingMultiple:1.25,
});
cy2 += RH3 + CGAP;

// ── Skill Gap + Interview  (h=7.0) ────────────────────────────
const RH4 = 7.0;
card(cx2, cy2, cw, RH4, C.purple);
secTitle(cx2+CP, cy2+0.28, cw-2*CP, "5.4  SKILL GAP  &  INTERVIEW SCORES");
slide.addChart(pres.charts.BAR, [
  { name:"Market Demand", labels:["Python","SQL","Docker","Excel","REST API","Git"], values:[2,2,2,2,2,2] },
  { name:"Student Supply",labels:["Python","SQL","Docker","Excel","REST API","Git"], values:[1,1,1,0,1,1] },
], {
  x:cx2+CX, y:cy2+0.85, w:cw-2*CX, h:3.8,
  barDir:"col",
  chartColors:["DC2626","2563EB"],
  showValue:true,
  dataLabelFontFace:F.sans, dataLabelFontSize:12, dataLabelColor:C.text,
  catAxisLabelFontFace:F.sans, catAxisLabelFontSize:13, catAxisLabelColor:C.text, catAxisLabelFontBold:true,
  valAxisLabelFontFace:F.sans, valAxisLabelFontSize:11, valAxisLabelColor:C.muted,
  valAxisMaxVal:3,
  chartArea:{ fill:{color:C.white}, border:{color:C.border, pt:0.5} },
  plotArea:{ fill:{color:C.white} },
  valGridLine:{ color:"E2E8F0", size:0.5 }, catGridLine:{ style:"none" },
  showLegend:true, legendPos:"b",
  legendFontFace:F.sans, legendFontSize:12, legendColor:C.text,
});
// Interview score tiles
const ivTiles = [
  { s:"7/10", l:"Strong Answer", c:C.green,  bg:"F0FDF4", bd:"BBF7D0" },
  { s:"7/10", l:"Average Answer",c:C.amber,  bg:"FFFBEB", bd:"FDE68A" },
  { s:"2/10", l:"Weak Answer",   c:C.red,    bg:"FEF2F2", bd:"FECACA" },
];
const ivW = (cw-2*CX-0.32)/3;
ivTiles.forEach((iv, i) => {
  const ivx = cx2+CX + i*(ivW+0.16);
  const ivy = cy2 + 4.88;
  slide.addShape(pres.shapes.RECTANGLE, {
    x:ivx, y:ivy, w:ivW, h:1.85,
    fill:{color:iv.bg}, line:{color:iv.bd, width:1}, shadow:mkS(),
  });
  slide.addText(iv.s, {
    x:ivx, y:ivy+0.1, w:ivW, h:0.90,
    fontFace:F.serif, fontSize:30, bold:true,
    color:iv.c, align:"center", valign:"middle", margin:0,
  });
  slide.addText(iv.l, {
    x:ivx+0.08, y:ivy+1.05, w:ivW-0.16, h:0.68,
    fontFace:F.sans, fontSize:13, bold:true,
    color:iv.c, align:"center", valign:"middle", margin:0, lineSpacingMultiple:1.15,
  });
});
cy2 += RH4 + CGAP;

// ── Conclusions + Limitations  (fill remainder) ───────────────
const RH5 = FTR_Y - CGAP - cy2;
card(cx2, cy2, cw, RH5, C.green);
secTitle(cx2+CP, cy2+0.28, cw-2*CP, "6. CONCLUSIONS");
const concls = [
  { e:"🚀", t:"17 ms/match confirms real-time viability for high-volume screening — no batching delays needed." },
  { e:"🔁", t:"RL adaptation demonstrably shifts CGPA (+6%), Trust (+3%), Activity (+3%) after hire reinforcement." },
  { e:"🤖", t:"7-step agent produces fully explainable, auditable decisions with Gemini reasoning — no black-box." },
  { e:"🛡️", t:"3-strike anti-cheat reliably differentiates strong (7/10) from weak (2/10) under proctored sessions." },
];
const clLineH = (RH5 * 0.44) / concls.length;
concls.forEach((c, i) => {
  const cly = cy2 + 0.88 + i*clLineH;
  slide.addText(c.e, {
    x:cx2+CX, y:cly, w:0.52, h:clLineH-0.08,
    fontSize:18, align:"center", valign:"middle", margin:0,
  });
  txt(cx2+CX+0.58, cly, cw-2*CX-0.58, clLineH-0.05, c.t, { size:15.5, ls:1.3, align:"left" });
});

hrule(cx2+CX, cy2+RH5*0.49, cw-2*CX);
secTitle(cx2+CP, cy2+RH5*0.49+0.08, cw-2*CP, "7. LIMITATIONS & FUTURE WORK");
const lims = [
  { t:"Small dataset:", d:"5 candidates / 8 jobs. RL convergence needs 1,000+ applicants for production validation." },
  { t:"LLM latency:",   d:"Gemini calls 1.4–2.1 s with ±1 point scoring variance on equivalent answers." },
  { t:"Anti-cheat:",    d:"VM-based or secondary-device cheating undetectable by browser JavaScript alone." },
  { t:"Future work:",   d:"PDF CV parsing via LLM · Video sentiment scoring · Federated RL across companies." },
];
const limLineH = (RH5 - RH5*0.49 - 0.62) / lims.length;
lims.forEach((l, i) => {
  const ly = cy2 + RH5*0.49 + 0.62 + i*limLineH;
  slide.addShape(pres.shapes.OVAL, {
    x:cx2+CX, y:ly+limLineH*0.3, w:0.18, h:0.18,
    fill:{ color: i===3 ? C.blue : C.amber },
    line:{ color: i===3 ? C.blue : C.amber, width:0 },
  });
  slide.addText([
    { text:l.t+" ", options:{ bold:true, color: i===3 ? C.blue : "92400E" } },
    { text:l.d,     options:{ color:C.text } },
  ], {
    x:cx2+CX+0.30, y:ly, w:cw-2*CX-0.32, h:limLineH,
    fontFace:F.sans, fontSize:15, align:"left",
    valign:"top", wrap:true, margin:0, lineSpacingMultiple:1.3,
  });
});
cy2 += RH5 + CGAP;

// ══════════════════════════════════════════════════════════════
//  FOOTER
// ══════════════════════════════════════════════════════════════

slide.addShape(pres.shapes.RECTANGLE, {
  x:0, y:FTR_Y, w:36, h:48-FTR_Y,
  fill:{color:C.navy}, line:{color:C.navy, width:0},
});
slide.addShape(pres.shapes.RECTANGLE, {
  x:0, y:FTR_Y, w:36, h:0.09,
  fill:{color:C.blue}, line:{color:C.blue, width:0},
});
// Left
slide.addText([
  { text:"University of Liberal Arts Bangladesh (ULAB)\n", options:{ bold:true, fontSize:15.5, color:"93C5FD" } },
  { text:"Department of Computer Science & Engineering  ·  Dhaka-1209, Bangladesh", options:{ fontSize:12.5, color:"64748B" } },
], {
  x:LM, y:FTR_Y+0.3, w:11, h:1.5,
  fontFace:F.sans, color:C.white,
  align:"left", valign:"top", wrap:true, margin:0, lineSpacingMultiple:1.45,
});
// Center
slide.addText("AI TALENT MATCH  ·  RESEARCH POSTER  ·  ULAB 2025", {
  x:11, y:FTR_Y+0.36, w:14, h:0.55,
  fontFace:F.sans, fontSize:16, bold:true, charSpacing:0.8,
  color:"60A5FA", align:"center", valign:"middle", margin:0,
});
slide.addText("Django  ·  Gemini 2.5 Flash  ·  PostgreSQL  ·  Reinforcement Learning  ·  Chart.js", {
  x:11, y:FTR_Y+0.98, w:14, h:0.38,
  fontFace:F.sans, fontSize:12, color:"475569",
  align:"center", valign:"middle", margin:0,
});
// Right
slide.addText([
  { text:"redwansamir90@gmail.com\n",                                                           options:{ bold:true, fontSize:14.5, color:"93C5FD" } },
  { text:"© 2025  Redwan Ahamad Samir  ·  Samia Rahman  ·  Bahadur Zaman Shezan\n",            options:{ fontSize:12, color:"64748B" } },
  { text:"All rights reserved — ULAB Department of Computer Science & Engineering",             options:{ fontSize:10.5, color:"374151" } },
], {
  x:25, y:FTR_Y+0.26, w:10.28, h:1.6,
  fontFace:F.sans, color:C.white,
  align:"right", valign:"top", wrap:true, margin:0, lineSpacingMultiple:1.45,
});

// ══════════════════════════════════════════════════════════════
//  SAVE
// ══════════════════════════════════════════════════════════════

const outPath = "/sessions/kind-keen-einstein/mnt/Ai_telent_match/poster/AI_Talent_Match_Poster_3x4ft.pptx";
await pres.writeFile({ fileName: outPath });
console.log("✅  Poster saved →", outPath);

})().catch(err => { console.error("❌ Error:", err.message); process.exit(1); });
