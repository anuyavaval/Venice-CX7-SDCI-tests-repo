#!/usr/bin/env python3
"""
CX7 1-Core iPerf core-scaling orchestrator (runs FROM the Windows workstation).

Drives both lab boxes over SSH (paramiko, password auth):
  - Loadgen (galena-3666-host): start iperf3 server on enp1s0np0
  - SUT (congo-0573-host): force 1Q on eth2, steer all eth2 IRQs to core 261
    (SMT sibling of iperf core 5), then sweep -P and collect throughput+retrans.

Results saved locally under results_<timestamp>/ : summary.csv, averages.csv,
and raw per-run JSON.

Usage:  python run_cx7_sweep.py
"""
import paramiko, time, json, statistics, os, sys
from datetime import datetime
from cx7_config import (SUT, LOADGEN, SUT_NIC, LG_NIC, SRV_DATA_IP,
                        IPERF_CORE, IRQ_CORE, BASE_PORT)

# ─── Test knobs (non-secret) ─────────────────────────────────────────────────
DURATION    = 60              # seconds per run
ITERS       = 5
P_LIST      = [1, 2, 4, 8, 12, 16, 20, 24, 28, 32]   # full set
# Hosts/creds/IPs come from cx7_config (config.env / env vars).
# ─────────────────────────────────────────────────────────────────────────────

def connect(cfg):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(cfg["host"], username=cfg["user"], password=cfg["pw"], timeout=30)
    return c

def run(c, cmd, sudo=False, pw=None, timeout=None):
    if sudo:
        pw = pw or SUT["pw"]
        cmd = f'echo {pw} | sudo -S -p "" bash -c {json.dumps(cmd)}'
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    return out.strip(), err.strip()

