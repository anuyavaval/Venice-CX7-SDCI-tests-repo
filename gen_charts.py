#!/usr/bin/env python3
"""Generate SDCI OFF vs ON line chart PNGs for each study (1P, 2P, 8P, 16P)."""
import os, csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── resolve CX7 root ───────────────────────────────────────────────────────────
CX7 = os.environ.get("CX7_ROOT") or r"C:\Users\anuvaval\Documents\cx8-core-scaling\CX7"
CX7 = os.path.normpath(CX7)
OUTDIR = os.path.join(CX7, "charts"); os.makedirs(OUTDIR, exist_ok=True)
print("CX7:", CX7)

# ── colours ────────────────────────────────────────────────────────────────────
C_OFF  = "#ED7D31"   # orange — SDCI OFF
C_ON   = "#4472C4"   # blue   — SDCI ON
C_OFF_L= "#FDDCBC"   # light orange fill
C_ON_L = "#C5D5EF"   # light blue fill
BG     = "#FAFAFA"
GRID   = "#E8E8E8"

def load_avgs(path):
    rows={}
    if not path or not os.path.exists(path): return rows
    with open(path) as f:
        rdr=csv.reader(f); next(rdr)
        for rec in rdr:
            if rec and rec[0].isdigit(): rows[int(rec[0])]=rec
    return rows

P_LIST=[1,2,4,8,12,16,20,24,28,32]

OFF_DIRS={
    "1P": os.path.join(CX7,"1P","results_20260716_202543"),
    "2P": os.path.join(CX7,"2P","results_20260716_221130"),
    "8P_a":os.path.join(CX7,"8P","results_20260717_000053"),
    "8P_b":os.path.join(CX7,"8P","results_20260717_063547"),
    "16P":os.path.join(CX7,"16P","results_20260717_073011"),
}
ON_DIRS={
    "1P": os.path.join(CX7,"1P","results_20260717_104422"),
    "2P": os.path.join(CX7,"2P","results_20260717_122930"),
    "8P": os.path.join(CX7,"8P","results_20260717_163411"),
    "16P":os.path.join(CX7,"16P","results_20260717_182032"),
}

def load_off(label):
    if label=="8P":
        d=load_avgs(os.path.join(OFF_DIRS["8P_a"],"averages.csv"))
        da={P:d[P] for P in [1,2,4,8,12] if P in d}
        db=load_avgs(os.path.join(OFF_DIRS["8P_b"],"averages.csv"))
        da.update(db); return da
    return load_avgs(os.path.join(OFF_DIRS[label],"averages.csv"))

def load_on(label):
    return load_avgs(os.path.join(ON_DIRS[label],"averages.csv"))

def get_vals(d):
    return [float(d[P][1]) if P in d else None for P in P_LIST]

def best_p(d):
    if not d: return None
    return max(d, key=lambda x: float(d[x][1]))

STUDIES=[
    ("1P",  1,  "1 Core  |  1Q  |  All IRQs → sibling 261"),
    ("2P",  2,  "2 Cores  |  2Q  |  IRQs interleaved → siblings 257–258"),
    ("8P",  8,  "8 Cores  |  8Q  |  IRQs interleaved → siblings 261–268"),
    ("16P", 16, "16 Cores  |  16Q  |  IRQs interleaved → siblings 257–272"),
]

