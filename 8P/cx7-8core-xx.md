# CX7 8-Core (8P) iPerf Core-Scaling — Resume Guide

> 8-core iPerf3 study on ConnectX-7 (400G), Venice B0, **SDCI ENABLED**.
> Extends the 1-core (1P) study. Same platform/tuning; only the multi-core
> parts differ. Shared connection method, credentials, mlx5-IRQ-by-BDF quirk,
> and hardware/FW details live in `../1P/CONNECTION_SKILL.md` — not repeated here.

---

## 1. Test Definition (8 cores)

| Item | Value |
|------|-------|
| NIC (SUT) | **eth2** (CX7 400G), IP 192.168.10.2, BDF 0000:21:00.0 |
| LoadGen NIC | **enp1s0np0**, IP 192.168.10.3 |
| iperf tool | **iperf3** — 8 concurrent processes, one pinned per core |
| iperf cores | **5-12** (`taskset -c <core>`, one proc each) |
| Queues | **8Q combined** (`ethtool -L eth2 combined 8`) — = number of cores |
| IRQ mapping | 64 eth2 IRQs **interleaved** across SMT siblings **261-268** via `IRQ_index % 8` |
| Ports | one iperf3 server per core: **5201-5208** |
| `-P` sweep | **1, 2, 4, 8, 12, 16, 20, 24, 28, 32** (same -P on all 8 procs) |
| Iterations | **10 per -P**, 60 s each |
| Throughput | **aggregate = sum of 8 procs**; per-core detail retained |
| SDCI | **ENABLED** |

### Sibling map (CCD0): `sibling = core + 256`
cores 5,6,7,8,9,10,11,12 → siblings 261,262,263,264,265,266,267,268.
Verified on box via `/sys/devices/system/cpu/cpuN/topology/thread_siblings_list`.

### IRQ interleave (the `%` logic, from parent CX8 convention)
64 IRQs assigned round-robin: IRQ i → `SIBLINGS[i % 8]`. Note IRQ index 0 is
`mlx5_async0` (not comp0), so comp0 lands on 262, comp1→263, … comp7→261,
comp8→262, … — every completion queue gets a distinct sibling.

---

## 2. How to Run (from Windows workstation)

```bash
cd 8P
cp config.env.example config.env      # first time: set CX7_SUT_PW / CX7_LG_PW
python run_cx7_8p_sweep.py            # ~1h40m (10 -P x 10 iters x 60s)
python build_cx7_8p_study.py          # -> results/CX7-8C-study-...xlsx
```

Orchestrator does everything over SSH (paramiko): starts 8 iperf3 servers on
the loadgen, tunes the SUT, sets 8Q, interleaves the 64 IRQs, runs the sweep
(8 procs concurrent per iteration via ThreadPoolExecutor), writes CSVs + raw JSON.

Output `results_<timestamp>/`:
- `summary.csv`   — per iteration (P, iter, agg_gbps, retransmits)
- `percore.csv`   — per iteration, per-core Gbps (core5..core12)
- `averages.csv`  — per-P agg avg/min/max/CV/avg-retrans
- `P<P>_iter<i>_core<c>.json` — raw iperf3 JSON (800 files for full sweep)

To add the 8P tab into the combined 1C+8C workbook: run `../add_8p_tab.py`.

---

## 3. Results Summary (run 2026-07-13, results_20260713_144947)

| -P | Agg Gbps | CV% | Retrans avg |
|----|---------|-----|-------------|
| 1 | 208.35 | 8.45 | 0 |
| 2 | 322.59 | 4.30 | 76 |
| 4 | 313.84 | 12.61 | 17.8K |
| 8 | 330.28 | 1.31 | 133K |
| 12 | 331.39 | 1.17 | 282K |
| 16 | 333.30 | 1.21 | 411K |
| **20** | **334.15** | 0.98 | 490K |
| 24 | 331.84 | 1.20 | 556K |
| 28 | 331.26 | 0.77 | 605K |
| 32 | 330.74 | 0.60 | 676K |

- **Best: -P 20 → 334 Gbps.** Plateau ~330 Gbps from P8 up.
- **~3.1x** the 1-core SDCI-on (~107 Gbps) — **sub-linear**; ceiling is the shared
  NIC/PCIe/400G path, not per-core. Per-core ~40-45 Gbps, well balanced.
- **Retransmits climb hard with -P** (133K→676K). 1P had ~zero; 8-core pushes the
  NIC into TCP loss. **P8-P12 = sweet spot** (full throughput, lower retrans, tight CV).
- **-P 4 unstable** (CV 12.6%, one bad iter min=203) — avoid for reporting.

---

## 4. Gotchas learned building 8P (do NOT re-hit these)

1. **`config.env` inline comments broke the parser.** Values like `CX7_NUM_CORES=8
   # cores` were read as `"8        # cores"` → int() crash. Fixed: the loader now
   strips inline `#` comments (`cx7_config.py`). Same fix applied to 1P.
2. **sed `\1` backreference gets mangled** through the Python→JSON→`sudo bash -c`
   layering (returned `\x01`). Use `awk -F: '{print $1}' | tr -d ' '` to extract
   IRQ numbers instead.
3. **Multi-statement bash with arrays does NOT survive** the sudo-bash JSON wrap
   (`SIB=(...)`, `$((i % N))` failed — "division by 0", array empty). Fix: compute
   the IRQ→sibling assignment **in Python**, then issue simple `echo N > ...` writes
   joined with `;`. This is the robust pattern — reuse it for 16P.
4. **combined=N resets IRQ affinities** — always set `ethtool -L combined N` FIRST,
   then steer IRQs.
5. **Cleanup step can crash after a long run** — the loadgen SSH channel may drop
   during the final `pkill` (WinError 10054). CSVs are already saved by then; the
   crash is cosmetic. Cleanup is now wrapped in try/except. If it does crash, kill
   stray servers manually: `pkill -f 'iperf3 -s'` on the loadgen.
6. **After SDCI reboot**, eth2 came up DOWN with no IP — `ip link set eth2 up` +
   re-add `192.168.10.2/24` before testing (see 1P results memory).

---

## 5. Scaling Up (future 16P) — we can build on this

The current scripts hardcode 8 cores via `config.env` knobs (`CX7_NUM_CORES=8`,
`CX7_BASE_CORE=5`). For 16P:
- Set `CX7_NUM_CORES=16` → cores 5-20, siblings 261-276, 16Q, ports 5201-5216.
- The `% NUM_CORES` IRQ interleave already generalizes (64 IRQs / 16 cores = 4 each).
- Copy 8P/ → 16P/, bump the knobs, rerun. The orchestrator logic is core-count-agnostic.
- Watch retransmits — they were already high at 8-core; 16-core may saturate harder.
- CX8 parity reference (16C, -P4, ~706 Gbps line rate): see `../../build_exec_v2.py`
  and project memory [[project-cx8-scripts]].

---

## 6. Files in this folder

| File | Purpose |
|------|---------|
| `run_cx7_8p_sweep.py` | 8P orchestrator (8 procs, 8Q, interleaved IRQs, -P sweep) |
| `build_cx7_8p_study.py` | Build standalone 8C Excel (System + 8-Core Study) |
| `cx7_config.py` | Config loader incl. 8P knobs (CORES, SIBLINGS, NUM_CORES) |
| `config.env.example` | Template — copy to `config.env`, set passwords |
| `cx7-8core-xx.md` | This file |
| `results_20260713_144947/` | Raw 8P SDCI-ON run (CSV + 800 JSON) |
| `results/` | 8C Excel output |
