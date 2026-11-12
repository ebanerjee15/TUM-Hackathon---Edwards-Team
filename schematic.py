"""
schematic.py: draws the plant as a process schematic (SVG) from controller.evaluate() output.
Pure drawing code: no physics, no logic. Works offline (inline SVG + CSS animation).
"""
TEAL, DARK, AMBER, RED, GREEN, GREY = "#0F7C8C", "#0B3C49", "#D98E04", "#C0392B", "#2E9C6A", "#8A9BA3"
LEVEL = {"OK": GREEN, "WARN": AMBER, "ALARM": RED}

STYLE = """<style>
.t {font-family: Helvetica, Arial, sans-serif; fill: #1f2d33;}
.s {font-size: 11px;} .m {font-size: 13px;} .l {font-size: 15px; font-weight: 700;} .b {font-weight: 700;}
.flow {stroke-dasharray: 6 8; animation: dash 0.9s linear infinite;}
@keyframes dash {to {stroke-dashoffset: -28;}}
.spin {transform-box: fill-box; transform-origin: center; animation: spin 1.2s linear infinite;}
@keyframes spin {to {transform: rotate(360deg);}}
</style>"""


def _txt(x, y, s, cls="m", fill=None, anchor="middle"):
    f = f' style="fill:{fill}"' if fill else ""
    return f'<text class="t {cls}" x="{x}" y="{y}" text-anchor="{anchor}"{f}>{s}</text>'


def _pipe(x1, y1, x2, y2, flowing, w=6, color="#AFC1C5"):
    out = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>'
    if flowing:
        out += f'<line class="flow" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{TEAL}" stroke-width="2.2" stroke-linecap="round"/>'
    return out


def _chamber(cx, rid, r):
    """Reactor chamber drawn as a vessel, holding the same information as the old reactor cards."""
    st = r["state"]
    if st.startswith("DENIED"):
        fill, stroke, label, pres = "#F4F4F4", RED, "CHEM. HOLD", "P — (isolated)"
    elif st.startswith("PRECURSOR STOPPED"):
        fill, stroke, label, pres = "#FBE7E4", RED, "STOPPED", "P — (not verified)"
    elif st.startswith("PRECURSOR INHIBITED"):
        fill, stroke, label, pres = "#FDF3E1", AMBER, "INHIBITED", "P — (not verified)"
    elif st.startswith("IDLE"):
        fill, stroke, label, pres = "#F4F4F4", GREY, "IDLE", "P — (idle)"
    else:
        fill, stroke, label, pres = "#FFFFFF", GREEN, "RUNNING", f'P {r["pressure_mbar"]:.0f} / 30 mbar'
    flow = "flow —" if r["flow_slm"] is None else f'flow {r["flow_slm"]:.1f} slm'
    thr = r["throttle_pct"]
    thr_txt = f"throttle {thr:.0f}%" if thr is not None else ("throttle 0%" if st.startswith("IDLE") else "throttle —")
    bar_w = 0 if thr is None else 80 * min(thr, 100) / 100
    x = cx - 48
    return (f'<rect x="{cx-44}" y="44" width="88" height="10" rx="4" fill="{DARK}"/>'
            f'<rect x="{x}" y="52" width="96" height="134" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
            f'<text class="t" x="{x+8}" y="72" style="font-size:14px"><tspan class="b">{rid}</tspan>'
            f'<tspan style="font-size:11px"> · {r["recipe"]}</tspan></text>'
            + _txt(x + 8, 90, label, "s b", stroke if stroke != GREY else "#6b7b80", anchor="start")
            + _txt(x + 8, 107, flow, "s", anchor="start")
            + _txt(x + 8, 123, pres, "s", anchor="start")
            + f'<rect x="{x+8}" y="131" width="80" height="6" rx="3" fill="#E4E3DD"/>'
            + (f'<rect x="{x+8}" y="131" width="{bar_w:.1f}" height="6" rx="3" fill="{TEAL}"/>' if bar_w else "")
            + _txt(x + 8, 152, thr_txt, "s", anchor="start")
            + f'<rect x="{cx-30}" y="168" width="60" height="5" rx="2" fill="#E07A2F" opacity="0.8"/>')


def _valve(cx, y, r):
    thr = r["throttle_pct"]
    col = TEAL if thr is not None else (GREY if r["state"].startswith("IDLE") else AMBER if r["state"].startswith("PRECURSOR INHIBITED") else RED)
    v = (f'<polygon points="{cx-10},{y-10} {cx+10},{y-10} {cx},{y}" fill="{col}"/>'
         f'<polygon points="{cx-10},{y+10} {cx+10},{y+10} {cx},{y}" fill="{col}"/>')
    return v


