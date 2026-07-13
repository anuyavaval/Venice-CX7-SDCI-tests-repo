# CX7 1-Core iPerf Core-Scaling — Resume Guide

> Single-core iPerf core-scaling on ConnectX-7 (CX7), eth2.
> **1-core (1C) baseline.** Expandable to 8C / 16C later (see §5).
>
> Shared tuning recipe, CPU sibling map, `EnSrcDnCnRply` gotcha, and CX8
> reference results are NOT repeated here — they live in the existing
> project memory / CX8 skills (`../project_cx8_scripts.md`, `../nic=eth2.txt`,
> `../build_exec_v2.py`). This file only holds what's specific to CX7 1-core.

---

## 1. Test Definition (1 Core)

| Item | Value |
|------|-------|
| NIC (SUT) | **eth2** (CX7), IP **192.168.10.2** |
| Loadgen NIC | **enp1s0np0**, IP **192.168.10.3** |
| iperf tool | **iperf3** — single process, single core; `-P` = parallel streams |
| iperf pinned to | **core 5** |
| eth2 IRQs → | **core 261** (all eth2 IRQs to sibling 261) |
| Queue | **1Q combined** (already done) |
| `-P` sweep | **1, 2, 4, 8, 12, 16, 20** |
| Iterations | **5 per -P** → avg / min / max / CV% / avg retransmits |
| Duration | 30 s/run |
| Goal | Best `-P` config for max single-core throughput |

**iperf3, not iperf2:** iperf3 keeps all `-P` streams in one process on one
core (correct for a 1-core pin). Do not switch to iperf2.

---

## 2. How to Run

```bash
# Loadgen (192.168.10.3) — first:
sudo ./cx7_sweep_loadgen.sh      # iperf3 -s on enp1s0np0

# SUT (192.168.10.2) — then:
sudo ./cx7_sweep_sut.sh
```

Output → `cx7_sweep_<timestamp>/`: `summary.csv` (per-iter),
`averages.csv` (per-P stats), `P<n>_iter<i>.json` (raw). Best `-P` printed at end.

---

## 3. Files here

| File | Purpose |
|------|---------|
| `cx7_sweep_sut.sh` | Pin core 5, steer eth2 IRQ→261, sweep -P, 5 iters, CSV |
| `cx7_sweep_loadgen.sh` | iperf3 server on enp1s0np0 |
| `cx7-1core-xx.md` | This file |

---

## 4. Confirm on the box before running
- [ ] eth2 IRQ names in `/proc/interrupts` (Mellanox often `mlx5_comp*`, not `eth2`).
      If grep matches nothing, set `NIC` grep pattern to the mlx5 device / PCI BDF.
- [ ] eth2=192.168.10.2, enp1s0np0=192.168.10.3, link up, ping OK.
- [ ] `iperf3` + `jq` on SUT.
- [ ] Record BIOS/tweakfile + SDCI state per run.

---

## 5. Scaling Up (future 8C / 16C)

Generalize pinning — replace `taskset -c 5` with a core range, steer each IRQ
to its own sibling (1:1) instead of all-to-261:

| Test | iperf cores | IRQ siblings |
|------|-------------|--------------|
| 1C (now) | 5 | 261 |
| 8C | 0–7 | 256–263 |
| 16C | 0–15 | 256–271 |

Sibling rule (CCD0): `sibling = core + 256`. CX8 best-config parity + SDCI
on/off comparison method: see `../project_cx8_scripts.md` / `../build_exec_v2.py`.
