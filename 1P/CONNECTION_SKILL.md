# CX7 Lab Connection Skill — How to Reach & Drive the Boxes

> Reusable connection knowledge for the CX7 core-scaling work. Saved so future
> sessions can resume without re-discovering hosts, creds, driver quirks, or the
> SSH automation method. Prior work was done *directly on the boxes*; remote
> automation from the Windows workstation was established fresh (this file).

---

## 1. Hosts, Credentials, Networks

> **Credentials and IPs are NOT stored in this repo.** They live in `config.env`
> (git-ignored). Copy `config.env.example` → `config.env` and fill in real values.
> All scripts read from it (Python via `cx7_config.py`, shell via `source config.env`).

| Role | Hostname | Data IP | NIC (data) | NIC driver/BDF |
|------|----------|---------|------------|----------------|
| **SUT** | congo-0573-host | 192.168.10.2 | eth2 (CX7) | mlx5_core @ 0000:21:00.0 |
| **LoadGen** | galena-3666-host | 192.168.10.3 | enp1s0np0 | (CX7) |

- Mgmt IPs + ssh user/password → set in `config.env` (`CX7_SUT_*`, `CX7_LG_*`).
- **sudo:** passwordless-via-stdin works — `echo <pw> | sudo -S -p "" <cmd>` → root.
- Mgmt IPs are remote (~277ms RTT). Data link 192.168.10.0/24 is direct SUT↔LoadGen (0.2ms).
- **ICMP note:** the LoadGen mgmt IP does NOT answer ping from the workstation, but
  SSH works fine. The data IP .3 answers ping *from the SUT*. Don't use
  ping-from-workstation as a liveness test.

## 2. Connection Method (from Windows workstation)

- No `sshpass`/`plink`/`expect` on this box. **Use Python + paramiko** (installed):
  `python -m pip install paramiko` (v5.0.0 confirmed working).
- OpenSSH client exists (`/usr/bin/ssh`) but password auth can't be scripted
  without a TTY helper — hence paramiko.
- Reusable driver script: **`run_cx7_sweep.py`** (this folder) — connects to both,
  tunes, runs the sweep, pulls results. Reuse its `connect()`/`run()` helpers.

Minimal snippet (reads creds from config.env via cx7_config):
```python
import paramiko
from cx7_config import SUT           # SUT = dict(host, user, pw) from config.env
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(SUT["host"], username=SUT["user"], password=SUT["pw"], timeout=30)
_, o, _ = c.exec_command("hostname"); print(o.read().decode())
# sudo:  echo <pw> | sudo -S -p "" bash -c "<cmd>"
```

## 3. Critical Driver Quirk — eth2 IRQ discovery

**eth2 IRQs are labeled by PCI BDF, not netdev name.** In `/proc/interrupts`
they appear as `mlx5_comp0@pci:0000:21:00.0` … `mlx5_comp63@...` (64 total) plus
`mlx5_async0@...`. A `grep eth2 /proc/interrupts` matches NOTHING and would
silently steer zero IRQs.

**Correct discovery:**
```bash
BDF=$(ethtool -i eth2 | awk '/bus-info:/{print $2}')     # 0000:21:00.0
grep "$BDF" /proc/interrupts | sed -E 's/^ *([0-9]+):.*/\1/'   # IRQ numbers
```

Also: `/proc/interrupts` has 512 CPU columns → grep dumps are ~110KB. Always
reduce to `IRQ num + label` with sed/awk; never cat the raw counter matrix.

## 4. Affinity: use `smp_affinity_list`, not the hex mask

Target core 261 is past the first 32-bit word. A hand-built hex bitmask lands on
the wrong CPU. Always: `echo 261 > /proc/irq/<n>/smp_affinity_list`.

## 5. Verified Environment Facts (2026-07-10)

- SUT: iperf3, jq, ethtool, taskset all present. eth2 `ethtool -l` max Combined=63,
  Current Combined already =1 (1Q). FW 28.48.1000, mlx5 driver v26.01.
- LoadGen: iperf3 present.
- SMT sibling map (CCD0): `sibling = core + 256` → core 5 ↔ **261**.

## 6. Gotchas learned
- Python stdout is **fully buffered** when run non-interactively (no TTY) — a
  long background run shows no interim output until it flushes/exits. Add
  `python -u` or `flush=True` if live progress is needed.
- Start iperf3 server detached with `nohup ... &` under sudo; verify with
  `pgrep -a -f 'iperf3 -s'`; kill with `pkill -f 'iperf3 -s'` when done.
