"""
controller.py: supervisory logic for the hBN shared-pumping demonstrator (doc Sections 2A, 2B, 6C, 6D).

Concept demonstration only. NOT safety-rated plant code: real interlocks live in independent,
qualified hardware/PLC logic. All recipes are synthetic placeholders, all signals are simulated.
"""
import copy
from datetime import datetime

import numpy as np

import model as m

# Synthetic recipe registry (local, pre-approved by fab EHS/process engineers in a real plant)
RECIPES = {"hBN-A": "GRP-hBN-A",     # approved recipe -> its compatibility group
           "TEST-B": None}           # unapproved: no compatibility group

PUMPS = {"A": ["A1", "A2"], "B": ["B1", "B2"]}
GREEN, AMBER, RED = "OK", "WARN", "ALARM"


# ---------------------------------------------------------------- state
def initial_state(p: m.Params):
    """Nominal plant: all pumps running, every reactor on approved hBN-A, all wired signals healthy."""
    reactors = []
    for c, idx in zip("AB", m.clusters(p)):
        for i in idx:
            reactors.append(dict(id=f"R{i + 1}", index=i, cluster=c, recipe="hBN-A", sensor_ok=True))
    return dict(
        reactors=reactors,
        pumps={pid: "RUNNING" for c in "AB" for pid in PUMPS[c]},
        header_blocked={"A": False, "B": False},
        header_sensor_ok={"A": True, "B": True},
        flow_multiplier={"A": 1.0, "B": 1.0},
        approved_group={"A": "GRP-hBN-A", "B": "GRP-hBN-A"},
        abatement_ready={"A": True, "B": True},
        log=[],
    )


def _log(state, level, cluster, event, action):
    state["log"].insert(0, dict(time=datetime.now().strftime("%H:%M:%S"), level=level,
                                cluster=cluster, event=event, action=action))


# ---------------------------------------------------------------- buttons (each returns a NEW state)
def reset(p):
    s = initial_state(p)
    _log(s, GREEN, "ALL", "Reset to nominal", "All pumps running, hBN-A approvals restored, alarms cleared")
    return s


def fail_pump(state, pump_id):
    s = copy.deepcopy(state)
    s["pumps"][pump_id] = "FAILED"
    _log(s, AMBER, pump_id[0], f"PUMP FAILURE: {pump_id}",
         f"{pump_id} isolated; remaining pump(s) in cluster {pump_id[0]} take the flow (if capacity allows)")
    return s


def block_header(state, cluster):
    s = copy.deepcopy(state)
    s["header_blocked"][cluster] = True
    _log(s, RED, cluster, f"HEADER {cluster} BLOCKED",
         f"Stop new precursor dosing in cluster {cluster}; approved emergency purge/vent/abatement path REQUIRED")
    return s


def double_flow(state, cluster):
    s = copy.deepcopy(state)
    s["flow_multiplier"][cluster] = 2.0
    _log(s, AMBER, cluster, f"Exhaust flow ×2 in cluster {cluster}", "Capacity re-checked against design peak")
    return s


def set_recipe(state, reactor_id, recipe):
    s = copy.deepcopy(state)
    r = next(r for r in s["reactors"] if r["id"] == reactor_id)
    r["recipe"] = recipe
    approved = RECIPES.get(recipe) == s["approved_group"][r["cluster"]]
    if approved:
        _log(s, GREEN, r["cluster"], f"{reactor_id} requalified on {recipe}", "Operator acknowledged; shared operation allowed")
    else:
        _log(s, RED, r["cluster"], f"CHEMISTRY NOT QUALIFIED: {reactor_id} requested {recipe}",
             f"{reactor_id} DENIED on shared header {r['cluster']}; no mixing, no route-around; "
             "qualified safe exhaust + requalification required before restart")
    return s


def lose_header_sensor(state, cluster):
    s = copy.deepcopy(state)
    s["header_sensor_ok"][cluster] = False
    _log(s, RED, cluster, f"SENSOR / DATA QUALITY FAULT: header {cluster} pressure signal lost",
         "Reading marked INVALID (no stale value used); conservative safe-handling STOP of new processing")
    return s


