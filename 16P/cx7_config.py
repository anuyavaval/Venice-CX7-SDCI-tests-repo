#!/usr/bin/env python3
"""
Central config loader for the CX7 SDCI test scripts.

Reads lab credentials + IPs from (in priority order):
  1. real environment variables
  2. a local `config.env` file next to this module (git-ignored)

Copy config.env.example -> config.env and fill in your values before running.
NO secrets are committed to git; config.env is in .gitignore.
"""
import os

def _load_env_file():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.split("#", 1)[0]                       # strip inline comment
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env_file()

def _req(name, default=None):
    v = os.environ.get(name, default)
    if v is None:
        raise SystemExit(
            f"Missing config value '{name}'. Copy config.env.example -> config.env "
            f"and fill it in, or export {name} in your environment.")
    return v

# ── Hosts / credentials ──
SUT_HOST  = _req("CX7_SUT_HOST")        # SUT mgmt IP
SUT_USER  = _req("CX7_SUT_USER", "amd")
SUT_PW    = _req("CX7_SUT_PW")
LG_HOST   = _req("CX7_LG_HOST")         # LoadGen mgmt IP
LG_USER   = _req("CX7_LG_USER", "amd")
LG_PW     = _req("CX7_LG_PW")

# ── Data-plane / NIC ──
SUT_NIC     = os.environ.get("CX7_SUT_NIC", "eth2")
LG_NIC      = os.environ.get("CX7_LG_NIC", "enp1s0np0")
SRV_DATA_IP = _req("CX7_SRV_DATA_IP")   # loadgen data IP (iperf3 server bind + SUT target)

# ── Test knobs ──
IPERF_CORE = int(os.environ.get("CX7_IPERF_CORE", "5"))   # first core (1P) / base core (8P)
IRQ_CORE   = int(os.environ.get("CX7_IRQ_CORE", "261"))   # 1P single IRQ core
BASE_PORT  = int(os.environ.get("CX7_BASE_PORT", "5201"))

# ── 8P (multi-core) knobs ──
# NUM_CORES iperf3 processes run on cores BASE_CORE .. BASE_CORE+NUM_CORES-1.
# Each core's IRQs land on its SMT sibling (= core + SIBLING_OFFSET).
# The NIC's 64 IRQs are interleaved across those siblings via  irq_index % NUM_CORES.
BASE_CORE      = int(os.environ.get("CX7_BASE_CORE", str(IPERF_CORE)))  # 5
NUM_CORES      = int(os.environ.get("CX7_NUM_CORES", "8"))              # 8 -> cores 5..12
SIBLING_OFFSET = int(os.environ.get("CX7_SIBLING_OFFSET", "256"))      # sibling = core+256 (CCD0)

CORES    = list(range(BASE_CORE, BASE_CORE + NUM_CORES))          # [5..12]
SIBLINGS = [c + SIBLING_OFFSET for c in CORES]                    # [261..268]

SUT = dict(host=SUT_HOST, user=SUT_USER, pw=SUT_PW)
LOADGEN = dict(host=LG_HOST, user=LG_USER, pw=LG_PW)
