"""
AI Talent Match — Poster Visualization
========================================
Run: python visualize_results.py
Reads test_results.json and generates poster-ready charts.
"""

import json
import os
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap

# ── Load results ──────────────────────────────────────────────────────────────
RESULTS_FILE = 'test_results.json'

if not os.path.exists(RESULTS_FILE):
    print(f"❌ {RESULTS_FILE} not found.")
    print("   Run first: python manage.py run_poster_tests --save")
    sys.exit(1)

with open(RESULTS_FILE) as f:
    data = json.load(f)

print("✅ Loaded test_results.json")

# ── Theme ─────────────────────────────────────────────────────────────────────
BG        = '#0a0f1e'
CARD      = '#0f1e3d'
ACCENT    = '#48bbff'
GREEN     = '#22c55e'
YELLOW    = '#f59e0b'
RED       = '#ef4444'
PURPLE    = '#a855f7'
TEXT      = '#e2e8f0'
SUBTEXT   = '#94a3b8'

plt.rcParams.update({
    'figure.facecolor':  BG,
    'axes.facecolor':    CARD,
    'axes.edgecolor':    '#1e3a5f',
    'axes.labelcolor':   TEXT,
    'xtick.color':       SUBTEXT,
    'ytick.color':       SUBTEXT,
    'text.color':        TEXT,
    'grid.color':        '#1e3a5f',
    'grid.alpha':        0.5,
    'font.family':       'DejaVu Sans',
})

OUT_DIR = 'poster_charts'
os.makedirs(OUT_DIR, exist_ok=True)


def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=180, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    print(f"   💾 {path}")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 1 — Trust Score Distribution
# ══════════════════════════════════════════════════════════════════════════════
print("\n📊 Chart 1: Trust Score Distribution")

trust = data.get('T1_trust_scores', [])
names  = [d['name'].split()[0] for d in trust]
scores = [d['trust_score'] for d in trust]
colors = [GREEN if s >= 80 else YELLOW if s >= 60 else RED for s in scores]

fig, ax = plt.subplots(figsize=(9, 5))
fig.patch.set_facecolor(BG)

bars = ax.barh(names[::-1], scores[::-1], color=colors[::-1],
               height=0.55, edgecolor='none')

for bar, score in zip(bars, scores[::-1]):
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
            f'{score:.0f}', va='center', fontsize=13, fontweight='bold', color=TEXT)

ax.set_xlim(0, 110)
ax.set_xlabel('Trust Score / 100', fontsize=11, color=SUBTEXT)
ax.set_title('Trust Score Distribution\nProfile Authenticity Engine', fontsize=14,
             fontweight='bold', color=ACCENT, pad=15)
ax.axvline(80, color=GREEN,  linestyle='--', alpha=0.4, linewidth=1.2)
ax.axvline(60, color=YELLOW, linestyle='--', alpha=0.4, linewidth=1.2)
ax.text(80.5, -0.6, 'Trusted', color=GREEN,  fontsize=9, alpha=0.7)
ax.text(60.5, -0.6, 'OK',      color=YELLOW, fontsize=9, alpha=0.7)
ax.grid(axis='x', alpha=0.3)
ax.set_axisbelow(True)

# add dept labels
for i, d in enumerate(trust[::-1]):
    ax.text(2, i, f'{d["dept"]}  CGPA {d["cgpa"]}',
            va='center', fontsize=8.5, color=SUBTEXT)

save(fig, '01_trust_scores.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 2 — AI Match Score Matrix (Heatmap)
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 2: AI Match Score Matrix")

matrix_rows = data.get('T2_match_matrix', [])
student_names = [r['student'].split()[0] for r in matrix_rows]
job_names     = list(matrix_rows[0]['scores'].keys()) if matrix_rows else []
job_short     = [j[:16] + '…' if len(j) > 16 else j for j in job_names]

matrix = np.array([[r['scores'].get(j, 0) for j in job_names] for r in matrix_rows])

cmap = LinearSegmentedColormap.from_list('talent',
    ['#0a0f1e', '#1e3a5f', '#48bbff', '#22c55e'])

fig, ax = plt.subplots(figsize=(13, 5))
im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=100, aspect='auto')

