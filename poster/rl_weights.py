import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np

# ── DATA ──────────────────────────────────────────────────────
features   = ['CGPA', 'Skills', 'Experience', 'Projects', 'Activity', 'Trust']
before     = [20.0, 20.0, 20.0, 15.0, 10.0, 15.0]
after_hire = [26.0, 17.0, 21.0, 16.0, 13.0, 18.0]
after_rej  = [18.0, 23.0, 19.0, 14.0,  9.0, 13.0]

table_data = [
    ('CGPA',       '20.0%', '26.0%', '▲ +6.0%', True),
    ('Skills',     '20.0%', '17.0%', '▼ −3.0%', False),
    ('Experience', '20.0%', '21.0%', '▲ +1.0%', True),
    ('Projects',   '15.0%', '16.0%', '▲ +1.0%', True),
    ('Activity',   '10.0%', '13.0%', '▲ +3.0%', True),
    ('Trust',      '15.0%', '18.0%', '▲ +3.0%', True),
]

# ── COLORS ────────────────────────────────────────────────────
C_BG     = '#0d1b2e'
C_CARD   = '#0f2440'
C_BORDER = '#1e3a6b'
C_BEFORE = '#38bdf8'
C_HIRE   = '#22c55e'
C_REJECT = '#ef4444'
C_TEXT   = '#e2e8f0'
C_MUTED  = '#94a3b8'
C_HEAD   = '#38bdf8'

# ── FIGURE with GridSpec ───────────────────────────────────────
fig = plt.figure(figsize=(9, 9), facecolor='none')
fig.patch.set_alpha(0)

gs = gridspec.GridSpec(2, 1, figure=fig,
                       height_ratios=[1.6, 1],
                       hspace=0.12,
                       left=0.09, right=0.97,
                       top=0.97, bottom=0.04)

ax_chart = fig.add_subplot(gs[0])
ax_table = fig.add_subplot(gs[1])

# ── DARK BG PATCHES ───────────────────────────────────────────
for ax in (ax_chart, ax_table):
    bg = mpatches.FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="round,pad=0.01",
        facecolor=C_BG, edgecolor=C_BORDER, linewidth=1,
        transform=ax.transAxes, zorder=0, clip_on=False
    )
    ax.add_patch(bg)
    ax.set_facecolor(C_BG)
    for sp in ax.spines.values():
        sp.set_color(C_BORDER)

# ── BAR CHART ─────────────────────────────────────────────────
x = np.arange(len(features))
w = 0.26

ax_chart.bar(x - w, before,     w, color=C_BEFORE, alpha=0.88, zorder=3)
ax_chart.bar(x,     after_hire, w, color=C_HIRE,   alpha=0.88, zorder=3)
ax_chart.bar(x + w, after_rej,  w, color=C_REJECT, alpha=0.88, zorder=3)

ax_chart.yaxis.grid(True, color=C_BORDER, linewidth=0.6, zorder=0)
ax_chart.set_axisbelow(True)
ax_chart.set_xlim(-0.55, len(features) - 0.45)
ax_chart.set_ylim(0, 34)
ax_chart.set_yticks([0, 5, 10, 15, 20, 25, 30])
ax_chart.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v)}%'))
ax_chart.tick_params(axis='y', colors=C_MUTED, labelsize=9, length=0)
ax_chart.set_xticks(x)
ax_chart.set_xticklabels(features, color=C_TEXT, fontsize=11, fontweight='bold')
ax_chart.tick_params(axis='x', length=0, pad=6)

leg = ax_chart.legend(
    handles=[
        mpatches.Patch(facecolor=C_BEFORE, label='Uniform (Before)'),
        mpatches.Patch(facecolor=C_HIRE,   label='▲ After Hire Signal'),
        mpatches.Patch(facecolor=C_REJECT, label='▼ After Reject Signal'),
    ],
    loc='upper right', ncol=1,
    frameon=True, facecolor=C_CARD, edgecolor=C_BORDER,
    labelcolor=C_TEXT, fontsize=9.5,
    handlelength=1.2, handleheight=0.9,
)

# ── TABLE ─────────────────────────────────────────────────────
ax_table.set_xlim(0, 1)
ax_table.set_ylim(0, 1)
ax_table.axis('off')

col_x    = [0.02, 0.32, 0.58, 0.80]
headers  = ['FEATURE', 'BEFORE', 'AFTER HIRE', 'Δ CHANGE']
n        = len(table_data)
head_h   = 0.18
row_h    = (1 - head_h) / n

# Header row
header_bg = mpatches.FancyBboxPatch(
    (0, 1 - head_h), 1, head_h,
    boxstyle="square,pad=0", linewidth=0,
    facecolor=C_CARD, transform=ax_table.transAxes, zorder=2
)
ax_table.add_patch(header_bg)
for cx, hdr in zip(col_x, headers):
    ax_table.text(cx, 1 - head_h / 2, hdr,
                  color=C_HEAD, fontsize=9.5, fontweight='bold',
                  va='center', transform=ax_table.transAxes, zorder=3)

# Header bottom border
ax_table.axhline(1 - head_h, color=C_BORDER, linewidth=1, zorder=3)

# Data rows
for i, (feat, bef, aft, delta, is_up) in enumerate(table_data):
    y_top = 1 - head_h - i * row_h
    y_bot = y_top - row_h
    y_mid = (y_top + y_bot) / 2

    if i % 2 == 1:
        stripe = mpatches.FancyBboxPatch(
            (0, y_bot), 1, row_h,
            boxstyle="square,pad=0", linewidth=0,
            facecolor=C_CARD, transform=ax_table.transAxes, zorder=2
        )
        ax_table.add_patch(stripe)

    ax_table.axhline(y_bot, color=C_BORDER, linewidth=0.4, zorder=3)

    dc = C_HIRE if is_up else C_REJECT
    vals   = [feat, bef, aft, delta]
    colors = [C_TEXT, C_MUTED, C_TEXT, dc]
    bolds  = [True, False, False, True]

    for cx, val, color, bold in zip(col_x, vals, colors, bolds):
        ax_table.text(cx, y_mid, val,
                      color=color, fontsize=10,
                      fontweight='bold' if bold else 'normal',
                      va='center', transform=ax_table.transAxes, zorder=4)

# ── SAVE ──────────────────────────────────────────────────────
plt.savefig('poster/rl_weights.png', dpi=180,
            bbox_inches='tight', transparent=True, facecolor='none')
print("✅ Saved → poster/rl_weights.png")
plt.show()
