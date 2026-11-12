"""
check_controller.py: Step 2 acceptance test (doc Section 6E). Run:  python check_controller.py
Plays every demo button and checks the controller's response. All lines must say OK.
"""
import sys

import controller as ctl
import model as m

DATA = sys.argv[1] if len(sys.argv) > 1 else "data/SEMICON_Europa_Hackathon_Participant_Data_Pack_2049.xlsx"
HOUR = 0

p = m.Params()
vp, profiles = m.load_data(DATA)
coef, _ = m.fit_pump_model(vp)
line = m.make_line(profiles, p.n_tools, p.seed)
results = []


def show(title, s):
    r = ctl.evaluate(s, line, coef, p, HOUR)
    print(f"\n=== {title} ===")
    for c, v in r["clusters"].items():
        hp = "BLOCKED" if v["header_blocked"] else ("INVALID" if v["header_mbar"] is None else f"{v['header_mbar']:.2f} mbar")
        pumps = ", ".join(f"{k}: {x['status']} {x['share_pct']:.0f}%" for k, x in v["pumps"].items())
        print(f"  Cluster {c}: {v['status']:28s} header {hp:10s} | {pumps} | {v['shared_kw']:.1f} kW vs {v['baseline_kw']:.1f} kW today")
        print(f"             reason: {v['reason']}")
    for rid in ["R1", "R3", "R6"]:
        x = r["reactors"][rid]
        thr = "—" if x["throttle_pct"] is None else f"{x['throttle_pct']:.0f}%"
        print(f"  {rid}: {x['state']:24s} recipe {x['recipe']:7s} throttle {thr}")
    if s["log"]:
        print(f"  LOG: [{s['log'][0]['level']}] {s['log'][0]['event']} → {s['log'][0]['action']}")
    return r


def check(name, cond):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}")
    results.append(cond)


s = ctl.initial_state(p)
r = show("1. NORMAL", s)
check("Both clusters RUNNING", all(v["status"] == "RUNNING" for v in r["clusters"].values()))
check("2 pumps per cluster, each ~50 % share", all(abs(x["share_pct"] - 50) < 1e-6 for v in r["clusters"].values() for x in v["pumps"].values()))
check("Header pressure below 30 mbar", all(v["header_mbar"] < p.P_set_mbar for v in r["clusters"].values()))

r = show("2. FAIL PUMP A1", ctl.fail_pump(s, "A1"))
check("A2 carries 100 % of cluster A", r["clusters"]["A"]["pumps"]["A2"]["share_pct"] == 100)
check("Cluster A still running (redundancy lost, amber)", r["clusters"]["A"]["level"] == ctl.AMBER)
check("Cluster B unchanged", r["clusters"]["B"]["status"] == "RUNNING")

r = show("3. BLOCK HEADER A", ctl.block_header(s, "A"))
check("Cluster A STOP / ISOLATE", r["clusters"]["A"]["status"] == "STOP / ISOLATE")
check("Pumps A1/A2 keep running (never sealed in)", all(x["status"] == "RUNNING" for x in r["clusters"]["A"]["pumps"].values()))
check("Cluster B keeps running", r["clusters"]["B"]["status"] == "RUNNING")

r = show("4. DOUBLE FLOW A", ctl.double_flow(s, "A"))
check("Cluster A red capacity alarm (no magic pressure hold)", r["clusters"]["A"]["level"] == ctl.RED)

r = show("5. R3 → unapproved TEST-B", ctl.set_recipe(s, "R3", "TEST-B"))
check("R3 denied on shared header", "DENIED" in r["reactors"]["R3"]["state"])
check("Chemistry alarm raised", any("CHEMISTRY" in a["status"] for a in r["alarms"]))
check("R3 flow not added to header", "R3" in r["clusters"]["A"]["denied"])

r = show("6. LOSE HEADER A PRESSURE SIGNAL", ctl.lose_header_sensor(s, "A"))
check("Header A reading INVALID (not faked)", r["clusters"]["A"]["header_mbar"] is None)
check("Cluster A conservative safe-handling stop", r["clusters"]["A"]["level"] == ctl.RED)
check("Exhaust maintained: pumps still carry flow", r["clusters"]["A"]["pumps"]["A1"]["flow_slm"] > 0)

r = show("7. RESET", ctl.reset(p))
check("Everything nominal again", all(v["status"] == "RUNNING" for v in r["clusters"].values()))

print("\nALL OK, ready for Step 3 (UI)" if all(results) else "\nSome checks FAILED: paste the output")