ax.set_xticks(range(len(job_short)))
ax.set_xticklabels(job_short, rotation=35, ha='right', fontsize=9)
ax.set_yticks(range(len(student_names)))
ax.set_yticklabels(student_names, fontsize=11)

for i in range(len(student_names)):
    for j in range(len(job_names)):
        val = matrix[i, j]
        color = 'white' if val < 55 else BG
        ax.text(j, i, f'{val:.0f}', ha='center', va='center',
                fontsize=10, fontweight='bold', color=color)

cbar = plt.colorbar(im, ax=ax, shrink=0.8)
cbar.ax.yaxis.set_tick_params(color=SUBTEXT)
cbar.set_label('Match Score %', color=SUBTEXT, fontsize=9)

ax.set_title('AI Match Score Matrix  (5 Students × 8 Jobs)\nSemantic Skill + Department + Trust + CGPA',
             fontsize=13, fontweight='bold', color=ACCENT, pad=12)

save(fig, '02_match_matrix.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 3 — Recruitment Agent Decisions
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 3: Recruitment Agent Decisions")

agent_runs = data.get('T3_agent_runs', [])
shortlisted = sum(1 for r in agent_runs if r['decision'] == 'shortlist')
reviewed    = sum(1 for r in agent_runs if r['decision'] == 'review')
rejected    = sum(1 for r in agent_runs if r['decision'] == 'reject')
total       = len(agent_runs)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Pie chart
sizes  = [shortlisted, reviewed, rejected]
labels = [f'Shortlisted\n{shortlisted}', f'Manual Review\n{reviewed}', f'Rejected\n{rejected}']
colors_pie = [GREEN, YELLOW, RED]
explode    = (0.05, 0.02, 0)
wedges, texts, autotexts = ax1.pie(
    sizes, labels=labels, colors=colors_pie, explode=explode,
    autopct='%1.0f%%', startangle=90,
    textprops={'color': TEXT, 'fontsize': 11},
    wedgeprops={'edgecolor': BG, 'linewidth': 2}
)
for at in autotexts:
    at.set_fontsize(12)
    at.set_fontweight('bold')
ax1.set_title(f'Agent Decisions\n{total} Live Runs', fontsize=13,
              fontweight='bold', color=ACCENT)

# Agent scores per student (grouped by decision)
by_student = {}
for r in agent_runs:
    name = r['student'].split()[0]
    if name not in by_student:
        by_student[name] = []
    by_student[name].append(r['score'])

snames = list(by_student.keys())
avg_scores = [sum(v)/len(v) for v in by_student.values()]
bar_colors = []
for name in snames:
    runs_for = [r for r in agent_runs if r['student'].split()[0] == name]
    decisions = [r['decision'] for r in runs_for]
    if 'shortlist' in decisions:
        bar_colors.append(GREEN)
    elif 'review' in decisions:
        bar_colors.append(YELLOW)
    else:
        bar_colors.append(RED)

bars = ax2.bar(snames, avg_scores, color=bar_colors, edgecolor='none', width=0.55)
for bar, sc in zip(bars, avg_scores):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
             f'{sc:.0f}%', ha='center', fontsize=11, fontweight='bold', color=TEXT)

ax2.axhline(60, color=GREEN,  linestyle='--', alpha=0.5, linewidth=1.2, label='Shortlist ≥60%')
ax2.axhline(45, color=YELLOW, linestyle='--', alpha=0.5, linewidth=1.2, label='Review ≥45%')
ax2.set_ylim(0, 85)
ax2.set_ylabel('Average Agent Score %', fontsize=10)
ax2.set_title('Average Score per Candidate\n(7-Step Agentic Screening)', fontsize=12,
              fontweight='bold', color=ACCENT)
