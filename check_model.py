"""
check_model.py: Step 1 acceptance test. Run:  python check_model.py
Every line must say OK before moving to Step 2.
"""
import sys

import model as m

DATA = sys.argv[1] if len(sys.argv) > 1 else "data/SEMICON_Europa_Hackathon_Participant_Data_Pack_2049.xlsx"

p = m.Params()
vp, profiles = m.load_data(DATA)
coef, r2 = m.fit_pump_model(vp)
line = m.make_line(profiles, p.n_tools, p.seed)
e = m.energy_summary(line, coef, p)

# Coincident-peak design basis for cluster A (tools 1-5)
A = m.clusters(p)[0]
peak_tool = line[A].max()
peak_cluster = line[A].max(axis=1).sum()
normal = m.design_check(peak_tool, peak_cluster, n_running=2, margin=p.margin_normal, p=p)
failed = m.design_check(peak_tool, peak_cluster, n_running=1, margin=p.margin_failed, p=p)


def check(name, value, target, tol):
    ok = abs(value - target) <= tol
    print(f"{'OK  ' if ok else 'FAIL'} {name:42s} {value:10.2f}   (doc: {target})")
    return ok


print(f"Pump model: P = {coef[0]:.5f} + {coef[1]:.8f}·Rated + {coef[2]:.8f}·Flow + {coef[3]:.8f}·Flow²/Rated  (R² = {r2:.4f})")
print(f"Pump speed S_600 = {m.m3h(p.S_600):.0f} m3/h | header conductance = {m.m3h(p.C_header):.0f} m3/h\n")
results = [
    check("Regression intercept c0", coef[0], 7.99878, 0.01),
    check("Mean T05 exhaust (slm)", profiles[0].mean(), 23.13, 0.05),
    check("Mean T06 exhaust (slm)", profiles[1].mean(), 23.86, 0.05),
    check("Baseline electricity (kW)", e["baseline_kw"], 80.92, 0.05),
    check("Shared electricity (kW)", e["proposed_kw"], 36.10, 0.05),
    check("Saving (%)", e["saving_pct"], 55.38, 0.1),
    check("Annual saving (MWh/yr)", e["saved_mwh_per_year"], 392.6, 1.0),
    check("Annual CO2e avoided (t/yr)", e["saved_tco2e_per_year"], 47.1, 0.2),
    check("Cluster A coincident peak (slm)", peak_cluster, 227.6, 0.1),
    check("Max header pressure (mbar)", normal["P_max_mbar"], 21.55, 0.02),
    check("Normal: required speed (m3/h)", normal["S_required_m3h"], 1057, 2),
    check("Normal: provided speed (m3/h)", normal["S_provided_m3h"], 1075, 2),
    check("One pump failed: required (m3/h)", failed["S_required_m3h"], 705, 2),
    check("One pump failed: provided (m3/h)", failed["S_provided_m3h"], 767, 2),
]
print(f"\nNormal headroom {normal['headroom_pct']:.1f}% (doc ~1.7%) | failed headroom {failed['headroom_pct']:.1f}%")

# Snapshot sanity: hour 0, cluster A, both pumps running
qA = line[A][:, 0]
P_h = m.header_pressure_mbar(qA.sum(), 2, p)
print(f"Hour 0, cluster A: flow {qA.sum():.1f} slm, header {P_h:.2f} mbar, "
      f"throttle openings {[round(100*m.throttle_fraction(q, P_h, p)) for q in qA]} %")
print("\nALL OK, ready for Step 2" if all(results) else "\nSome checks FAILED: paste the output")
