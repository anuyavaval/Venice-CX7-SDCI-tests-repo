# Venice CX7 SDCI iPerf Tests

Single-core (1C) iPerf3 core-scaling study on **AMD Venice B0** with a
**ConnectX-7 (400G)** NIC, comparing **SDCI OFF vs SDCI ENABLED**. Built to be
resumable and to expand to 8-core / 16-core later.

## TL;DR result (1-core)

| Metric | SDCI OFF | SDCI ENABLED |
|--------|----------|--------------|
| Peak throughput | 89.26 Gbps (at -P 32) | **110.67 Gbps (at -P 4)** |
| Sustained plateau | ~86–89 Gbps | **~107 Gbps** (P8–P32) |
| Single-core uplift | — | **~+20 Gbps / +21%** |

SDCI lifts the single-core ceiling and reaches it with far fewer streams.
Full data + system config: `results/CX7-1C-study-VeniceB0-G2-BIOS.xlsx`.

---

## Quick start (after `git clone`)

```bash
# 1. Python deps (workstation that drives the boxes over SSH)
pip install paramiko openpyxl

# 2. Set up credentials (NOT in git)
cp config.env.example config.env
#   edit config.env: set CX7_SUT_PW, CX7_LG_PW, and confirm IPs/NIC names

# 3. Run the full 1-core sweep (drives both boxes over SSH from the workstation)
python run_cx7_sweep.py           # -P 1..32, 5 iters x 60s -> results_<timestamp>/

# 4. Rebuild the Excel study from result dirs
python build_cx7_study.py         # -> results/CX7-1C-study-VeniceB0-G2-BIOS.xlsx
```

Alternatively run the shell scripts **directly on the lab boxes**:
`cx7_sweep_loadgen.sh` on the loadgen (first), then `cx7_sweep_sut.sh` on the SUT.

---

## Files

| File | Purpose |
|------|---------|
| `run_cx7_sweep.py` | **Main orchestrator** — SSHes to both boxes, tunes, runs full -P sweep, writes CSV + raw JSON |
| `append_cx7_sweep.py` | Append extra -P points to an existing result dir |
| `build_cx7_study.py` | Build the Excel study (System tab + SDCI off/on/delta tables) |
| `cx7_config.py` | Central config loader (reads `config.env` / env vars) |
| `config.env.example` | Template — copy to `config.env` and fill in secrets |
| `cx7_sweep_sut.sh` | Standalone SUT-side runner (run on the box) |
| `cx7_sweep_loadgen.sh` | Standalone loadgen iperf3 server (run on the box) |
| `README.md` | This file |
| `CONNECTION_SKILL.md` | How to reach/drive the boxes; mlx5 IRQ-by-BDF quirk; gotchas |
| `cx7-1core-xx.md` | 1-core test definition + scale-up plan (8C/16C) |
| `results/` | Final Excel study output |
| `results_20260710_142856/` | Raw SDCI-**OFF** run (CSV + per-iter JSON) |
| `results_20260710_190626/` | Raw SDCI-**ON** run (CSV + per-iter JSON) |

## Test configuration (both runs identical except SDCI)

- **NIC:** eth2 = ConnectX-7, 400G, PCIe Gen5 x16, FW 28.48.1000, driver mlx5_core
- **Queues:** 1Q combined (`ethtool -L eth2 combined 1`)
- **Pinning:** iperf3 client on **core 5**; all eth2 IRQs → **core 261** (SMT sibling)
- **iperf3:** single process, `-P` = parallel TCP streams, 60 s × 5 iters
- **Tuning:** irqbalance off, flow-control off, governor=performance, boost off, cclk 2500 MHz
- **BIOS:** G2 (PCOV207040_G2N), Venice B0, `DF EnSrcDnCnRply=0x1`

## Security

`config.env` (real credentials) is **git-ignored** and never committed. Only
`config.env.example` (placeholders) is in the repo. See `.gitignore`.
