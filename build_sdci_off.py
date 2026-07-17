#!/usr/bin/env python3
"""
Build CX7-Core-Scaling-SDCI-OFF-VeniceB0-G2-BIOS.xlsx
  Tab 0 "System"     — platform / NIC / BIOS / test method info
  Tab 1 "1P"         — 1-core sweep results
  Tab 2 "2P"         — 2-core sweep results
  Tab 3 "8P"         — 8-core sweep results (merged from two runs)
  Tab 4 "16P"        — 16-core sweep results
Output: CX7/CX7-Core-Scaling-SDCI-OFF-VeniceB0-G2-BIOS.xlsx
"""
import os, csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ── resolve CX7 repo root ──────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_p = _HERE
for _ in range(6):
    if os.path.isdir(os.path.join(_p, "1P")) and os.path.isdir(os.path.join(_p, "16P")):
        break
    _p = os.path.dirname(_p)
CX7 = os.path.normpath(_p)

AMD_RED  = "ED1C24"; AMD_GREY = "58595B"; HDR_BLUE = "1F4E78"
LT_GREY  = "F2F2F2"; WHITE    = "FFFFFF"; BEST_GRN = "C6EFCE"
STUDY_COLORS = {"1P": "BDD7EE", "2P": "FCE4D6", "8P": "E2EFDA", "16P": "FFF2CC"}

thin  = Side(style="thin",  color="BFBFBF")
thick = Side(style="medium", color="8EA9C1")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

def title(ws, r, c1, c2, t, bg=AMD_RED, fg=WHITE, sz=13, ht=26):
    ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
    c = ws.cell(r, c1, t)
    c.font = Font(bold=True, color=fg, size=sz)
    c.fill = PatternFill("solid", fgColor=bg)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[r].height = ht

def kv(ws, r, k, v):
    a = ws.cell(r, 1, k); b = ws.cell(r, 2, v)
    a.font = Font(bold=True, color="333333"); a.alignment = Alignment(vertical="center", indent=1)
    b.alignment = Alignment(vertical="center", indent=1, wrap_text=True)
    a.fill = PatternFill("solid", fgColor=LT_GREY); a.border = BORDER; b.border = BORDER
    ws.row_dimensions[r].height = 16

def hdr(ws, r, c, t, bg=HDR_BLUE, fg=WHITE, sz=9):
    cell = ws.cell(r, c, t)
    cell.font = Font(bold=True, color=fg, size=sz)
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = BORDER
    return cell

def val(ws, r, c, v, bg=None, bold=False, fmt="0.00"):
    cell = ws.cell(r, c, v)
    cell.font = Font(bold=bold, color="111111")
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.number_format = fmt
    cell.border = BORDER
    if bg:
        cell.fill = PatternFill("solid", fgColor=bg)
    return cell

def load_avgs(path):
    rows = {}
    if not path or not os.path.exists(path):
        return rows
    with open(path) as f:
        rdr = csv.reader(f); next(rdr)
        for rec in rdr:
            if rec and rec[0].isdigit():
                rows[int(rec[0])] = rec
    return rows

# ── Load data ──────────────────────────────────────────────────────────────────
d1p  = load_avgs(os.path.join(CX7, "1P",  "results_20260716_202543", "averages.csv"))
d2p  = load_avgs(os.path.join(CX7, "2P",  "results_20260716_221130", "averages.csv"))
# 8P: merge first run (P1-12 valid) + resumed run (P16-32)
d8p_a = load_avgs(os.path.join(CX7, "8P", "results_20260717_000053", "averages.csv"))
d8p_b = load_avgs(os.path.join(CX7, "8P", "results_20260717_063547", "averages.csv"))
d8p = {P: d8p_a[P] for P in [1,2,4,8,12] if P in d8p_a}
d8p.update(d8p_b)   # P16-32 from clean resumed run
d16p = load_avgs(os.path.join(CX7, "16P", "results_20260717_073011", "averages.csv"))

P_LIST = [1, 2, 4, 8, 12, 16, 20, 24, 28, 32]
STUDIES = [("1P", d1p, 1), ("2P", d2p, 2), ("8P", d8p, 8), ("16P", d16p, 16)]

wb = openpyxl.Workbook()

# ══════════════════════════════════════════════════════════════════════════════
# Tab 0: System
# ══════════════════════════════════════════════════════════════════════════════
ws = wb.active; ws.title = "System"; ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 30; ws.column_dimensions["B"].width = 82

title(ws,1,1,2,"CX7 Core-Scaling iPerf Study — System Configuration  (SDCI DISABLED)",
      bg=AMD_RED, sz=14, ht=30)
title(ws,2,1,2,"Platform: Venice B0  |  BIOS: G2 (PCOV207040_G2N)  |  SUT: congo-0573-host  |  SDCI: DISABLED",
      bg=AMD_GREY, sz=10, ht=18)