# ---------------------------------------------------------------- evaluation (pure: never changes state)
def evaluate(state, line, coef, p: m.Params, hour):
    """Apply the gates and the physics for one snapshot hour. Returns per-cluster and per-reactor results."""
    out = {"clusters": {}, "reactors": {}, "alarms": []}
    for c, idx in zip("AB", m.clusters(p)):
        reactors = [r for r in state["reactors"] if r["cluster"] == c]
        mult = state["flow_multiplier"][c]
        pumps_running = [pid for pid in PUMPS[c] if state["pumps"][pid] == "RUNNING"]
        n_run, n_inst = len(pumps_running), len(PUMPS[c])

        # Gate C: chemistry permit per reactor (simulated eligibility, NOT chemistry prediction)
        denied = [r for r in reactors if RECIPES.get(r["recipe"]) != state["approved_group"][c]]
        allowed = [r for r in reactors if r not in denied]

        # Design basis: coincident peak of the reactors on the header
        peak_tool = float(line[[r["index"] for r in allowed]].max() * mult) if allowed else 0.0
        peak_cluster = float(line[[r["index"] for r in allowed]].max(axis=1).sum() * mult) if allowed else 0.0
        margin = p.margin_normal if n_run == n_inst else p.margin_failed
        design = m.design_check(peak_tool, peak_cluster, n_run, margin, p) if allowed else None

        flows = {r["id"]: float(line[r["index"], hour] * mult) for r in allowed}
        q_total = sum(flows.values())

        # Decide the cluster mode, most severe first
        status, level, reason = "RUNNING", GREEN, "All checks pass"
        P_h = None
        if state["header_blocked"][c]:
            status, level, reason = "STOP / ISOLATE", RED, "Header blocked: emergency exhaust path required (not provided by this GUI)"
        elif not state["header_sensor_ok"][c]:
            status, level, reason = "SAFE-HANDLING STOP", RED, "Header pressure signal INVALID: regulation cannot be verified"
        elif not state["abatement_ready"][c]:
            status, level, reason = "STOP", RED, "Abatement not ready: no untreated bypass allowed"
        elif n_run == 0:
            status, level, reason = "STOP", RED, "No pump running"
        else:
            P_h = m.header_pressure_mbar(q_total, n_run, p)
            fracs = {rid: m.throttle_fraction(q, P_h, p) for rid, q in flows.items()}
            current_ok = all(f <= 1.0 for f in fracs.values())
            if not current_ok:
                status, level, reason = "CAPACITY ALARM → SAFE STOP", RED, "Reactors cannot hold 30 mbar now"
            elif design is not None and not design["passes"]:
                status, level, reason = "DESIGN CAPACITY EXCEEDED", RED, \
                    f"Coincident peak needs {design['S_required_m3h']:.0f} m³/h, provided {design['S_provided_m3h']:.0f} m³/h: re-size; new processing inhibited"
            elif n_run < n_inst:
                status, level, reason = "RUNNING: REDUNDANCY LOST", AMBER, "One pump failed; remaining pump carries the cluster"
            if denied and level != RED:
                status, level, reason = "CHEMISTRY HOLD (partial)", AMBER, \
                    f"{', '.join(r['id'] for r in denied)} denied; others run only if its isolation is qualified"

        stopped = level == RED
        for r in reactors:
            rid = r["id"]
            if r in denied:
                out["reactors"][rid] = dict(cluster=c, recipe=r["recipe"], state="DENIED: CHEMISTRY HOLD", level=RED,
                                            flow_slm=None, pressure_mbar=None, throttle_pct=None)
            elif stopped:
                st = ("PRECURSOR STOPPED · emergency exhaust REQUIRED" if state["header_blocked"][c]
                      else "PRECURSOR INHIBITED · exhaust maintained")
                out["reactors"][rid] = dict(cluster=c, recipe=r["recipe"], state=st, level=RED,
                                            flow_slm=flows[rid], pressure_mbar=None, throttle_pct=None)
            else:
                f = fracs[rid]
                out["reactors"][rid] = dict(cluster=c, recipe=r["recipe"],
                                            state="IDLE (no flow)" if flows[rid] == 0 else "RUNNING", level=GREEN,
                                            flow_slm=flows[rid], pressure_mbar=p.P_set_mbar, throttle_pct=100 * f)

        # Pump flow shares and electricity at this hour
        pumps = {}
        # Pumps are NEVER switched off by a hold: exhaust must stay contained and treated (doc 6D).
        through = 0.0 if state["header_blocked"][c] else q_total     # a blocked header passes no flow
        for pid in PUMPS[c]:
            run = pid in pumps_running
            share = through / n_run if run and n_run else 0.0
            pumps[pid] = dict(status=state["pumps"][pid], flow_slm=share,
                              share_pct=100 / n_run if run and n_run else 0.0,
                              kw=float(m.pump_kw(coef, share, p.rated_slm)) if run else 0.0)
        baseline_kw = float(sum(m.pump_kw(coef, line[r["index"], hour] * mult, p.rated_slm) for r in reactors))

        out["clusters"][c] = dict(status=status, level=level, reason=reason, pumps=pumps,
                                  header_mbar=P_h if state["header_sensor_ok"][c] else None,
                                  header_sensor_ok=state["header_sensor_ok"][c], header_blocked=state["header_blocked"][c],
                                  flow_slm=q_total, design=design, denied=[r["id"] for r in denied],
                                  shared_kw=sum(v["kw"] for v in pumps.values()), baseline_kw=baseline_kw,
                                  abatement="ACTIVE · compatible · never bypassed" if state["abatement_ready"][c] else "NOT READY")
        if level != GREEN:
            out["alarms"].append(dict(cluster=c, level=level, status=status, reason=reason))
    return out