def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"results_{ts}")
    os.makedirs(outdir, exist_ok=True)
    print(f"Results -> {outdir}\n")

    print("== Connecting ==")
    sut = connect(SUT); print("  SUT:", run(sut, "hostname")[0])
    lg  = connect(LOADGEN); print("  LoadGen:", run(lg, "hostname")[0])

    # ── Loadgen tuning + iperf3 server ──
    print("\n== LoadGen: tuning + starting iperf3 server ==")
    run(lg, "systemctl stop irqbalance || true", sudo=True)
    run(lg, f"ethtool -A {LG_NIC} rx off tx off || true", sudo=True)
    run(lg, "cpupower frequency-set -g performance || true", sudo=True)
    run(lg, "echo 0 > /sys/devices/system/cpu/cpufreq/boost || true", sudo=True)
    run(lg, "pkill -f 'iperf3 -s' || true", sudo=True)
    time.sleep(1)
    # start server detached
    run(lg, f"nohup iperf3 -s -B {SRV_DATA_IP} -p {BASE_PORT} > /tmp/iperf3_srv.log 2>&1 &", sudo=True)
    time.sleep(2)
    chk, _ = run(lg, "pgrep -a -f 'iperf3 -s' | head -2")
    print("  server:", chk or "NOT RUNNING (check /tmp/iperf3_srv.log)")

    # ── SUT tuning: flow control, governor, 1Q, IRQ steer ──
    print("\n== SUT: tuning eth2 ==")
    run(sut, "systemctl stop irqbalance || true", sudo=True)
    run(sut, f"ethtool -A {SUT_NIC} rx off tx off || true", sudo=True)
    run(sut, "cpupower frequency-set -g performance || true", sudo=True)
    run(sut, "echo 0 > /sys/devices/system/cpu/cpufreq/boost || true", sudo=True)

    # Force 1Q combined
    run(sut, f"ethtool -L {SUT_NIC} combined 1 || true", sudo=True)
    ql, _ = run(sut, f"ethtool -l {SUT_NIC} | awk '/Current/{{f=1}} f&&/Combined:/{{print $2; exit}}'")
    print(f"  1Q combined -> Current Combined = {ql}")

    # Steer all eth2 IRQs (matched by BDF) to core 261
    bdf, _ = run(sut, f"ethtool -i {SUT_NIC} | awk '/bus-info:/{{print $2}}'")
    steer = (
        f"BDF={bdf}; n=0; "
        f"for irq in $(grep \"$BDF\" /proc/interrupts | sed -E 's/^ *([0-9]+):.*/\\1/'); do "
        f"echo {IRQ_CORE} > /proc/irq/$irq/smp_affinity_list 2>/dev/null && n=$((n+1)); done; "
        f"echo steered $n IRQs; "
        f"c0=$(grep \"mlx5_comp0@pci:$BDF\" /proc/interrupts | sed -E 's/^ *([0-9]+):.*/\\1/'); "
        f"echo comp0 IRQ $c0 affinity=$(cat /proc/irq/$c0/smp_affinity_list 2>/dev/null)"
    )
    so, _ = run(sut, steer, sudo=True)
    print(f"  BDF {bdf}:", so.replace("\n", " | "))

    # ── Sweep ──
    print(f"\n== Sweep: -P {P_LIST}, {ITERS} iters x {DURATION}s, iperf core {IPERF_CORE} ==")
    summary = [("P", "iter", "gbps", "retransmits")]
    averages = [("P", "avg_gbps", "min_gbps", "max_gbps", "cv_pct", "avg_retransmits")]

    for P in P_LIST:
        print(f"\n########## -P {P} ##########")
        vals, rets = [], []
        for i in range(1, ITERS + 1):
            cmd = (f"taskset -c {IPERF_CORE} iperf3 -c {SRV_DATA_IP} -p {BASE_PORT} "
                   f"-P {P} -t {DURATION} -J")
            out, err = run(sut, cmd, timeout=DURATION + 30)
            gbps, ret = 0.0, 0
            try:
                j = json.loads(out)
                gbps = j["end"]["sum_received"]["bits_per_second"] / 1e9
                ret  = j["end"]["sum_sent"].get("retransmits", 0)
            except Exception:
                print(f"  iter {i}: PARSE FAIL ({err[:80]})")
            # save raw
            with open(os.path.join(outdir, f"P{P}_iter{i}.json"), "w") as f:
                f.write(out)
            print(f"  iter {i}: {gbps:6.2f} Gbps  retrans={ret}")
            summary.append((P, i, f"{gbps:.2f}", ret))
            vals.append(gbps); rets.append(ret)

        avg = statistics.mean(vals); mn = min(vals); mx = max(vals)
        sd  = statistics.pstdev(vals); cv = (sd / avg * 100) if avg else 0
        ravg = statistics.mean(rets)
        print(f">> -P {P:<3} avg={avg:6.2f}  min={mn:6.2f}  max={mx:6.2f}  "
              f"CV={cv:5.2f}%  retrans_avg={ravg:.1f}")
        averages.append((P, f"{avg:.2f}", f"{mn:.2f}", f"{mx:.2f}", f"{cv:.2f}", f"{ravg:.1f}"))

    # write CSVs
    def wcsv(path, rows):
        with open(path, "w") as f:
            for r in rows: f.write(",".join(map(str, r)) + "\n")
    wcsv(os.path.join(outdir, "summary.csv"), summary)
    wcsv(os.path.join(outdir, "averages.csv"), averages)

    # cleanup loadgen server
    run(lg, "pkill -f 'iperf3 -s' || true", sudo=True)

    print("\n==================== SWEEP COMPLETE ====================")
    for r in averages: print("  " + "  ".join(f"{c:>10}" for c in r))
    best = max(averages[1:], key=lambda r: float(r[1]))
    print(f"\nBest -P by avg: -P {best[0]} -> {best[1]} Gbps (CV {best[4]}%)")
    print(f"CSVs: {outdir}")
    sut.close(); lg.close()

if __name__ == "__main__":
    main()