for label, nc, subtitle in STUDIES:
    doff = load_off(label)
    don  = load_on(label)

    y_off = get_vals(doff)
    y_on  = get_vals(don)
    x     = list(range(len(P_LIST)))
    x_labels = [str(p) for p in P_LIST]

    bp_off = best_p(doff)
    bp_on  = best_p(don)
    bv_off = float(doff[bp_off][1]) if bp_off else None
    bv_on  = float(don[bp_on][1])   if bp_on  else None
    bi_off = P_LIST.index(bp_off)   if bp_off else None
    bi_on  = P_LIST.index(bp_on)    if bp_on  else None

    fig, ax = plt.subplots(figsize=(10, 5.2))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # ── light fill between curves ──────────────────────────────────────────────
    y_off_arr = np.array([v if v is not None else np.nan for v in y_off])
    y_on_arr  = np.array([v if v is not None else np.nan for v in y_on])
    ax.fill_between(x, y_off_arr, y_on_arr, alpha=0.12, color="#888888")

    # ── lines ─────────────────────────────────────────────────────────────────
    ax.plot(x, y_off_arr, color=C_OFF, linewidth=2.2, marker="o",
            markersize=5, markerfacecolor=C_OFF_L, markeredgecolor=C_OFF,
            markeredgewidth=1.4, label="SDCI DISABLED", zorder=3)
    ax.plot(x, y_on_arr,  color=C_ON,  linewidth=2.2, marker="o",
            markersize=5, markerfacecolor=C_ON_L,  markeredgecolor=C_ON,
            markeredgewidth=1.4, label="SDCI ENABLED",  zorder=3)

    # ── peak markers (larger, filled, annotated) ───────────────────────────────
    if bi_off is not None and y_off[bi_off] is not None:
        ax.plot(x[bi_off], y_off[bi_off], marker="*", markersize=16,
                color=C_OFF, zorder=5, linestyle="None",
                label=f"Peak OFF: -P {bp_off} → {bv_off:.1f} Gbps")
        ax.annotate(f" -P{bp_off}\n {bv_off:.1f} Gbps",
                    xy=(x[bi_off], y_off[bi_off]),
                    xytext=(x[bi_off]+0.25, y_off[bi_off]),
                    fontsize=7.5, color=C_OFF, va="center",
                    arrowprops=dict(arrowstyle="->", color=C_OFF, lw=0.8))

    if bi_on is not None and y_on[bi_on] is not None:
        ax.plot(x[bi_on], y_on[bi_on], marker="*", markersize=16,
                color=C_ON, zorder=5, linestyle="None",
                label=f"Peak ON:  -P {bp_on} → {bv_on:.1f} Gbps")
        offset = -0.35 if bi_on == bi_off else 0.25
        ax.annotate(f" -P{bp_on}\n {bv_on:.1f} Gbps",
                    xy=(x[bi_on], y_on[bi_on]),
                    xytext=(x[bi_on]+offset, y_on[bi_on]),
                    fontsize=7.5, color=C_ON, va="center",
                    arrowprops=dict(arrowstyle="->", color=C_ON, lw=0.8))

    # ── formatting ────────────────────────────────────────────────────────────
    ax.set_xticks(x); ax.set_xticklabels(x_labels, fontsize=9)
    ax.set_xlabel("-P  (parallel streams per iperf3 process)", fontsize=9.5)
    ax.set_ylabel("Aggregate Throughput  (Gbps)", fontsize=9.5)
    ax.set_title(f"CX7 {label}  —  SDCI OFF vs ON  |  Venice B0, G2 BIOS\n{subtitle}",
                 fontsize=11, fontweight="bold", pad=10)
    ax.grid(True, color=GRID, linewidth=0.8, linestyle="--", zorder=0)
    ax.spines[["top","right"]].set_visible(False)
    ax.spines[["left","bottom"]].set_color("#CCCCCC")
    ax.tick_params(colors="#555555")

    # ── y-axis range with a little headroom ───────────────────────────────────
    all_vals = [v for v in list(y_off) + list(y_on) if v is not None]
    if all_vals:
        ymin = min(all_vals)*0.97; ymax = max(all_vals)*1.025
        ax.set_ylim(ymin, ymax)

    # ── legend ────────────────────────────────────────────────────────────────
    ax.legend(loc="lower right", fontsize=8, framealpha=0.85,
              edgecolor="#CCCCCC", facecolor=BG)

    # ── footer note ───────────────────────────────────────────────────────────
    fig.text(0.5, 0.01,
             "10 iterations × 60 s per -P  |  iperf3 TCP Rx  |  cclk=2500 MHz  |  governor=performance  |  boost=OFF",
             ha="center", fontsize=7, color="#888888")

    plt.tight_layout(rect=[0,0.03,1,1])
    outpath = os.path.join(OUTDIR, f"chart_{label}_sdci_off_vs_on.png")
    plt.savefig(outpath, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"  Saved: {outpath}")

# ── Summary bar chart ──────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)

labels_s  = ["1P (1-core)","2P (2-core)","8P (8-core)","16P (16-core)"]
labels_k  = ["1P","2P","8P","16P"]
vals_off  = []
vals_on   = []
for lbl in labels_k:
    doff=load_off(lbl); don=load_on(lbl)
    bp_off=best_p(doff); bp_on=best_p(don)
    vals_off.append(float(doff[bp_off][1]) if bp_off else 0)
    vals_on.append(float(don[bp_on][1])    if bp_on  else 0)

x=np.arange(len(labels_s)); w=0.32
b1=ax.bar(x-w/2, vals_off, w, color=C_OFF, alpha=0.85, label="SDCI DISABLED", zorder=3)
b2=ax.bar(x+w/2, vals_on,  w, color=C_ON,  alpha=0.85, label="SDCI ENABLED",  zorder=3)

for bar,v in list(zip(b1,vals_off))+list(zip(b2,vals_on)):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+2,
            f"{v:.1f}", ha="center", va="bottom", fontsize=7.5, color="#333333")

ax.set_xticks(x); ax.set_xticklabels(labels_s, fontsize=9)
ax.set_ylabel("Peak Aggregate Throughput  (Gbps)", fontsize=9.5)
ax.set_title("CX7 Core-Scaling — Peak Throughput Summary  |  SDCI OFF vs ON\nVenice B0, G2 BIOS",
             fontsize=11, fontweight="bold", pad=10)
ax.grid(True, axis="y", color=GRID, linewidth=0.8, linestyle="--", zorder=0)
ax.spines[["top","right"]].set_visible(False)
ax.spines[["left","bottom"]].set_color("#CCCCCC")
ax.legend(fontsize=9, framealpha=0.85, edgecolor="#CCCCCC", facecolor=BG)
plt.tight_layout()
outpath=os.path.join(OUTDIR,"chart_summary_peak.png")
plt.savefig(outpath,dpi=150,bbox_inches="tight",facecolor=BG)
plt.close()
print(f"  Saved: {outpath}")
print(f"\nAll charts -> {OUTDIR}")
