"""
app.py: interactive concept demonstrator for shared vacuum pumping on a hypothetical 10-tool hBN MOCVD line.
Run (offline):  streamlit run app.py
UI only: physics in model.py, supervisory logic in controller.py, drawing in schematic.py.
"""
import os

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import controller as ctl
import model as m
import schematic as sc

DATA = os.environ.get("HBN_DATA", "data/SEMICON_Europa_Hackathon_Participant_Data_Pack_2049.xlsx")
RED = "#C0392B"

st.set_page_config(page_title="hBN Shared-Pumping Demonstrator", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"""
<style>
.block-container {{padding-top: 1.4rem; padding-bottom: 1rem;}}
h1 {{color:#0B3C49; font-size:2rem !important; padding-bottom:0.2rem;}}
.banner {{background:#0B3C49; color:#fff; padding:9px 16px; border-radius:8px; font-weight:700; font-size:0.9rem;
          display:flex; justify-content:space-between; margin-bottom:0.6rem;}}
.banner span {{color:#8FB8BF; font-weight:400; font-size:0.82rem;}}
section[data-testid="stSidebar"] {{background:#EEF3F4;}}
section[data-testid="stSidebar"] .stButton button {{background:#fff; border:1px solid #D5DDE0; color:#5B6F78; font-weight:500;}}
div[data-testid="stMetricValue"] {{font-size:2rem;}}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data (cached, local file only)
@st.cache_resource(show_spinner="Loading local data pack…")
def load():
    p = m.Params()
    vp, profiles = m.load_data(DATA)
    coef, r2 = m.fit_pump_model(vp)
    line = m.make_line(profiles, p.n_tools, p.seed)
    return p, coef, r2, line, m.energy_summary(line, coef, p)


if not os.path.exists(DATA):
    st.error(f"Local data file not found: `{DATA}`. Put the hackathon workbook in the `data/` folder.")
    st.stop()
p, coef, r2, line, annual = load()
if "plant" not in st.session_state:
    st.session_state.plant = ctl.initial_state(p)


def act(fn, *args):
    st.session_state.plant = fn(st.session_state.plant, *args)


# ---------------------------------------------------------------- sidebar: scenario controls
with st.sidebar:
    st.markdown("### Scenario controls")
    hour = st.slider("Snapshot hour", 0, line.shape[1] - 1, 0, help="Hour of the synthetic 720-hour month")
    if st.button("↺ Reset / Normal", key="reset", width="stretch"):
        st.session_state.plant = ctl.reset(p)
    if st.button("Fail pump A1", key="fail", width="stretch"):
        act(ctl.fail_pump, "A1")
    if st.button("Block header A", key="block", width="stretch"):
        act(ctl.block_header, "A")
    if st.button("Double A flow", key="double", width="stretch"):
        act(ctl.double_flow, "A")
    if st.button("R3 → TEST-B", key="chem", width="stretch", help="Request an unapproved synthetic recipe on reactor R3"):
        act(ctl.set_recipe, "R3", "TEST-B")
    if st.button("Lose header A signal", key="sensor", width="stretch"):
        act(ctl.lose_header_sensor, "A")
    r3_bad = next(r for r in st.session_state.plant["reactors"] if r["id"] == "R3")["recipe"] != "hBN-A"
    if st.button("Requalify R3", key="requal", width="stretch", disabled=not r3_bad, help="Simulated operator acknowledgement"):
        act(ctl.set_recipe, "R3", "hBN-A")
    pl = st.session_state.plant
    active = {"fail": any(v == "FAILED" for v in pl["pumps"].values()),
              "block": pl["header_blocked"]["A"],
              "double": pl["flow_multiplier"]["A"] != 1.0,
              "chem": any(r["recipe"] != "hBN-A" for r in pl["reactors"]),
              "sensor": not pl["header_sensor_ok"]["A"]}
    css = [f".st-key-{k} button {{border:2.5px solid {RED} !important; background:#FDECEA !important; color:#7A1F14 !important; font-weight:700 !important;}}"
           for k, on in active.items() if on]
    if not any(active.values()):
        css.append(".st-key-reset button {border:2.5px solid #0F7C8C !important; background:#E3F1F2 !important; color:#0B3C49 !important; font-weight:700 !important;}")
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)
    st.caption("Buttons combine: e.g. fail a pump, then block a header. Reset clears everything.")
    st.divider()
    st.caption("Concept demonstration only, not a safety system. Real interlocks need independent, qualified hardware/PLC logic.")

res = ctl.evaluate(st.session_state.plant, line, coef, p, hour)
cl = res["clusters"]

# ---------------------------------------------------------------- header
st.title("Shared vacuum pumping · hBN MOCVD line")
st.markdown('<div class="banner"><div>🔒 LOCAL / OFFLINE: DATA STAYS IN FAB · AIR-GAPPED · WIRED-ONLY · NO CLOUD</div>'
            '<span>synthetic hackathon data · minimal signals, no recipes</span></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- plant schematic
components.html('<div style="width:100%;height:100%;">' + sc.plant_svg(res).replace('width="100%"', 'width="100%" height="100%" preserveAspectRatio="xMidYMid meet"', 1)
                + '</div><style>html,body{margin:0;height:100%;overflow:hidden;background:transparent;}</style>', height=640)

# ---------------------------------------------------------------- KPIs
running = sum(1 for c in cl.values() for x in c["pumps"].values() if x["status"] == "RUNNING")
shared_kw = sum(c["shared_kw"] for c in cl.values())
base_kw = sum(c["baseline_kw"] for c in cl.values())
k = st.columns(4)
with k[0].container(border=True):
    st.metric("Pumps running", f"{running} of 4")
    st.caption("vs 10 in a one-pump-per-reactor layout")
with k[1].container(border=True):
    st.metric("Pump power now", f"{shared_kw:.1f} kW")
    st.caption(f"{100 * (shared_kw / base_kw - 1):.0f}% vs {base_kw:.0f} kW baseline at this hour")
with k[2].container(border=True):
    st.metric("Annual · SYNTHETIC SCENARIO", f"−{annual['saving_pct']:.0f}%")
    st.caption(f"≈ {annual['saved_mwh_per_year']:.0f} MWh · {annual['saved_tco2e_per_year']:.0f} t CO₂e per year")
with k[3].container(border=True):
    st.markdown(f'<div style="font-size:0.875rem">Active alarms</div>'
                f'<div style="font-size:2rem; font-weight:600; color:{RED if res["alarms"] else "#2E9C6A"}">{len(res["alarms"])}</div>',
                unsafe_allow_html=True)
    st.caption("All clear" if not res["alarms"] else " · ".join(f'{a["cluster"]}: {a["status"]}' for a in res["alarms"]))

# ---------------------------------------------------------------- tabs
t1, t2, t3 = st.tabs(["Pressure trends", "Alarm log", "Data & assumptions"])

with t1:
    st.caption("Steady-state header pressure over the synthetic month, with the current plant state. "
               "Red dashed line: highest header pressure at which the busiest reactor can still hold 30 mbar. Grey line: snapshot hour.")
    cols = st.columns(2)
    plant = st.session_state.plant
    for col, (name, idx) in zip(cols, zip("AB", m.clusters(p))):
        c = cl[name]
        with col:
            if c["header_blocked"] or c["header_mbar"] is None:
                st.info(f"Header {name}: {'blocked' if c['header_blocked'] else 'pressure signal INVALID'}. No trace shown (no faked data).")
                continue
            allowed = [r["index"] for r in plant["reactors"] if r["cluster"] == name and r["id"] not in c["denied"]]
            n_run = sum(1 for x in c["pumps"].values() if x["status"] == "RUNNING")
            ser = m.throughput(line[allowed].sum(axis=0) * plant["flow_multiplier"][name], p.T_gas) / m.s_eff_header(n_run, p) / 100
            lim = c["design"]["P_max_mbar"]
            df = pd.DataFrame({"Hour": np.arange(len(ser)), "Header pressure (mbar)": ser})
            top = max(lim * 1.15, float(ser.max()) * 1.1)
            ch = (alt.Chart(df).mark_line(color="#0F7C8C", strokeWidth=1.2)
                  .encode(x=alt.X("Hour:Q", scale=alt.Scale(domain=[0, len(ser) - 1], nice=False)),
                          y=alt.Y("Header pressure (mbar):Q", scale=alt.Scale(domain=[0, top])))
                  + alt.Chart(pd.DataFrame({"y": [lim]})).mark_rule(color=RED, strokeDash=[6, 4]).encode(y="y:Q")
                  + alt.Chart(pd.DataFrame({"x": [hour]})).mark_rule(color="#8A9BA3").encode(x="x:Q"))
            st.markdown(f"**Header {name}** · {n_run} pump(s) running · month max {ser.max():.1f} mbar vs limit {lim:.2f} mbar")
            st.altair_chart(ch.properties(height=230), width="stretch")

with t2:
    st.caption("Stored locally only; no outbound communication.")
    log = st.session_state.plant["log"]
    if log:
        st.dataframe(pd.DataFrame(log)[["time", "level", "cluster", "event", "action"]], hide_index=True, width="stretch")
    else:
        st.write("No events yet. Use the scenario controls in the sidebar.")

with t3:
    st.dataframe(pd.DataFrame([
        ("Pump electricity vs flow and size", "DATA", f"Regression on 28 workbook points, R² = {r2:.4f}; extrapolated below 10 % load"),
        ("Reactor exhaust flows", "DATA (proxy)", "T05/T06 profiles, one proxy per whole hBN reactor, time-shifted (seed 42)"),
        ("Grid carbon 0.12 kg CO₂e/kWh", "DATA", "Utility_Data, illustrative"),
        ("Header pressure P = Q / S_eff", "PHYSICS", "Pumps in parallel, in series with header conductance"),
        ("Throttle opening = C_required / C_tool", "PHYSICS", "Steady state; feasible only if ≤ 100 % and header < 30 mbar"),
        ("Reactor pressure 30 mbar", "LITERATURE", "Published hBN MOCVD example"),
        ("Pump speed 1,335 m³/h", "ASSUMPTION", "Inferred from 600 slm at 30 mbar, NOT a pump specification"),
        ("Foreline 360 m³/h, header 1,800 m³/h", "ASSUMPTION", "No pipe geometry in workbook; requires OEM validation"),
        ("1.5× capacity margin; 1.0× after one pump fails", "DESIGN RULE", "C03 capacity with margin; N-1 check"),
        ("8,760 h per year", "ASSUMPTION", "Continuous operation"),
        ("Recipes hBN-A / TEST-B", "ILLUSTRATION", "Synthetic placeholders, no real recipe or IP"),
    ], columns=["Item", "Source", "Detail"]), hide_index=True, width="stretch")
    st.caption("Not claimed: 95 % downtime reduction, 70 % maintenance/waste reduction, pipe sizes, real-fab performance "
               "or compatibility of uncharacterised TEB exhaust.")