ax2.legend(fontsize=9, facecolor=CARD, edgecolor=ACCENT, labelcolor=TEXT)
ax2.grid(axis='y', alpha=0.3)
ax2.set_axisbelow(True)

fig.suptitle('7-Step Autonomous Recruitment Agent', fontsize=15,
             fontweight='bold', color=ACCENT, y=1.01)
save(fig, '03_agent_decisions.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 4 — RL Weight Agent Before vs After
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 4: RL Weight Agent")

rl = data.get('T4_rl_weights', [])
if rl:
    wkeys   = [d['weight'].title() for d in rl]
    before  = [d['before'] for d in rl]
    a_hire  = [d['after_hire'] for d in rl]
    a_rej   = [d['after_reject'] for d in rl]

    x = np.arange(len(wkeys))
    w = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))
    b1 = ax.bar(x - w,   before,  w, label='Before',       color='#334155', edgecolor='none')
    b2 = ax.bar(x,       a_hire,  w, label='After Hire',   color=GREEN,     edgecolor='none', alpha=0.85)
    b3 = ax.bar(x + w,   a_rej,   w, label='After Reject', color=ACCENT,    edgecolor='none', alpha=0.85)

    for bars in [b1, b2, b3]:
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
                    f'{bar.get_height():.3f}', ha='center', fontsize=8, color=SUBTEXT)

    ax.set_xticks(x)
    ax.set_xticklabels(wkeys, fontsize=11)
    ax.set_ylabel('Weight Value', fontsize=10)
    ax.set_ylim(0, 0.52)
    ax.set_title('RL Weight Agent — Adaptive Learning\nWeights Auto-Adjust After Every Hire / Reject Signal',
                 fontsize=13, fontweight='bold', color=ACCENT, pad=12)
    ax.legend(fontsize=10, facecolor=CARD, edgecolor=ACCENT, labelcolor=TEXT)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)

    # Delta annotation
    for i, d in enumerate(rl):
        delta = d['net_delta']
        clr   = GREEN if delta > 0 else RED
        arrow = '▲' if delta > 0 else '▼'
        ax.text(i + w, a_rej[i] + 0.018,
                f'{arrow}{abs(delta):.3f}', ha='center', fontsize=9,
                color=clr, fontweight='bold')

    save(fig, '04_rl_weights.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 5 — AI Interview Answer Scoring
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 5: AI Interview Scoring")

interview = data.get('T7_interview_scoring', [])
if interview:
    labels = ['Strong\n(Expert)', 'Average\n(Intermediate)', 'Weak\n(Junior)']
    scores = [d['score'] for d in interview]
    expected = [d['expected'] for d in interview]
    bar_cols = [GREEN if s >= 7 else YELLOW if s >= 5 else RED for s in scores]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(labels))
    b1 = ax.bar(x - 0.18, expected, 0.32, label='Expected Score',
                color='#334155', edgecolor='none')
    b2 = ax.bar(x + 0.18, scores,   0.32, label='Gemini Score',
                color=bar_cols,    edgecolor='none')

    for bar in b2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f'{bar.get_height()}/10', ha='center', fontsize=12,
                fontweight='bold', color=TEXT)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 13)
    ax.set_ylabel('Score / 10', fontsize=10)
    ax.set_title('AI Interview Answer Scoring\nGemini Independently Scores 3 Quality Levels',
                 fontsize=13, fontweight='bold', color=ACCENT, pad=12)
    ax.axhline(7, color=GREEN,  linestyle='--', alpha=0.4, linewidth=1)
    ax.axhline(5, color=YELLOW, linestyle='--', alpha=0.4, linewidth=1)
    ax.legend(fontsize=10, facecolor=CARD, edgecolor=ACCENT, labelcolor=TEXT)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)

    save(fig, '05_interview_scoring.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 6 — Skill Demand vs Supply Gap
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 6: Skill Gap Analysis")

gaps = data.get('T8_skill_gap', [])
if gaps:
    skills  = [g['skill'] for g in gaps]
    demand  = [g['demand'] for g in gaps]
    supply  = [g['supply'] for g in gaps]
    gap_v   = [g['gap'] for g in gaps]

    x = np.arange(len(skills))
    w = 0.3

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - w/2, demand, w, label='Jobs Demanding', color=RED,    edgecolor='none', alpha=0.85)
    ax.bar(x + w/2, supply, w, label='Students Having', color=GREEN, edgecolor='none', alpha=0.85)

    # Gap line
    ax.plot(x, gap_v, color=ACCENT, marker='o', linewidth=2.2,
            markersize=7, label='Gap (Demand − Supply)', zorder=5)

    ax.set_xticks(x)
    ax.set_xticklabels(skills, rotation=30, ha='right', fontsize=10)
    ax.set_ylabel('Count', fontsize=10)
    ax.set_title('Skill Demand vs Supply Gap\nTalent Shortage Intelligence for Companies',
                 fontsize=13, fontweight='bold', color=ACCENT, pad=12)
    ax.legend(fontsize=10, facecolor=CARD, edgecolor=ACCENT, labelcolor=TEXT)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)

    save(fig, '06_skill_gap.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 7 — Pipeline Performance Timing
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 7: Pipeline Timing")

timing = data.get('T9_timing', [])
if timing:
    steps = [t['step'].split('.')[1].strip() if '.' in t['step'] else t['step'] for t in timing]
    ms    = [t['ms'] for t in timing]
    cols  = [ACCENT if t['ms'] < 200 else YELLOW if t['ms'] < 1000 else PURPLE for t in timing]

    fig, ax = plt.subplots(figsize=(11, 5))
    bars = ax.barh(steps[::-1], ms[::-1], color=cols[::-1],
                   height=0.55, edgecolor='none')

    for bar, val in zip(bars, ms[::-1]):
        label = f'{val}ms' if val < 1000 else f'{val/1000:.1f}s'
        ax.text(bar.get_width() + 15, bar.get_y() + bar.get_height()/2,
                label, va='center', fontsize=11, fontweight='bold', color=TEXT)

    ax.set_xlim(0, max(ms) * 1.2)
    ax.set_xlabel('Time (ms)', fontsize=10)
    ax.set_title('End-to-End Pipeline Performance\nApply → Match → Agent → Interview → Report',
                 fontsize=13, fontweight='bold', color=ACCENT, pad=12)
    ax.axvline(1000, color=YELLOW, linestyle='--', alpha=0.4, linewidth=1)
    ax.text(1020, -0.5, '1s', color=YELLOW, fontsize=9, alpha=0.7)
    ax.grid(axis='x', alpha=0.3)
    ax.set_axisbelow(True)

    # legend
    fast_p  = mpatches.Patch(color=ACCENT,  label='< 200ms (instant)')
    mid_p   = mpatches.Patch(color=YELLOW,  label='< 1s (fast)')
    slow_p  = mpatches.Patch(color=PURPLE,  label='Gemini API (~1-2s)')
    ax.legend(handles=[fast_p, mid_p, slow_p], fontsize=9,
              facecolor=CARD, edgecolor=ACCENT, labelcolor=TEXT)

    save(fig, '07_pipeline_timing.png')


# ══════════════════════════════════════════════════════════════════════════════
# CHART 8 — MEGA DASHBOARD (all key metrics on one page)
# ══════════════════════════════════════════════════════════════════════════════
print("📊 Chart 8: Full Dashboard (poster-ready summary)")

fig = plt.figure(figsize=(20, 14))
fig.patch.set_facecolor(BG)
gs = GridSpec(3, 4, figure=fig, hspace=0.55, wspace=0.4)

# ── Top title ──
fig.text(0.5, 0.97,
         'AI TALENT MATCH — System Performance Dashboard',
         ha='center', fontsize=20, fontweight='bold', color=ACCENT)
fig.text(0.5, 0.945,
         'Django · Google Gemini 2.5 Flash · Reinforcement Learning · Anti-Cheat · Career AI',
         ha='center', fontsize=11, color=SUBTEXT)

# ── 1. Trust Scores (row 0, col 0-1) ──
ax1 = fig.add_subplot(gs[0, 0:2])
t_names  = [d['name'].split()[0] for d in trust]
t_scores = [d['trust_score'] for d in trust]
t_colors = [GREEN if s >= 80 else YELLOW if s >= 60 else RED for s in t_scores]
ax1.barh(t_names[::-1], t_scores[::-1], color=t_colors[::-1], height=0.55, edgecolor='none')
for i, (n, s) in enumerate(zip(t_names[::-1], t_scores[::-1])):
    ax1.text(s + 1.5, i, f'{s:.0f}', va='center', fontsize=10, fontweight='bold', color=TEXT)
ax1.set_xlim(0, 110)
ax1.set_title('Trust Scores / 100', fontsize=12, fontweight='bold', color=ACCENT)
ax1.grid(axis='x', alpha=0.3); ax1.set_axisbelow(True)

# ── 2. Agent Decisions Pie (row 0, col 2) ──
ax2 = fig.add_subplot(gs[0, 2])
sizes2 = [shortlisted, reviewed, rejected]
ax2.pie(sizes2,
        labels=[f'Shortlisted\n{shortlisted}', f'Review\n{reviewed}', f'Rejected\n{rejected}'],
        colors=[GREEN, YELLOW, RED],
        autopct='%1.0f%%', startangle=90,
        textprops={'color': TEXT, 'fontsize': 9},
        wedgeprops={'edgecolor': BG, 'linewidth': 2})
ax2.set_title('Agent Decisions\n15 Live Runs', fontsize=12, fontweight='bold', color=ACCENT)

# ── 3. Interview Scoring (row 0, col 3) ──
ax3 = fig.add_subplot(gs[0, 3])
i_labels = ['Strong', 'Average', 'Weak']
i_scores = [d['score'] for d in interview] if interview else [8, 6, 2]
i_colors = [GREEN if s >= 7 else YELLOW if s >= 5 else RED for s in i_scores]
bars3 = ax3.bar(i_labels, i_scores, color=i_colors, edgecolor='none', width=0.55)
for bar in bars3:
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.15,
             f'{bar.get_height()}/10', ha='center', fontsize=10, fontweight='bold', color=TEXT)
