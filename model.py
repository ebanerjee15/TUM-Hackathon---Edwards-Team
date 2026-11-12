"""
model.py: physics and energy model for the hBN shared-pumping demonstrator.
Implements Sections 3-5 of the Final Solution 1 hand-off document.

Concept demonstration only: synthetic hackathon data plus explicit assumptions.
Not an industrial engineering design or a safety system.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- constants
R = 8.314                     # J/(mol·K)                       PHYSICS
P_ATM = 101325.0              # Pa                              PHYSICS
T_STD = 273.15                # K, standard conditions for slm  PHYSICS
SLM_TO_MOLS = P_ATM * 1e-3 / (R * T_STD * 60)                   # mol/s per slm


@dataclass
class Params:
    """Every number the model uses, with its source (doc Section 3)."""
    T_gas: float = 300.0          # K           ASSUMPTION: line-gas temperature
    P_set_mbar: float = 30.0      # mbar        LITERATURE: hBN MOCVD process pressure
    C_tool: float = 0.10          # m3/s        ASSUMPTION: foreline conductance per reactor
    C_header: float = 0.50        # m3/s        ASSUMPTION: header conductance per cluster (1800 m3/h)
    rated_slm: float = 600.0      # slm         DATA: PMP-04 rated flow
    S_600: float | None = None    # m3/s        DERIVED: 600 slm at 30 mbar (set in __post_init__)
    margin_normal: float = 1.5    # -           DESIGN RULE: C03 capacity margin
    margin_failed: float = 1.0    # -           DESIGN RULE: one-pump-failed check
    grid_kg_per_kwh: float = 0.12 # kg CO2e/kWh DATA: Utility_Data (illustrative)
    hours_per_year: float = 8760  # h           ASSUMPTION: continuous operation
    seed: int = 42                # -           ASSUMPTION: time-shift of tool profiles
    n_tools: int = 10
    tools_per_cluster: int = 5
    pumps_per_cluster: int = 2

    def __post_init__(self):
        if self.S_600 is None:    # convert 600 standard L/min to actual m3/s at 30 mbar, 300 K
            self.S_600 = throughput(self.rated_slm, self.T_gas) / (self.P_set_mbar * 100)


# ---------------------------------------------------------------- unit helpers
def throughput(slm, T_gas=300.0):
    """Gas throughput Q in Pa·m3/s for a standard flow in slm (doc Section 4)."""
    return np.asarray(slm, float) * SLM_TO_MOLS * R * T_gas


def m3h(s_m3_per_s):
    return s_m3_per_s * 3600


# ---------------------------------------------------------------- data
def load_data(path):
    """Read the two sheets the demonstrator needs from the hackathon workbook."""
    xls = pd.ExcelFile(path)
    vp = pd.read_excel(xls, "Vacuum_Performance")
    fpd = pd.read_excel(xls, "Fab_Process_Data")
    profiles = [fpd[fpd["Tool_ID"] == t].sort_values("Timestamp")["Required_Exhaust_Flow_slm"].to_numpy(float)
                for t in ("T05", "T06")]
    return vp, profiles


def fit_pump_model(vp):
    """P_kW = c0 + c1·Rated + c2·Flow + c3·Flow²/Rated, fitted to all 28 pump points (DATA)."""
    flow = vp["Load_pct"] / 100 * vp["Rated_Flow_slm"]
    X = np.column_stack([np.ones(len(vp)), vp["Rated_Flow_slm"], flow, flow ** 2 / vp["Rated_Flow_slm"]])
    y = vp["Electricity_kWh_per_h"].to_numpy(float)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    r2 = 1 - ((y - X @ coef) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return coef, float(r2)


def pump_kw(coef, flow_slm, rated_slm=600.0):
    """Electricity of one running pump. Extrapolated below 10 % load (conservative convention, doc Section 5)."""
    f = np.asarray(flow_slm, float)
    return coef[0] + coef[1] * rated_slm + coef[2] * f + coef[3] * f ** 2 / rated_slm


def make_line(profiles, n_tools=10, seed=42):
    """n_tools reactor exhaust curves: alternating T05/T06 profiles, each randomly time-shifted.
    Each curve is a proxy for ONE whole hBN reactor's exhaust (no double counting)."""
    rng = np.random.default_rng(seed)
    H = min(len(p) for p in profiles)
    return np.array([np.roll(profiles[i % 2][:H], rng.integers(0, H)) for i in range(n_tools)])


def clusters(p: Params):
    """Tool indices per cluster, e.g. [[0..4], [5..9]]."""
    return [list(range(i, min(i + p.tools_per_cluster, p.n_tools))) for i in range(0, p.n_tools, p.tools_per_cluster)]


# ---------------------------------------------------------------- vacuum physics (doc Section 4)
def header_max_mbar(q_tool_slm, p: Params):
    """Highest header pressure at which a reactor with flow q can still reach P_set (throttle fully open)."""
    return (p.P_set_mbar * 100 - throughput(q_tool_slm, p.T_gas) / p.C_tool) / 100


def s_eff_header(n_running, p: Params):
    """Effective speed at the header: running pumps in parallel, in series with header conductance."""
    if n_running <= 0:
        return 0.0
    S = n_running * p.S_600
    return S * p.C_header / (S + p.C_header)


def header_pressure_mbar(q_total_slm, n_running, p: Params):
    """Steady-state header pressure P = Q / S_eff (inf if no pump running)."""
    S = s_eff_header(n_running, p)
    return np.inf if S == 0 else float(throughput(q_total_slm, p.T_gas) / S / 100)


def throttle_fraction(q_tool_slm, P_header_mbar, p: Params):
    """Throttle opening needed to hold P_set: C_required / C_tool. >1 or header >= P_set means infeasible."""
    dP = (p.P_set_mbar - P_header_mbar) * 100
    if dP <= 0:
        return np.inf
    return float(throughput(q_tool_slm, p.T_gas) / dP / p.C_tool)


def design_check(peak_tool_slm, peak_cluster_slm, n_running, margin, p: Params):
    """Required vs provided effective speed at the header for a given design flow."""
    P_max = header_max_mbar(peak_tool_slm, p) * 100
    S_req = throughput(margin * peak_cluster_slm, p.T_gas) / P_max if P_max > 0 else np.inf
    S_prov = s_eff_header(n_running, p)
    return dict(P_max_mbar=P_max / 100, S_required_m3h=m3h(S_req), S_provided_m3h=m3h(S_prov),
                headroom_pct=100 * (S_prov / S_req - 1) if np.isfinite(S_req) else -100.0,
                passes=bool(S_prov >= S_req))


# ---------------------------------------------------------------- energy (doc Section 5)
def energy_summary(line, coef, p: Params):
    """Baseline (one pump per reactor) vs proposed (clusters with load-sharing pumps), same 720 h input."""
    baseline_kw = float(np.mean(pump_kw(coef, line, p.rated_slm).sum(axis=0)))
    proposed_kw = 0.0
    for idx in clusters(p):
        q = line[idx].sum(axis=0)
        proposed_kw += float(np.mean(p.pumps_per_cluster * pump_kw(coef, q / p.pumps_per_cluster, p.rated_slm)))
    saved_mwh = (baseline_kw - proposed_kw) * p.hours_per_year / 1000
    return dict(baseline_kw=baseline_kw, proposed_kw=proposed_kw,
                saving_pct=100 * (1 - proposed_kw / baseline_kw),
                saved_mwh_per_year=saved_mwh, saved_tco2e_per_year=saved_mwh * p.grid_kg_per_kwh)
