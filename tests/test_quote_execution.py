from io import BytesIO

import pandas as pd
import pytest

from nitikube.execution import ExecutionTask, cumulative_cost_by_day, schedule_tasks, topological_order
from nitikube.quote_ingest import audit_quote_arithmetic, map_quote_lines, quote_total, read_quote_table


def test_execution_schedule_and_critical_path():
    tasks = [
        ExecutionTask("a", "A", 2),
        ExecutionTask("b", "B", 3, ("a",)),
        ExecutionTask("c", "C", 1, ("a",)),
        ExecutionTask("d", "D", 2, ("b", "c")),
    ]
    plan = schedule_tasks(tasks)
    assert plan.project_duration_days == 7
    assert plan.critical_path == ("a", "b", "d")
    assert [x.task_id for x in plan.tasks if x.critical] == ["a", "b", "d"]


def test_execution_cycle_is_rejected():
    tasks = [
        ExecutionTask("a", "A", 1, ("b",)),
        ExecutionTask("b", "B", 1, ("a",)),
    ]
    with pytest.raises(ValueError, match="cycle"):
        topological_order(tasks)


def test_cashflow_uses_finish_day():
    plan = schedule_tasks([
        ExecutionTask("a", "A", 2, cost=100),
        ExecutionTask("b", "B", 1, ("a",), cost=200),
    ])
    assert cumulative_cost_by_day(plan) == [(2.0, 100.0), (3.0, 300.0)]


def test_csv_quote_read_and_mapping():
    csv = b"Item,Qty,Unit,Rate,Amount\nCOB,12,pcs,500,6000\nPaint,10,L,200,2100\n"
    table = read_quote_table(csv, "quote.csv")
    lines = map_quote_lines(
        table,
        description_col="Item",
        quantity_col="Qty",
        unit_col="Unit",
        unit_rate_col="Rate",
        amount_col="Amount",
    )
    assert len(lines) == 2
    assert lines[0].calculated_amount == 6000
    assert quote_total(lines) == 8100

    audits = audit_quote_arithmetic(lines, tolerance_pct=0.5, absolute_tolerance=1)
    assert audits[0].status == "matches"
    assert audits[1].status == "arithmetic_mismatch"
    assert audits[1].difference == 100


def test_quote_mapping_requires_valid_quantity():
    table = pd.DataFrame({"Item": ["COB"], "Qty": [None]})
    with pytest.raises(ValueError, match="quantity"):
        map_quote_lines(table, description_col="Item", quantity_col="Qty")