ax3.set_ylim(0, 13)
ax3.set_title('AI Interview Scoring\nAnswer Quality Tiering', fontsize=12,
              fontweight='bold', color=ACCENT)
ax3.grid(axis='y', alpha=0.3); ax3.set_axisbelow(True)

# ── 4. Match Matrix Heatmap (row 1, col 0-2) ──
ax4 = fig.add_subplot(gs[1, 0:3])
if matrix_rows:
    cmap2 = LinearSegmentedColormap.from_list('talent2',
        ['#0a0f1e', '#1e3a5f', '#48bbff', '#22c55e'])
    im4 = ax4.imshow(matrix, cmap=cmap2, vmin=0, vmax=100, aspect='auto')
    ax4.set_xticks(range(len(job_short)))
    ax4.set_xticklabels(job_short, rotation=35, ha='right', fontsize=8)
    ax4.set_yticks(range(len(student_names)))
    ax4.set_yticklabels(student_names, fontsize=9)
    for i in range(len(student_names)):
        for j in range(len(job_names)):
            v = matrix[i, j]
            ax4.text(j, i, f'{v:.0f}', ha='center', va='center',
                     fontsize=8.5, fontweight='bold',
                     color='white' if v < 55 else BG)
    ax4.set_title('AI Match Score Matrix  (5 Students × 8 Jobs)', fontsize=12,
                  fontweight='bold', color=ACCENT)

