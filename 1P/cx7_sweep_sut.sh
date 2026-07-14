#!/usr/bin/env bash
# ============================================================================
# CX7 eth2 core-scaling sweep  (SUT / client side)
# ----------------------------------------------------------------------------
# iperf pinned to CORE 5, NIC (eth2) IRQs steered to its SMT sibling CORE 261.
# Sweeps -P = 1 2 4 8 12 16 20, runs each 5x, reports avg throughput + retries.
# Loadgen runs iperf3 servers on enp1s0np0 (see cx7_sweep_loadgen.sh).
# ============================================================================
set -uo pipefail

# ─── Config ─────────────────────────────────────────────────────────────────
# Load non-secret defaults from config.env if present (same dir), else use
# the values below. Override any of these via environment variables.
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$_here/config.env" ]] && source "$_here/config.env"

NIC="${CX7_SUT_NIC:-eth2}"                 # SUT NIC under test (local IP 192.168.10.2)
SRV_IP="${CX7_SRV_DATA_IP:-192.168.10.3}"  # loadgen data IP (iperf3 server)
IPERF_CORE="${CX7_IPERF_CORE:-5}"          # core running iperf client
IRQ_CORE="${CX7_IRQ_CORE:-261}"            # SMT sibling of core 5 (from topology)
BASE_PORT="${CX7_BASE_PORT:-5201}"         # loadgen server base port
DURATION=60                        # seconds per iperf run
ITERS=5                            # repetitions per -P value
P_LIST=(1 2 4 8 12 16 20 24 28 32)   # -P sweep
OUTDIR="cx7_sweep_$(date +%Y%m%d_%H%M%S)"
# ────────────────────────────────────────────────────────────────────────────

command -v iperf3 >/dev/null || { echo "iperf3 not found"; exit 1; }
command -v jq >/dev/null    || { echo "jq not found (needed for JSON parse)"; exit 1; }
[[ $EUID -eq 0 ]] || { echo "run as root (IRQ affinity + tuning need it)"; exit 1; }

mkdir -p "$OUTDIR"
SUMMARY="$OUTDIR/summary.csv"
echo "P,iter,gbps,retransmits" > "$SUMMARY"
AVGCSV="$OUTDIR/averages.csv"
echo "P,avg_gbps,min_gbps,max_gbps,cv_pct,avg_retransmits" > "$AVGCSV"

# ─── NIC + IRQ tuning ───────────────────────────────────────────────────────
echo "== Tuning $NIC =="
systemctl stop irqbalance 2>/dev/null || true
ethtool -A "$NIC" rx off tx off 2>/dev/null || true
cpupower frequency-set -g performance >/dev/null 2>&1 || true
echo 0 > /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || true

# Force 1 queue (1Q combined) — this is the 1-core test.
echo "== Forcing $NIC to 1Q combined =="
ethtool -L "$NIC" combined 1 2>/dev/null || echo "WARN: could not set combined 1 on $NIC"
echo "  combined queues now: $(ethtool -l "$NIC" 2>/dev/null | awk '/Current/{f=1} f&&/Combined:/{print $2; exit}')"

# Steer ALL of this NIC's IRQs to core 261 (SMT sibling of iperf core 5).
# Mellanox mlx5 labels IRQs by PCI BDF (mlx5_comp*@pci:0000:21:00.0), NOT by
# netdev name — so match on the BDF from ethtool -i, not "$NIC".
BDF=$(ethtool -i "$NIC" 2>/dev/null | awk '/bus-info:/{print $2}')
echo "== Steering all $NIC (BDF $BDF) IRQs -> core $IRQ_CORE (sibling of core $IPERF_CORE) =="
if [[ -z "$BDF" ]]; then
  echo "WARN: could not resolve BDF for $NIC — IRQs NOT steered"
else
  IRQS=$(grep "$BDF" /proc/interrupts | sed -E 's/^ *([0-9]+):.*/\1/')
  if [[ -z "$IRQS" ]]; then
    echo "WARN: no IRQs matched BDF '$BDF' in /proc/interrupts — IRQs NOT steered"
  else
    n=0
    for irq in $IRQS; do
      echo "$IRQ_CORE" > "/proc/irq/$irq/smp_affinity_list" 2>/dev/null && n=$((n+1))
    done
    echo "  steered $n IRQ(s) -> core $IRQ_CORE"
    # spot-check the active completion queue (comp0)
    c0=$(grep "mlx5_comp0@pci:$BDF" /proc/interrupts | sed -E 's/^ *([0-9]+):.*/\1/')
    [[ -n "$c0" ]] && echo "  comp0 IRQ $c0 affinity now: $(cat /proc/irq/$c0/smp_affinity_list 2>/dev/null)"
  fi
fi

# ─── Sweep ──────────────────────────────────────────────────────────────────
for P in "${P_LIST[@]}"; do
  echo ""
  echo "########## -P $P ##########"
  vals=(); rets=()
  for i in $(seq 1 "$ITERS"); do
    JSON="$OUTDIR/P${P}_iter${i}.json"
    # single iperf3 client process pinned to core 5; -P = parallel streams
    taskset -c "$IPERF_CORE" iperf3 -c "$SRV_IP" -p "$BASE_PORT" \
        -P "$P" -t "$DURATION" -J > "$JSON" 2>/dev/null

    gbps=$(jq -r '.end.sum_received.bits_per_second / 1e9' "$JSON" 2>/dev/null)
    ret=$(jq -r '.end.sum_sent.retransmits // 0' "$JSON" 2>/dev/null)
    [[ "$gbps" == "null" || -z "$gbps" ]] && gbps=0
    [[ "$ret"  == "null" || -z "$ret"  ]] && ret=0

    printf "  iter %d: %6.2f Gbps  retrans=%s\n" "$i" "$gbps" "$ret"
    echo "$P,$i,$gbps,$ret" >> "$SUMMARY"
    vals+=("$gbps"); rets+=("$ret")
  done

  # avg / min / max / CV / avg retransmits
  read -r avg mn mx cv <<<"$(printf '%s\n' "${vals[@]}" | awk '
    {s+=$1; ss+=$1*$1; if(NR==1||$1<mn)mn=$1; if(NR==1||$1>mx)mx=$1; n++}
    END{m=s/n; sd=sqrt(ss/n-m*m); cv=(m>0)?sd/m*100:0;
        printf "%.2f %.2f %.2f %.2f", m, mn, mx, cv}')"
  ravg=$(printf '%s\n' "${rets[@]}" | awk '{s+=$1;n++} END{printf "%.1f", (n?s/n:0)}')
  printf ">> -P %-3s avg=%6.2f  min=%6.2f  max=%6.2f  CV=%5.2f%%  retrans_avg=%s\n" \
         "$P" "$avg" "$mn" "$mx" "$cv" "$ravg"
  echo "$P,$avg,$mn,$mx,$cv,$ravg" >> "$AVGCSV"
done

echo ""
echo "==================== SWEEP COMPLETE ===================="
column -t -s, "$AVGCSV"
echo ""
echo "Best -P by avg throughput:"
tail -n +2 "$AVGCSV" | sort -t, -k2 -nr | head -1 | \
  awk -F, '{printf "  -P %s  ->  %.2f Gbps  (CV %.2f%%)\n",$1,$2,$5}'
echo "Raw + per-iter JSON in: $OUTDIR/"
