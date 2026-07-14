#!/usr/bin/env python3
"""
CX7 2-Core (2P) iPerf core-scaling orchestrator — SDCI ENABLED.

Extends the 1P study to 2 cores. Runs FROM the Windows workstation, drives
both lab boxes over SSH (paramiko).

Per the parent-directory scaling convention (core-count is config-driven):
  - NUM_CORES iperf3 client processes, one pinned per core (cores 1..2, skip 0).
  - eth2 forced to combined = NUM_CORES queues (ethtool -L eth2 combined 2).
  - The NIC's 64 IRQs are INTERLEAVED across the SMT sibling cores (257..258)
    using modulo:  sibling = SIBLINGS[irq_index % NUM_CORES].
    With 64 IRQs / 2 cores that is 32 IRQs per sibling (round-robin).
  - Each proc runs the SAME -P value; we sweep -P over the list.
  - 10 iterations per -P, 60 s each. Throughput = SUM of all procs (aggregate),
    and per-core detail is retained.

Results -> results_<timestamp>/ : summary.csv, averages.csv, percore.csv, raw JSON.
"""
import paramiko, time, json, statistics, os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from cx7_config import (SUT, LOADGEN, SUT_NIC, LG_NIC, SRV_DATA_IP,
                        BASE_PORT, CORES, SIBLINGS, NUM_CORES)

# ─── Test knobs ──────────────────────────────────────────────────────────────
DURATION = 60
ITERS    = 10
P_LIST   = [1, 2, 4, 8, 12, 16, 20, 24, 28, 32]
# one iperf3 server per core on the loadgen, ports BASE_PORT .. BASE_PORT+NUM_CORES-1.
PORTS    = [BASE_PORT + i for i in range(NUM_CORES)]
# ─────────────────────────────────────────────────────────────────────────────

def connect(cfg):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(cfg["host"], username=cfg["user"], password=cfg["pw"], timeout=30)
    return c

def run(c, cmd, sudo=False, timeout=None):
    if sudo:
        cmd = f'echo {SUT["pw"]} | sudo -S -p "" bash -c {json.dumps(cmd)}'
    _, o, e = c.exec_command(cmd, timeout=timeout)
    return o.read().decode(errors="replace").strip(), e.read().decode(errors="replace").strip()