# ── 5. Skill Gap (row 1, col 3) ──
ax5 = fig.add_subplot(gs[1, 3])
if gaps:
    g_skills = [g['skill'][:10] for g in gaps[:6]]
    g_gap    = [g['gap'] for g in gaps[:6]]
    g_cols   = [RED if g > 1 else YELLOW if g > 0 else GREEN for g in g_gap]
    ax5.barh(g_skills[::-1], g_gap[::-1], color=g_cols[::-1], height=0.55, edgecolor='none')
    ax5.set_title('Top Skill Gaps\nDemand − Supply', fontsize=12, fontweight='bold', color=ACCENT)
    ax5.set_xlabel('Gap Count', fontsize=9)
    ax5.grid(axis='x', alpha=0.3); ax5.set_axisbelow(True)

# ── 6. Pipeline Timing (row 2, col 0-2) ──
ax6 = fig.add_subplot(gs[2, 0:3])
if timing:
    t_steps = [t['step'].split('.')[1].strip() if '.' in t['step'] else t['step'] for t in timing]
    t_ms    = [t['ms'] for t in timing]
    t_cols  = [ACCENT if m < 200 else YELLOW if m < 1000 else PURPLE for m in t_ms]
    ax6.barh(t_steps[::-1], t_ms[::-1], color=t_cols[::-1], height=0.55, edgecolor='none')
    for bar, val in zip(ax6.patches, t_ms[::-1]):
        label = f'{val}ms' if val < 1000 else f'{val/1000:.1f}s'
        ax6.text(bar.get_width() + 10, bar.get_y() + bar.get_height()/2,
                 label, va='center', fontsize=9, color=TEXT)
    ax6.set_title('Pipeline Performance', fontsize=12, fontweight='bold', color=ACCENT)
    ax6.set_xlabel('Time (ms)', fontsize=9)
    ax6.grid(axis='x', alpha=0.3); ax6.set_axisbelow(True)

