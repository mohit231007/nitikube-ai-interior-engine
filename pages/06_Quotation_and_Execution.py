from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from nitikube.execution import ExecutionTask, cumulative_cost_by_day, schedule_tasks
from nitikube.quote_ingest import audit_quote_arithmetic, map_quote_lines, quote_total, read_quote_table


st.set_page_config(page_title="NitiKube — Quotation + Execution Audit", page_icon="▤", layout="wide")
st.title("Quotation Audit + Execution Planner")
st.caption("Audit structured contractor quotations and sequence work through a deterministic dependency graph. NitiKube surfaces differences; it does not accuse a contractor without checking scope, pack sizes, wastage and assumptions.")

quote_tab, execution_tab = st.tabs(["Quotation Audit", "Execution Schedule"])

with quote_tab:
    st.subheader("Structured quote import")
    st.write("Upload CSV/XLSX. You map the semantic columns explicitly so NitiKube does not silently guess what a number means.")
    uploaded = st.file_uploader("Quotation file", type=["csv", "xlsx", "xlsm"], key="quote_upload")
    if uploaded:
        try:
            table = read_quote_table(uploaded.getvalue(), uploaded.name)
            st.dataframe(table.head(50), use_container_width=True)
            columns = list(table.columns)
            if len(columns) < 2:
                raise ValueError("quotation must contain at least description and quantity columns")

            c1, c2, c3 = st.columns(3)
            desc_col = c1.selectbox("Description column", columns, index=0)
            qty_col = c2.selectbox("Quantity column", columns, index=min(1, len(columns)-1))
            optional_choices = ["<none>"] + columns
            unit_col = c3.selectbox("Unit column", optional_choices, index=0)

            c4, c5 = st.columns(2)
            rate_col = c4.selectbox("Unit-rate column", optional_choices, index=0)
            amount_col = c5.selectbox("Quoted-amount column", optional_choices, index=0)

            def none_if_marker(value: str) -> str | None:
                return None if value == "<none>" else value

            lines = map_quote_lines(
                table,
                description_col=desc_col,
                quantity_col=qty_col,
                unit_col=none_if_marker(unit_col),
                unit_rate_col=none_if_marker(rate_col),
                amount_col=none_if_marker(amount_col),
            )
            tolerance_pct = st.number_input("Arithmetic tolerance (%)", min_value=0.0, value=0.5, step=0.1)
            audits = audit_quote_arithmetic(lines, tolerance_pct=tolerance_pct)
            audit_df = pd.DataFrame([
                {
                    "row": x.row_number,
                    "description": x.description,
                    "quoted_amount": x.quoted_amount,
                    "qty×rate": x.calculated_amount,
                    "difference": x.difference,
                    "difference_pct": x.difference_pct,
                    "status": x.status,
                }
                for x in audits
            ])
            st.dataframe(audit_df, use_container_width=True, hide_index=True)

            mismatches = sum(x.status == "arithmetic_mismatch" for x in audits)
            insufficient = sum(x.status == "insufficient_data" for x in audits)
            m1, m2, m3 = st.columns(3)
            m1.metric("Mapped lines", len(lines))
            m2.metric("Arithmetic mismatches", mismatches)
            m3.metric("Quoted/calculated known total", f"₹{quote_total(lines):,.2f}")
            if mismatches:
                st.warning("Arithmetic mismatches found. Confirm taxes, discounts, pack-level pricing, rounding and scope before treating them as errors.")
            if insufficient:
                st.info(f"{insufficient} lines lack enough quantity/rate/amount data for arithmetic validation.")

            csv = audit_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download audit CSV", csv, "nitikube_quote_audit.csv", "text/csv")
        except Exception as exc:
            st.error(f"Quotation audit error: {exc}")
    else:
        st.info("For scanned PDFs/photos, NitiKube's future CV/OCR ingestion layer will first extract a proposed table, then require verification before cost auditing. This page intentionally handles structured files only today.")

