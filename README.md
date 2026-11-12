# hBN Shared-Pumping Digital Twin

**A local, interactive concept demonstrator for reducing vacuum-pumping energy use in semiconductor manufacturing.**

Developed for the **Edwards × Swansea University challenge** at the **NextSEMI Hackathon, SEMICON Europa 2026** (Munich, 10–12 November 2026). The project explores whether a group of hexagonal boron nitride (hBN) metal-organic chemical vapour deposition (MOCVD) reactors could share vacuum-pumping infrastructure without compromising the modelled process-pressure and operational constraints.

> [!IMPORTANT]
> **Proof of concept, not a plant design or safety system.** This project uses fictional hackathon data, simplified vacuum physics and explicit engineering assumptions. The results are illustrative, not measured savings or verified operating limits for a real fabrication facility.

## The idea

A conventional arrangement assigns a dedicated vacuum pump to each reactor, even when individual exhaust demand is relatively low. This demonstrator compares that baseline with a **shared-pumping architecture**:

| Baseline | Proposed concept |
| --- | --- |
| 10 hypothetical hBN MOCVD reactors | The same 10 reactors |
| One pump per reactor (**10 pumps**) | Two clusters of five reactors |
| Independent exhaust pumping | Two parallel pumps per cluster (**4 pumps total**) |
| Dedicated pump energy demand | Load sharing, header-pressure checks and supervisory fault handling |

Each cluster is represented as:

```text
5 hBN MOCVD reactors
        │
  Individual throttle valves
        │
   Shared exhaust header
        │
   ┌────┴────┐
 Pump 1    Pump 2    (parallel, load sharing)
   └────┬────┘
        │
  Nitrogen dilution
        │
 Thermal abatement
        │
  Treated exhaust
```

The interactive app displays both clusters, reactor and pump states, estimated header pressures, throttle openings, pumping electricity, and the response to simulated faults.

## Illustrative model results

For the supplied synthetic data and the model's default assumptions:

| Metric | Dedicated-pump baseline | Shared-pumping concept |
| --- | ---: | ---: |
| Installed pumps | 10 | 4 |
| Mean pumping power | 80.92 kW | 36.10 kW |
| Modelled pumping-power reduction | — | **55.38%** |
| Annualised electricity saving | — | **392.6 MWh/year** |
| Annualised emissions avoided | — | **47.1 t CO₂e/year** |

Annual figures extrapolate the synthetic 720-hour demand profile to **8,760 operating hours/year**, using an illustrative grid-emissions factor of **0.12 kg CO₂e/kWh**. They cover **modelled vacuum-pump electricity only**, not the full environmental or financial impact of a fab gas-management system.

The model also checks effective pumping capacity against coincident reactor peaks. Under its assumed conductances and margins, cluster A has approximately **1.6% normal-case capacity headroom** and **8.7% headroom with one pump unavailable** (using a reduced contingency margin). These are model outputs, **not validated hardware ratings or a claim of production readiness**.

## Interactive scenarios

Use the Streamlit sidebar to explore:

- **Normal operation:** two pumps share the flow in each cluster.
- **Pump A1 failure:** the other pump takes the cluster load, with a redundancy warning if the modelled capacity check passes.
- **Blocked header A:** processing is stopped/isolated in the simulation; an independent, qualified emergency exhaust path would be required in practice.
- **Doubled flow in cluster A:** capacity and pressure-control limits are re-evaluated; the example produces a capacity alarm.
- **Unapproved recipe on reactor R3:** a synthetic chemistry-compatibility gate denies that reactor access to the shared header.
- **Loss of header A pressure signal:** the reading becomes invalid, and the simulated controller inhibits new processing rather than using stale data.
- **Requalify R3 / Reset:** restore the approved synthetic recipe or reset the demonstration.

Faults can be combined. The **Pressure trends**, **Alarm log** and **Data & assumptions** tabs show the resulting behaviour and model provenance.

## Run locally

**Requirements:** Python **3.10+** and the included Excel data pack. From the repository root:

```bash
# Optional: create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell): .venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install streamlit altair numpy pandas openpyxl

# Launch the interactive demonstrator
python -m streamlit run app.py
```

Open the **local address printed by Streamlit** in your browser (typically `http://localhost:8501`). The included `.streamlit/config.toml` binds the server to `localhost` and disables Streamlit usage-statistics collection. The application itself makes no remote API calls.