def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"results_{ts}")
    os.makedirs(outdir, exist_ok=True)
    print(f"Results -> {outdir}")
    print(f"2P: cores {CORES} | siblings {SIBLINGS} | ports {PORTS}\n")

    print("== Connecting ==")
    sut = connect(SUT); print("  SUT:", run(sut, "hostname")[0])
    lg  = connect(LOADGEN); print("  LoadGen:", run(lg, "hostname")[0])

    # ── LoadGen: tuning + one iperf3 server per core/port ──
    print("\n== LoadGen: tuning + starting iperf3 servers (one per core) ==")
    run(lg, "systemctl stop irqbalance || true", sudo=True)
    run(lg, f"ethtool -A {LG_NIC} rx off tx off || true", sudo=True)
    run(lg, "cpupower frequency-set -g performance || true", sudo=True)
    run(lg, "echo 0 > /sys/devices/system/cpu/cpufreq/boost || true", sudo=True)
    run(lg, "pkill -f 'iperf3 -s' || true", sudo=True); time.sleep(1)
    for i, p in enumerate(PORTS):
        # pin each server to a distinct core too (mirrors client core layout)
        run(lg, f"nohup taskset -c {CORES[i]} iperf3 -s -B {SRV_DATA_IP} -p {p} "
                f"> /tmp/iperf3_srv_{p}.log 2>&1 &", sudo=True)
    time.sleep(2)
    nsrv, _ = run(lg, "pgrep -f 'iperf3 -s' | wc -l")
    print(f"  servers running: {nsrv}/{NUM_CORES}")

    # ── SUT: tuning + combined=NUM_CORES + interleaved IRQ steering ──
    print("\n== SUT: tuning eth2 (NUM_CORES Q, interleaved IRQs) ==")
    run(sut, "systemctl stop irqbalance || true", sudo=True)
    run(sut, f"ethtool -A {SUT_NIC} rx off tx off || true", sudo=True)
    run(sut, "cpupower frequency-set -g performance || true", sudo=True)
    run(sut, "echo 0 > /sys/devices/system/cpu/cpufreq/boost || true", sudo=True)

    # combined = NUM_CORES (2)
    run(sut, f"ethtool -L {SUT_NIC} combined {NUM_CORES} || true", sudo=True)
    ql, _ = run(sut, f"ethtool -l {SUT_NIC} | awk '/Current/{{f=1}} f&&/Combined:/{{print $2; exit}}'")
    print(f"  combined queues -> {ql}")

    # Interleave all eth2 IRQs across the siblings via modulo (IRQ i -> SIB[i % N]).
    # Compute the assignment in Python and issue simple echo writes — multi-statement
    # bash w/ arrays does not survive the Python->JSON->sudo-bash wrapping reliably.
    bdf, _ = run(sut, f"ethtool -i {SUT_NIC} | awk '/bus-info:/{{print $2}}'")
    irq_out, _ = run(sut, f"grep \"{bdf}\" /proc/interrupts | awk -F: '{{print $1}}' | tr -d ' '")
    irqs = irq_out.split()
    pairs = [(irq, SIBLINGS[i % NUM_CORES]) for i, irq in enumerate(irqs)]
    chain = " ; ".join(
        f"echo {sib} > /proc/irq/{irq}/smp_affinity_list" for irq, sib in pairs)
    run(sut, chain, sudo=True)
    print(f"  BDF {bdf}: interleaved {len(irqs)} IRQs across siblings {SIBLINGS}")
    # spot-check first 4 completion IRQs
    chk, _ = run(sut, f"for n in $(seq 0 3); do "
                      f"irq=$(grep \"mlx5_comp$n@pci:{bdf}\" /proc/interrupts | awk -F: '{{print $1}}' | tr -d ' '); "
                      f"[ -n \"$irq\" ] && echo comp$n=$(cat /proc/irq/$irq/smp_affinity_list); done")
    print("  " + chk.replace("\n", " "))

    # ── Persistent per-core SSH connections ──
    # Opening a fresh SSH connection per stream per iteration trips sshd's MaxStartups
    # rate limit. Open ONE connection per core up front (staggered), then reuse them.
    print(f"\n== Opening {NUM_CORES} persistent SSH connections (staggered) ==")
    conns = []
    for i in range(NUM_CORES):
        conns.append(connect(SUT))
        time.sleep(0.3)   # stagger to stay under sshd MaxStartups
    print(f"  {len(conns)} connections up")

    # ── Sweep ──
    print(f"\n== Sweep: -P {P_LIST}, {ITERS} iters x {DURATION}s, {NUM_CORES} procs ==")
    summary  = [("P", "iter", "agg_gbps", "retransmits")]
    percore  = [("P", "iter") + tuple(f"core{c}" for c in CORES)]
    averages = [("P", "avg_agg_gbps", "min", "max", "cv_pct", "avg_retransmits")]

    def one_stream(idx, port, core, P):
        """Run one iperf3 client over a PERSISTENT SSH connection (conns[idx])."""
        try:
            cmd = (f"taskset -c {core} iperf3 -c {SRV_DATA_IP} -p {port} "
                   f"-P {P} -t {DURATION} -J")
            out, _ = run(conns[idx], cmd, timeout=DURATION + 30)
            j = json.loads(out)
            g = j["end"]["sum_received"]["bits_per_second"] / 1e9
            r = j["end"]["sum_sent"].get("retransmits", 0)
            return g, r, out
        except Exception as ex:
            return 0.0, 0, f'{{"error":"{type(ex).__name__}"}}'

    for P in P_LIST:
        print(f"\n########## -P {P} (x{NUM_CORES} cores) ##########")
        agg_list, ret_list = [], []
        for it in range(1, ITERS + 1):
            # launch all procs concurrently over the persistent connections
            with ThreadPoolExecutor(max_workers=NUM_CORES) as ex:
                res = list(ex.map(lambda a: one_stream(*a, P),
                                  [(i, PORTS[i], CORES[i]) for i in range(NUM_CORES)]))
            gbps = [r[0] for r in res]; rets = [r[1] for r in res]
            for i, r in enumerate(res):
                with open(os.path.join(outdir, f"P{P}_iter{it}_core{CORES[i]}.json"), "w") as f:
                    f.write(r[2])
            agg = sum(gbps); tret = sum(rets)
            print(f"  iter {it:2d}: agg={agg:7.2f} Gbps  "
                  f"percore=[{' '.join(f'{g:.1f}' for g in gbps)}]  retrans={tret}")
            summary.append((P, it, f"{agg:.2f}", tret))
            percore.append((P, it) + tuple(f"{g:.2f}" for g in gbps))
            agg_list.append(agg); ret_list.append(tret)

        avg = statistics.mean(agg_list); mn = min(agg_list); mx = max(agg_list)
        cv = (statistics.pstdev(agg_list) / avg * 100) if avg else 0
        ravg = statistics.mean(ret_list)
        print(f">> -P {P:<3} agg_avg={avg:7.2f}  min={mn:7.2f}  max={mx:7.2f}  "
              f"CV={cv:5.2f}%  retrans_avg={ravg:.1f}")
        averages.append((P, f"{avg:.2f}", f"{mn:.2f}", f"{mx:.2f}", f"{cv:.2f}", f"{ravg:.1f}"))

    def wcsv(path, rows):
        with open(path, "w") as f:
            for r in rows: f.write(",".join(map(str, r)) + "\n")
    wcsv(os.path.join(outdir, "summary.csv"), summary)
    wcsv(os.path.join(outdir, "percore.csv"), percore)
    wcsv(os.path.join(outdir, "averages.csv"), averages)

    # Close the persistent per-core connections.
    for cc in conns:
        try: cc.close()
        except Exception: pass

    # CSVs are saved above; cleanup is best-effort (SSH can drop after a long run).
    try:
        run(lg, "pkill -f 'iperf3 -s' || true", sudo=True)
    except Exception as ex:
        print(f"(cleanup skipped: {type(ex).__name__} — data already saved)")

    print("\n==================== 2P SWEEP COMPLETE ====================")
    for r in averages: print("  " + "  ".join(f"{c:>12}" for c in r))
    best = max(averages[1:], key=lambda r: float(r[1]))
    print(f"\nBest -P by agg avg: -P {best[0]} -> {best[1]} Gbps (CV {best[4]}%)")
    print(f"CSVs: {outdir}")
    sut.close(); lg.close()

if __name__ == "__main__":
    main()
