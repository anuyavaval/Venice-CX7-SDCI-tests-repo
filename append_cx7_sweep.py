#!/usr/bin/env python3
"""
Append additional -P points to an EXISTING CX7 sweep result dir.
Reuses the same setup (1Q, IRQ->261, core 5, 60s x 5). Same helpers as
run_cx7_sweep.py, but only runs P_APPEND and appends to summary.csv +
averages.csv (raw JSON dropped in the same dir).

Usage:  python append_cx7_sweep.py
"""
import paramiko, time, json, statistics, os, csv
from cx7_config import (SUT, LOADGEN, SUT_NIC, LG_NIC, SRV_DATA_IP,
                        IPERF_CORE, IRQ_CORE, BASE_PORT)

# ─── Test knobs (must match the original run) ────────────────────────────────
DURATION, ITERS = 60, 5
RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "results_20260710_142856")   # existing dir to append to
P_APPEND   = [24, 28, 32]
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
    return o.read().decode(errors="replace").strip(), e.read().decode(errors="replace").strip()

def existing_ps(path):
    if not os.path.exists(path): return set()
    with open(path) as f:
        return {row[0] for row in csv.reader(f) if row and row[0].isdigit()}

def main():
    assert os.path.isdir(RESULT_DIR), f"missing {RESULT_DIR}"
    sumcsv = os.path.join(RESULT_DIR, "summary.csv")
    avgcsv = os.path.join(RESULT_DIR, "averages.csv")

    already = existing_ps(avgcsv)
    todo = [p for p in P_APPEND if str(p) not in already]
    if not todo:
        print("All requested -P already present:", P_APPEND); return
    print(f"Appending -P {todo} to {RESULT_DIR} (existing: {sorted(already, key=int)})")

    sut = connect(SUT); lg = connect(LOADGEN)
    print("SUT:", run(sut, "hostname")[0], "| LoadGen:", run(lg, "hostname")[0])

    # LoadGen server
    run(lg, "systemctl stop irqbalance || true", sudo=True)
    run(lg, f"ethtool -A {LG_NIC} rx off tx off || true", sudo=True)
    run(lg, "cpupower frequency-set -g performance || true", sudo=True)
    run(lg, "pkill -f 'iperf3 -s' || true", sudo=True); time.sleep(1)
    run(lg, f"nohup iperf3 -s -B {SRV_DATA_IP} -p {BASE_PORT} > /tmp/iperf3_srv.log 2>&1 &", sudo=True)
    time.sleep(2)
    print("server:", run(lg, "pgrep -a -f 'iperf3 -s' | head -1")[0] or "NOT RUNNING")

    # SUT tuning + 1Q + IRQ steer
    run(sut, "systemctl stop irqbalance || true", sudo=True)
    run(sut, f"ethtool -A {SUT_NIC} rx off tx off || true", sudo=True)
    run(sut, "cpupower frequency-set -g performance || true", sudo=True)
    run(sut, f"ethtool -L {SUT_NIC} combined 1 || true", sudo=True)
    ql, _ = run(sut, f"ethtool -l {SUT_NIC} | awk '/Current/{{f=1}} f&&/Combined:/{{print $2; exit}}'")
    bdf, _ = run(sut, f"ethtool -i {SUT_NIC} | awk '/bus-info:/{{print $2}}'")
    steer = (f"BDF={bdf}; n=0; for irq in $(grep \"$BDF\" /proc/interrupts | "
             f"sed -E 's/^ *([0-9]+):.*/\\1/'); do echo {IRQ_CORE} > "
             f"/proc/irq/$irq/smp_affinity_list 2>/dev/null && n=$((n+1)); done; echo steered $n IRQs")
    so, _ = run(sut, steer, sudo=True)
    print(f"1Q Combined={ql} | {so}")

    new_summary, new_avg = [], []
    for P in todo:
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
            with open(os.path.join(RESULT_DIR, f"P{P}_iter{i}.json"), "w") as f:
                f.write(out)
            print(f"  iter {i}: {gbps:6.2f} Gbps  retrans={ret}")
            new_summary.append((P, i, f"{gbps:.2f}", ret)); vals.append(gbps); rets.append(ret)
        avg = statistics.mean(vals); mn = min(vals); mx = max(vals)
        cv = (statistics.pstdev(vals) / avg * 100) if avg else 0
        ravg = statistics.mean(rets)
        print(f">> -P {P:<3} avg={avg:6.2f} min={mn:6.2f} max={mx:6.2f} CV={cv:5.2f}% retrans_avg={ravg:.1f}")
        new_avg.append((P, f"{avg:.2f}", f"{mn:.2f}", f"{mx:.2f}", f"{cv:.2f}", f"{ravg:.1f}"))

    # append (files already have headers)
    with open(sumcsv, "a", newline="") as f:
        for r in new_summary: f.write(",".join(map(str, r)) + "\n")
    with open(avgcsv, "a", newline="") as f:
        for r in new_avg: f.write(",".join(map(str, r)) + "\n")

    run(lg, "pkill -f 'iperf3 -s' || true", sudo=True)
    print("\n==================== APPEND COMPLETE ====================")
    # reprint full sorted averages
    with open(avgcsv) as f:
        rows = [r for r in csv.reader(f) if r]
    hdr, data = rows[0], sorted(rows[1:], key=lambda r: int(r[0]))
    print("  " + "  ".join(f"{c:>10}" for c in hdr))
    for r in data: print("  " + "  ".join(f"{c:>10}" for c in r))
    best = max(data, key=lambda r: float(r[1]))
    print(f"\nBest -P by avg: -P {best[0]} -> {best[1]} Gbps (CV {best[4]}%)")
    sut.close(); lg.close()

if __name__ == "__main__":
    main()