def _pump(cx, cy, pid, x):
    failed = x["status"] == "FAILED"
    ring = RED if failed else GREEN
    body = f'<circle cx="{cx}" cy="{cy}" r="34" fill="{"#F9E0DD" if failed else "#FFFFFF"}" stroke="{ring}" stroke-width="4"/>'
    if failed:
        body += (f'<line x1="{cx-18}" y1="{cy-18}" x2="{cx+18}" y2="{cy+18}" stroke="{RED}" stroke-width="5"/>'
                 f'<line x1="{cx+18}" y1="{cy-18}" x2="{cx-18}" y2="{cy+18}" stroke="{RED}" stroke-width="5"/>')
    else:
        body += (f'<g class="spin"><path d="M{cx},{cy-22} L{cx+6},{cy} L{cx-6},{cy} Z M{cx+19},{cy+11} L{cx},{cy+6} L{cx+3},{cy-4} Z '
                 f'M{cx-19},{cy+11} L{cx-3},{cy-4} L{cx},{cy+6} Z" fill="{TEAL}"/>'
                 f'<circle cx="{cx}" cy="{cy}" r="5" fill="{DARK}"/></g>')
    return (body + _txt(cx + 44, cy - 6, f"Pump {pid}", "m b", anchor="start")
            + _txt(cx + 44, cy + 10, "FAILED" if failed else f'{x["share_pct"]:.0f}% · {x["kw"]:.1f} kW',
                   "s", RED if failed else GREEN, anchor="start"))


def _cluster(x0, name, c, reactors):
    flowing = c["flow_slm"] > 0 and not c["header_blocked"]
    out = [f'<g transform="translate({x0},0)">',
           f'<rect x="0" y="0" width="600" height="570" rx="14" fill="#F4F8F9" stroke="#DCE6E8"/>',
           _txt(16, 30, f"CLUSTER {name}", "l", anchor="start")]
    pill_w = 12 + 7.2 * len(c["status"])
    out.append(f'<rect x="120" y="14" width="{pill_w}" height="22" rx="11" fill="{LEVEL[c["level"]]}"/>'
               + _txt(120 + pill_w / 2, 30, c["status"], "s b", "#FFFFFF"))
    # reactors, valves, drops to header
    for i, (rid, r) in enumerate(reactors):
        cx = 70 + i * 110
        out.append(_pipe(cx, 186, cx, 258, flowing and (r["flow_slm"] or 0) > 0 and not r["state"].startswith("DENIED")))
        out.append(_chamber(cx, rid, r))
        out.append(_valve(cx, 220, r))
    # header pipe and gauge
    hcol = RED if c["header_blocked"] else "#AFC1C5"
    out.append(_pipe(40, 258, 540, 258, flowing, w=14, color=hcol))
    out.append(_txt(44, 286, f"HEADER {name}", "s b", anchor="start"))
    if c["header_blocked"]:
        out.append(f'<line x1="275" y1="240" x2="305" y2="276" stroke="{RED}" stroke-width="6"/>'
                   f'<line x1="305" y1="240" x2="275" y2="276" stroke="{RED}" stroke-width="6"/>'
                   + _txt(290, 234, "BLOCKED", "m b", RED))
        g_txt, g_col = "BLOCKED", RED
    elif c["header_mbar"] is None:
        g_txt, g_col = "SIGNAL LOST", RED
    else:
        g_txt, g_col = f'{c["header_mbar"]:.1f}', DARK
    out.append(f'<circle cx="566" cy="258" r="26" fill="#FFFFFF" stroke="{g_col}" stroke-width="3"/>'
               + _txt(566, 256, g_txt if len(g_txt) < 7 else "!", "m b", g_col)
               + _txt(566, 270, "mbar" if g_col == DARK else "", "s", GREY)
               + (_txt(566, 300, g_txt, "s b", g_col) if len(g_txt) >= 7 else ""))
    # pumps
    pumps = list(c["pumps"].items())
    out.append(_pipe(290, 265, 290, 305, flowing))
    out.append(_pipe(170, 305, 410, 305, flowing))
    for (pid, x), px in zip(pumps, (170, 410)):
        out.append(_pipe(px, 305, px, 326, flowing and x["status"] == "RUNNING"))
        out.append(_pump(px, 360, pid, x))
        out.append(_pipe(px, 394, px, 430, flowing and x["status"] == "RUNNING"))
    out.append(_pipe(170, 430, 410, 430, flowing))
    out.append(_txt(420, 423, "N2 dilution added here", "s", GREY, anchor="start"))
    out.append(_pipe(290, 430, 290, 455, flowing))
    # abatement and stack
    out.append(f'<rect x="210" y="455" width="160" height="62" rx="10" fill="#FFFFFF" stroke="{DARK}" stroke-width="2.5"/>'
               + _txt(290, 480, "ABATEMENT", "m b") + _txt(290, 498, "thermal · never bypassed", "s", GREY))
    out.append(_pipe(370, 486, 470, 486, flowing))
    out.append(f'<polygon points="470,476 488,486 470,496" fill="{TEAL if flowing else GREY}"/>'
               + _txt(494, 483, "treated", "s", GREY, anchor="start") + _txt(494, 496, "exhaust", "s", GREY, anchor="start"))
    # chemistry permit
    chem = f'HOLD: {", ".join(c["denied"])}' if c["denied"] else "APPROVED"
    out.append(_txt(16, 555, f"Chemistry permit: {chem}", "s b", RED if c["denied"] else GREEN, anchor="start"))
    out.append("</g>")
    return "".join(out)


def plant_svg(res):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1240 580" width="100%">{STYLE}']
    for name, x0 in (("A", 0), ("B", 640)):
        reactors = [(rid, r) for rid, r in res["reactors"].items() if r["cluster"] == name]
        parts.append(_cluster(x0, name, res["clusters"][name], reactors))
    parts.append("</svg>")
    return "".join(parts)