r = 4
title(ws,r,1,2,"PLATFORM / CPU", bg=HDR_BLUE, sz=11); r+=1
for k,v_ in [
    ("Platform","AMD Venice B0"),
    ("System (SUT)","congo-0573-host"),
    ("Load Generator","galena-3666-host"),
    ("CPU Model","AMD Eng Sample: 100-000001041-03"),
    ("Topology","1 socket, 256 cores/socket, 2 threads/core = 512 CPUs"),
    ("CPU Freq (forced cclk)","2500 MHz  (confirmed via cpupower — policy max 2.50 GHz, asserted by HW)"),
    ("Governor / Boost","performance / OFF"),
    ("NUMA","node0: 0-127,256-383  |  node1: 128-255,384-511"),
]:
    kv(ws,r,k,v_); r+=1
r+=1
title(ws,r,1,2,"BIOS / FIRMWARE", bg=HDR_BLUE, sz=11); r+=1
for k,v_ in [
    ("BIOS Version","PCOV207040_G2N  (\"G2\" BIOS)"),
    ("BIOS Release Date","06/25/2026"),
    ("DF EnSrcDnCnRply","0x1"),
    ("SDCI State","DISABLED  ← this study"),
    ("OS / Kernel","Ubuntu 24.04.3 LTS / 6.8.0-117-generic"),
]:
    kv(ws,r,k,v_); r+=1
r+=1
title(ws,r,1,2,"NIC UNDER TEST — ConnectX-7 (eth2)", bg=HDR_BLUE, sz=11); r+=1
for k,v_ in [
    ("Device","NVIDIA/Mellanox ConnectX-7 (MT2910)"),
    ("Part Number","MCX75310AAS-NEA_Ax"),
    ("Mellanox FW","28.48.1000 (MT_0000000838)"),
    ("Driver","mlx5_core v26.01-1.0.0"),
    ("PCI BDF","0000:21:00.0"),
    ("PCIe Link","Gen5 32GT/s x16"),
    ("Data IP","192.168.10.2/24  (peer loadgen 192.168.10.3)"),
    ("Link Speed","400G, Full duplex, DAC, Link UP"),
    ("MTU","1500"),
]:
    kv(ws,r,k,v_); r+=1
r+=1
title(ws,r,1,2,"TEST METHOD", bg=HDR_BLUE, sz=11); r+=1
for k,v_ in [
    ("Tool","iperf3 — N concurrent processes (one per core); -P parallel streams per process"),
    ("Direction","SUT clients → LoadGen servers (unidirectional TCP Rx)"),
    ("Duration / Iterations","60 s per run, 10 iterations per -P (aggregate avg reported)"),
    ("-P sweep","1, 2, 4, 8, 12, 16, 20, 24, 28, 32  (same -P on all procs)"),
    ("IRQ steering","1P: all 64 IRQs → sibling 261 (core 5+256)"),
    ("IRQ steering","2P/8P/16P: 64 IRQs interleaved across SMT siblings via irq_index % NUM_CORES"),
    ("Throughput","Aggregate = sum of all procs; per-core detail retained in raw JSON"),
    ("SDCI State","DISABLED"),
]:
    kv(ws,r,k,v_); r+=1
r+=1
title(ws,r,1,2,"STUDY CONFIGURATION SUMMARY", bg=HDR_BLUE, sz=11); r+=1
for label, _, nc in STUDIES:
    siblings = f"{256+1}..{256+nc}" if nc > 1 else "261 (all IRQs)"
    kv(ws, r, f"{label}  ({nc}-core)",
       f"Cores 1..{nc}  (skip 0)  |  {nc}Q combined  |  IRQs → siblings {siblings}  |  "
       f"10 iters × 60 s  |  SDCI DISABLED")
    r+=1