with execution_tab:
    st.subheader("Dependency-based interior execution schedule")
    st.write("Edit tasks, durations and dependencies. Dependencies are comma-separated task IDs. Durations are planning inputs, not universal contractor norms.")

    default_tasks = pd.DataFrame([
        {"task_id": "site", "name": "Site verification / protection", "duration_days": 1.0, "dependencies": "", "cost": 10000.0, "trade": "general"},
        {"task_id": "electrical_rough", "name": "Electrical rough-in", "duration_days": 2.0, "dependencies": "site", "cost": 25000.0, "trade": "electrical"},
        {"task_id": "ceiling", "name": "False-ceiling framework + boards", "duration_days": 4.0, "dependencies": "electrical_rough", "cost": 45000.0, "trade": "ceiling"},
        {"task_id": "surface_prep", "name": "Wall/ceiling surface preparation", "duration_days": 3.0, "dependencies": "ceiling", "cost": 20000.0, "trade": "paint"},
        {"task_id": "paint", "name": "Primer + paint", "duration_days": 4.0, "dependencies": "surface_prep", "cost": 35000.0, "trade": "paint"},
        {"task_id": "joinery", "name": "Factory joinery / furniture installation", "duration_days": 3.0, "dependencies": "paint", "cost": 180000.0, "trade": "carpentry"},
        {"task_id": "fixtures", "name": "Lighting / switch / fixture fit-off", "duration_days": 1.5, "dependencies": "paint", "cost": 30000.0, "trade": "electrical"},
        {"task_id": "soft", "name": "Soft furnishings + styling", "duration_days": 1.0, "dependencies": "joinery,fixtures", "cost": 40000.0, "trade": "furnishing"},
    ])
    edited = st.data_editor(default_tasks, use_container_width=True, num_rows="dynamic", key="execution_tasks")

    try:
        tasks: list[ExecutionTask] = []
        for _, row in edited.iterrows():
            task_id = str(row["task_id"]).strip()
            if not task_id:
                continue
            dep_text = "" if pd.isna(row["dependencies"]) else str(row["dependencies"])
            deps = tuple(x.strip() for x in dep_text.split(",") if x.strip())
            cost = None if pd.isna(row["cost"]) else float(row["cost"])
            tasks.append(
                ExecutionTask(
                    task_id=task_id,
                    name=str(row["name"]),
                    duration_days=float(row["duration_days"]),
                    dependencies=deps,
                    cost=cost,
                    trade=None if pd.isna(row["trade"]) else str(row["trade"]),
                )
            )
        plan = schedule_tasks(tasks)
        schedule_df = pd.DataFrame([
            {
                "task_id": x.task_id,
                "task": x.name,
                "trade": x.trade,
                "start_day": x.earliest_start_day,
                "finish_day": x.earliest_finish_day,
                "duration_days": x.duration_days,
                "dependencies": ",".join(x.dependencies),
                "cost": x.cost,
                "critical": x.critical,
            }
            for x in plan.tasks
        ])
        s1, s2 = st.columns(2)
        s1.metric("Earliest project duration", f"{plan.project_duration_days:.1f} days")
        s2.metric("Critical path", " → ".join(plan.critical_path))
        st.dataframe(schedule_df, use_container_width=True, hide_index=True)

        timeline = schedule_df.copy()
        timeline["Start"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(timeline["start_day"], unit="D")
        timeline["Finish"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(timeline["finish_day"], unit="D")
        fig = px.timeline(timeline, x_start="Start", x_end="Finish", y="task", color="critical", hover_data=["task_id", "trade", "cost"])
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(title="Relative execution timeline (anchor date is illustrative)")
        st.plotly_chart(fig, use_container_width=True)

        cashflow = cumulative_cost_by_day(plan)
        if cashflow:
            cash_df = pd.DataFrame(cashflow, columns=["day", "cumulative_cost"])
            st.line_chart(cash_df.set_index("day"))
            st.caption("Cashflow assumes each entered task cost is recognized at task completion; it is a planning convention, not a contractor payment rule.")
    except Exception as exc:
        st.error(f"Execution graph error: {exc}")
