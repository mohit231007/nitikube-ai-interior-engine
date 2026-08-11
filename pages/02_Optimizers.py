from __future__ import annotations

import pandas as pd
import streamlit as st

from nitikube.constraints import ScopeCategory, guard_scope
from nitikube.lighting_optimizer import optimise_lighting_layouts
from nitikube.optimizer import DesignOption, pareto_front, weighted_rank


st.set_page_config(page_title="NitiKube — Optimizers", page_icon="◇", layout="wide")
st.title("Constraint + Multi-objective Optimizers")
st.caption("NitiKube searches feasible combinations first, then ranks them. Target ranges and weights remain explicit user/project assumptions rather than hidden AI guesses.")

light_tab, design_tab, safety_tab = st.tabs(["Lighting Optimizer", "Design Trade-offs", "Scope Guardrails"])

with light_tab:
    st.subheader("Search COB layouts by brightness + beam coverage")
    a, b, c, d = st.columns(4)
    length_ft = a.number_input("Room length (ft)", min_value=1.0, value=22.75, step=0.25)
    width_ft = b.number_input("Room width (ft)", min_value=1.0, value=10.583, step=0.25, format="%.3f")
    ceiling = c.number_input("Ceiling height (ft)", min_value=6.0, value=9.0, step=0.25)
    plane = d.number_input("Evaluation plane (ft)", min_value=0.0, value=2.5, step=0.25)

    e, f, g, h = st.columns(4)
    angle = e.number_input("Beam angle (°)", min_value=5.0, max_value=120.0, value=36.0)
    min_lux = f.number_input("Minimum maintained lux", min_value=20.0, value=140.0, step=10.0)
    max_lux = g.number_input("Maximum maintained lux", min_value=20.0, value=190.0, step=10.0)
    spacing_ratio = h.number_input("Max spacing / nominal beam", min_value=0.5, max_value=2.0, value=1.20, step=0.05)

    lumen_text = st.text_input("Available fixture outputs (lumens, comma separated)", value="350,400,450,500,550,600")
    try:
        lumen_options = [float(x.strip()) for x in lumen_text.split(",") if x.strip()]
        candidates = optimise_lighting_layouts(
            length_ft=length_ft,
            width_ft=width_ft,
            ceiling_height_ft=ceiling,
            evaluation_plane_height_ft=plane,
            beam_angle_deg=angle,
            lumen_options=lumen_options,
            min_lux=min_lux,
            max_lux=max_lux,
            max_spacing_to_beam=spacing_ratio,
            min_fixtures=4,
            max_fixtures=30,
        )
        if candidates:
            top = candidates[:15]
            df = pd.DataFrame([
                {
                    "fixtures": x.fixtures,
                    "grid": f"{x.rows} × {x.cols}",
                    "lm/fixture": x.lumens_per_fixture,
                    "maintained lux": round(x.maintained_lux, 1),
                    "beam diameter ft": round(x.beam_diameter_ft, 2),
                    "width spacing ft": round(x.width_spacing_ft, 2),
                    "length spacing ft": round(x.length_spacing_ft, 2),
                    "worst spacing/beam": round(x.worst_spacing_to_beam, 3),
                    "objective score ↓": round(x.score, 3),
                }
                for x in top
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
            best = top[0]
            st.success(f"Best under the entered constraints: {best.fixtures} fixtures in a {best.rows} × {best.cols} grid at {best.lumens_per_fixture:.0f} lm each, estimated {best.maintained_lux:.0f} lx.")
            st.caption("The objective score is only a ranking heuristic among already-feasible candidates. Photometric files (IES/LDT) will later replace the simple nominal-beam approximation where available.")
        else:
            st.warning("No feasible combination found in the searched fixture-count/lumen range. Widen the target range, allow more beam spacing, provide other lumen outputs, use a wider beam, or add diffuse/cove lighting.")
    except Exception as exc:
        st.error(f"Lighting search input error: {exc}")

with design_tab:
    st.subheader("Budget-constrained design ranking + Pareto front")
    budget = st.number_input("Budget available for these options (₹)", min_value=0.0, value=300_000.0, step=10_000.0)
    defaults = pd.DataFrame([
        {"name": "Value", "cost": 180000.0, "quality": 78.0, "durability": 82.0, "aesthetics": 72.0, "comfort": 78.0, "maintainability": 88.0, "feasible": True},
        {"name": "Balanced", "cost": 240000.0, "quality": 88.0, "durability": 90.0, "aesthetics": 86.0, "comfort": 88.0, "maintainability": 86.0, "feasible": True},
        {"name": "Premium", "cost": 320000.0, "quality": 94.0, "durability": 92.0, "aesthetics": 95.0, "comfort": 92.0, "maintainability": 80.0, "feasible": True},
    ])
    edited = st.data_editor(defaults, use_container_width=True, num_rows="dynamic", key="design_options")

    weights_cols = st.columns(5)
    weights = (
        weights_cols[0].number_input("Quality weight", min_value=0.0, value=0.25, step=0.05),
        weights_cols[1].number_input("Durability weight", min_value=0.0, value=0.25, step=0.05),
        weights_cols[2].number_input("Aesthetics weight", min_value=0.0, value=0.15, step=0.05),
        weights_cols[3].number_input("Comfort weight", min_value=0.0, value=0.15, step=0.05),
        weights_cols[4].number_input("Maintainability weight", min_value=0.0, value=0.20, step=0.05),
    )

    try:
        options = [
            DesignOption(
                name=str(row["name"]),
                cost=float(row["cost"]),
                quality=float(row["quality"]),
                durability=float(row["durability"]),
                aesthetics=float(row["aesthetics"]),
                comfort=float(row["comfort"]),
                maintainability=float(row["maintainability"]),
                feasible=bool(row["feasible"]),
            )
            for _, row in edited.iterrows()
        ]
        ranked = weighted_rank(options, budget=budget, weights=weights)
        front = pareto_front(options, budget=budget)
        if ranked:
            rank_df = pd.DataFrame([{"rank": i+1, "option": o.name, "cost": o.cost, "weighted score": round(s, 2)} for i, (o, s) in enumerate(ranked)])
            st.dataframe(rank_df, use_container_width=True, hide_index=True)
            st.success(f"Weighted winner under budget: {ranked[0][0].name}")
        else:
            st.warning("No feasible options are within the budget.")
        st.write("**Pareto-efficient options:**", ", ".join(o.name for o in front) if front else "None")
        st.caption("The starter scores above are editable placeholders for testing the optimizer, not NitiKube factual claims about real materials/designs. Production scores must be derived from sourced evidence and explicit user preferences.")
    except Exception as exc:
        st.error(f"Option ranking error: {exc}")

with safety_tab:
    st.subheader("Execution-scope safety boundary")
    category = st.selectbox("Scope category", list(ScopeCategory), format_func=lambda x: x.value.replace("_", " ").title())
    guard = guard_scope(category)
    if guard.professional_verification_required:
        st.error("PROFESSIONAL VERIFICATION REQUIRED")
    else:
        st.success("NitiKube planning support allowed")
    st.write(guard.message)