# ══════════════════════════════════════════════════════════════════════════════
# Per-study tabs
# ══════════════════════════════════════════════════════════════════════════════
def make_study_tab(wb, label, data, num_cores, color):
    ws = wb.create_sheet(label)
    ws.sheet_view.showGridLines = False

    siblings_str = (f"siblings {257}–{256+num_cores}" if num_cores > 1
                    else "sibling 261 (core 5+256)")
    irq_str = (f"64 IRQs interleaved across {siblings_str} via i%{num_cores}"
               if num_cores > 1 else f"all 64 IRQs → {siblings_str}")

    NCOLS = 6
    for j,w in enumerate([8,15,11,11,9,14], start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w

    title(ws,1,1,NCOLS,
          f"CX7 {label} iPerf Core-Scaling — SDCI DISABLED  |  Venice B0, G2 BIOS",
          bg=AMD_RED, sz=14, ht=30)
    title(ws,2,1,NCOLS,
          f"eth2 (CX7 400G)  |  {num_cores}Q  |  iperf cores 1–{num_cores}  |  "
          f"{irq_str}  |  60 s × 10 iters  |  SDCI DISABLED",
          bg=AMD_GREY, sz=9, ht=20)

    # study config block
    r = 4
    title(ws,r,1,NCOLS,f"{label} CONFIGURATION", bg=HDR_BLUE, sz=10, ht=18); r+=1
    ws.column_dimensions["A"].width = 28; ws.column_dimensions["B"].width = 60
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NCOLS)
    c = ws.cell(r, 1,
        f"Cores: {num_cores}  |  iperf procs: {num_cores}  |  Combined queues: {num_cores}  |  "
        f"IRQ: {irq_str}  |  SDCI: DISABLED  |  cclk: 2500 MHz")
    c.alignment = Alignment(vertical="center", indent=1, wrap_text=True)
    c.border = BORDER; ws.row_dimensions[r].height = 20; r+=2

    # header row
    title(ws,r,1,NCOLS,f"{label} SWEEP — Aggregate throughput (SDCI DISABLED)",
          bg=HDR_BLUE, sz=10, ht=18); r+=1
    hr = r
    for j,h in enumerate(["-P","Agg avg\n(Gbps)","Min\n(Gbps)","Max\n(Gbps)","CV %","Retrans\navg"], start=1):
        hdr(ws, hr, j, h, bg=HDR_BLUE, sz=9)
    ws.row_dimensions[hr].height = 30; r+=1

    best_P = max(data, key=lambda x: float(data[x][1])) if data else None
    for P in P_LIST:
        ws.row_dimensions[r].height = 15
        row_bg = LT_GREY if r % 2 == 0 else None
        d = data.get(P)
        is_best = (P == best_P)
        bg = BEST_GRN if is_best else row_bg

        val(ws, r, 1, P, bg=bg, bold=is_best, fmt="0")
        if d:
            val(ws, r, 2, float(d[1]), bg=bg, bold=is_best)
            val(ws, r, 3, float(d[2]), bg=bg)
            val(ws, r, 4, float(d[3]), bg=bg)
            val(ws, r, 5, float(d[4]), bg=bg)
            val(ws, r, 6, float(d[5]), bg=bg)
        else:
            for j in range(2, 7):
                val(ws, r, j, "—", bg=LT_GREY, fmt="@")
        r+=1

    # best-P summary
    r+=1
    title(ws,r,1,NCOLS,"BEST -P", bg=HDR_BLUE, sz=10, ht=18); r+=1
    if best_P:
        bv = float(data[best_P][1]); cv = float(data[best_P][4])
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NCOLS)
        c = ws.cell(r, 1, f"-P {best_P}  →  {bv:.2f} Gbps  (CV {cv:.2f}%)")
        c.font = Font(bold=True, color="111111", size=11)
        c.fill = PatternFill("solid", fgColor=BEST_GRN)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
        ws.row_dimensions[r].height = 22; r+=2

    # key observations
    title(ws,r,1,NCOLS,"KEY OBSERVATIONS", bg=HDR_BLUE, sz=10, ht=18); r+=1
    plateau_vals = [float(data[P][1]) for P in P_LIST if P in data and P >= 4]
    notes = [
        f"Best -P: {best_P} → {float(data[best_P][1]):.2f} Gbps (CV {float(data[best_P][4]):.2f}%)." if best_P else "",
        f"Plateau ({num_cores} cores, SDCI OFF): {min(plateau_vals):.1f}–{max(plateau_vals):.1f} Gbps "
        f"from -P 4 onward." if plateau_vals else "",
        f"Config: {num_cores}Q combined, {irq_str}, cclk=2500 MHz, governor=performance, boost=OFF.",
        "SDCI DISABLED. Compare against SDCI ENABLED study for SDCI impact.",
    ]
    for n in notes:
        if not n: continue
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NCOLS)
        c = ws.cell(r, 1, "•  " + n)
        c.alignment = Alignment(vertical="center", indent=1, wrap_text=True)
        ws.row_dimensions[r].height = 26; r+=1

for label, data, nc in STUDIES:
    make_study_tab(wb, label, data, nc, STUDY_COLORS[label])

OUT = os.path.join(CX7, "CX7-Core-Scaling-SDCI-OFF-VeniceB0-G2-BIOS.xlsx")
wb.save(OUT)
print("WROTE:", OUT)
for label, data, _ in STUDIES:
    best_P = max(data, key=lambda x: float(data[x][1])) if data else None
    print(f"  {label}: best -P {best_P} → {float(data[best_P][1]):.2f} Gbps" if best_P else f"  {label}: no data")
