#!/usr/bin/env bash
# ============================================================================
# CX7 core-scaling sweep  (LOADGEN / server side)
# ----------------------------------------------------------------------------
# Run on the loadgen box. Starts an iperf3 server bound to enp1s0np0 so the
# SUT client (cx7_sweep_sut.sh) can connect. One server handles all -P streams.
# ============================================================================
set -uo pipefail

# ─── Config ─────────────────────────────────────────────────────────────────
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$_here/config.env" ]] && source "$_here/config.env"

NIC="${CX7_LG_NIC:-enp1s0np0}"             # loadgen NIC
BIND_IP="${CX7_SRV_DATA_IP:-192.168.10.3}" # enp1s0np0 IP (== SRV_IP on SUT)
BASE_PORT="${CX7_BASE_PORT:-5201}"
SRV_CORE="${CX7_IPERF_CORE:-5}"            # core to pin the server to (optional)
# ────────────────────────────────────────────────────────────────────────────

command -v iperf3 >/dev/null || { echo "iperf3 not found"; exit 1; }
[[ $EUID -eq 0 ]] || echo "note: not root — NIC tuning skipped"

if [[ $EUID -eq 0 ]]; then
  systemctl stop irqbalance 2>/dev/null || true
  ethtool -A "$NIC" rx off tx off 2>/dev/null || true
  cpupower frequency-set -g performance >/dev/null 2>&1 || true
  echo 0 > /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || true
fi

echo "Starting iperf3 server on $BIND_IP:$BASE_PORT (Ctrl-C to stop)"
# -s server, -1 would exit after one test; omit so it serves the whole sweep
exec taskset -c "$SRV_CORE" iperf3 -s -B "$BIND_IP" -p "$BASE_PORT"