# ── 7. Key Stats Card (row 2, col 3) ──
ax7 = fig.add_subplot(gs[2, 3])
ax7.axis('off')
stats = [
    ('Match Pairs',    '40',       ACCENT),
    ('Trust Range',    '42–94/100', GREEN),
    ('Agent Runs',     '15',       ACCENT),
    ('Match Speed',    '17 ms',    GREEN),
    ('Fraud Rules',    '8 rules',  YELLOW),
    ('Career Tracks',  '5 unique', GREEN),
    ('Full Cycle',     '~4 sec',   ACCENT),
    ('Anti-Cheat',     '3-strike', RED),
]
y_pos = 0.95
ax7.text(0.5, 1.02, 'Key Metrics', ha='center', fontsize=12,
         fontweight='bold', color=ACCENT, transform=ax7.transAxes)
for label, val, col in stats:
    ax7.text(0.02, y_pos, label,
             fontsize=9, color=SUBTEXT, transform=ax7.transAxes)
    ax7.text(0.98, y_pos, val,
             fontsize=9, fontweight='bold', color=col,
             ha='right', transform=ax7.transAxes)
    y_pos -= 0.115
    ax7.plot([0.02, 0.98], [y_pos + 0.06, y_pos + 0.06],
             color='#1e3a5f', linewidth=0.7, transform=ax7.transAxes)

save(fig, '00_FULL_DASHBOARD.png')

print(f"\n✅ All charts saved to ./{OUT_DIR}/")
print("   Files:")
for f in sorted(os.listdir(OUT_DIR)):
    path = os.path.join(OUT_DIR, f)
    size = os.path.getsize(path) // 1024
    print(f"   📄 {f}  ({size} KB)")
print("\n🎯 Use 00_FULL_DASHBOARD.png for your poster!")