By default, the app reads:

```text
data/SEMICON_Europa_Hackathon_Participant_Data_Pack_2049.xlsx
```

To use a workbook at another location, set the `HBN_DATA` environment variable **before** launching the app. The replacement workbook must contain the expected sheet names and columns.

## Model and implementation

The code separates the numerical model, supervisory logic and presentation:

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI, scenarios, pressure plots and metrics |
| `model.py` | Synthetic demand generation, pump-power regression, vacuum and energy calculations |
| `controller.py` | Simulated chemistry permits, cluster states, fault responses and alarm log |
| `schematic.py` | Animated SVG drawing of the plant |
| `check_model.py` | Numerical regression and design-check acceptance tests |
| `check_controller.py` | Scenario and fault-response acceptance tests |
| `.streamlit/config.toml` | Local-server and UI configuration |
| `data/*.xlsx` | Supplied synthetic hackathon participant data pack |

### Inputs and assumptions

- Reads **`Vacuum_Performance`** to fit pump electricity against pump rating and flow using **28 synthetic operating points**.
- Uses **`Fab_Process_Data`** exhaust profiles for tools `T05` and `T06` as proxies for entire reactors. Alternating profiles are randomly time-shifted (fixed seed `42`) to form a **10-reactor, 720-hour** scenario. These are **not measured hBN reactor traces**.
- Estimates gas throughput using an ideal-gas conversion, and header pressure from throughput and **effective pumping speed** (parallel pumps combined with assumed header conductance).
- Checks whether individual reactor throttle valves can maintain the assumed **30 mbar** operating pressure.
- Uses assumed per-reactor foreline conductance of **0.10 m³/s**, cluster header conductance of **0.50 m³/s**, and a derived—not manufacturer-specified—pump speed at the reference pressure.
- Checks a **1.5× normal-operation** design-flow margin and a **1.0× single-pump-failure** margin.
- Models supervisory decisions using **synthetic recipe identifiers and simulated signals**; it does not identify real process chemistry or certify gas compatibility.

The energy and capacity models are deliberately simple and explainable. In particular, the pump-power curve is extrapolated below the lowest load points in the synthetic data.

## Run the checks

Before reviewing the UI, you can run the two supplied acceptance scripts:

```bash
python check_model.py
python check_controller.py
```

Both scripts check their outputs against the expected synthetic scenario and should end with an **`ALL OK`** message when the data and code match. They can also take an alternative workbook path as their first argument, although the numerical reference values are specific to the supplied data pack.

## Scope and limitations

This repository demonstrates **one possible architecture and its supervisory behaviour**, rather than a validated industrial solution.

- **No safety certification or hardware control.** No physical pumps, valves, sensors or abatement systems are connected. Real interlocks must be implemented independently in qualified equipment/PLC systems.
- **No guaranteed emergency handling.** The blocked-header scenario explicitly requires a suitable emergency exhaust/abatement route, which the app does **not** implement.
- **No real recipe compatibility assessment.** `hBN-A` and `TEST-B` are illustrative placeholders, not a chemical hazard assessment or operating permit.
- **Limited environmental boundary.** The calculated savings concern pump electricity. Full deployment would require assessment of abatement, dilution/purge gas, thermal and utility demands, capital equipment, maintenance, embodied impacts and lifecycle trade-offs.
- **Unvalidated process and equipment assumptions.** Conductance, pump performance outside the supplied data, dynamics/transients, control-system behaviour and reliability require equipment-vendor and process-engineering review.
- **Synthetic inputs.** The participant workbook contains fictional values for comparative hackathon modelling; it must **not** be presented as Edwards, customer or industry benchmark data.

Possible next steps include hydraulic/vacuum-network validation, dynamic control modelling, real pump curves and transient tests, hazard and operability review, and a more complete lifecycle and techno-economic assessment.

## Hackathon context

This work addresses the **“Future of Semiconductor Fab Gas Management”** challenge set by **Edwards and Swansea University** at the **SEMICON Europa × TUM Venture Labs NextSEMI Hackathon 2026**. The wider challenge asked teams to rethink post-process gas management for a more sustainable fab while accounting for safety, reliability and process performance, with **2049** as a long-term horizon.

The project is an independent hackathon proof of concept; the names of event partners do not imply endorsement or technical validation.
