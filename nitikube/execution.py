from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ExecutionTask:
    task_id: str
    name: str
    duration_days: float
    dependencies: tuple[str, ...] = ()
    cost: float | None = None
    trade: str | None = None


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    name: str
    earliest_start_day: float
    earliest_finish_day: float
    duration_days: float
    dependencies: tuple[str, ...]
    cost: float | None
    trade: str | None
    critical: bool


@dataclass(frozen=True)
class ExecutionPlan:
    tasks: tuple[ScheduledTask, ...]
    project_duration_days: float
    critical_path: tuple[str, ...]


def _validate(tasks: list[ExecutionTask]) -> dict[str, ExecutionTask]:
    if not tasks:
        raise ValueError("at least one task is required")
    mapping: dict[str, ExecutionTask] = {}
    for task in tasks:
        if not task.task_id.strip():
            raise ValueError("task_id is required")
        if task.task_id in mapping:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        if task.duration_days < 0:
            raise ValueError(f"negative duration for {task.task_id}")
        mapping[task.task_id] = task
    for task in tasks:
        missing = [dep for dep in task.dependencies if dep not in mapping]
        if missing:
            raise ValueError(f"{task.task_id} has missing dependencies: {', '.join(missing)}")
        if task.task_id in task.dependencies:
            raise ValueError(f"{task.task_id} cannot depend on itself")
    return mapping


def topological_order(tasks: Iterable[ExecutionTask]) -> list[str]:
    tasks = list(tasks)
    mapping = _validate(tasks)
    indegree = {task_id: 0 for task_id in mapping}
    children: dict[str, list[str]] = {task_id: [] for task_id in mapping}
    for task in tasks:
        for dep in task.dependencies:
            indegree[task.task_id] += 1
            children[dep].append(task.task_id)

    queue = sorted([task_id for task_id, degree in indegree.items() if degree == 0])
    order: list[str] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()

    if len(order) != len(tasks):
        raise ValueError("task graph contains a dependency cycle")
    return order


def schedule_tasks(tasks: Iterable[ExecutionTask]) -> ExecutionPlan:
    tasks = list(tasks)
    mapping = _validate(tasks)
    order = topological_order(tasks)

    earliest_start: dict[str, float] = {}
    earliest_finish: dict[str, float] = {}
    predecessor_on_longest_path: dict[str, str | None] = {}

    for task_id in order:
        task = mapping[task_id]
        if not task.dependencies:
            start = 0.0
            predecessor = None
        else:
            predecessor = max(task.dependencies, key=lambda dep: earliest_finish[dep])
            start = earliest_finish[predecessor]
        earliest_start[task_id] = start
        earliest_finish[task_id] = start + task.duration_days
        predecessor_on_longest_path[task_id] = predecessor

    project_finish_task = max(order, key=lambda task_id: earliest_finish[task_id])
    project_duration = earliest_finish[project_finish_task]

    critical_reversed: list[str] = []
    cursor: str | None = project_finish_task
    while cursor is not None:
        critical_reversed.append(cursor)
        cursor = predecessor_on_longest_path[cursor]
    critical_path = tuple(reversed(critical_reversed))
    critical_set = set(critical_path)

    scheduled = tuple(
        ScheduledTask(
            task_id=task_id,
            name=mapping[task_id].name,
            earliest_start_day=earliest_start[task_id],
            earliest_finish_day=earliest_finish[task_id],
            duration_days=mapping[task_id].duration_days,
            dependencies=mapping[task_id].dependencies,
            cost=mapping[task_id].cost,
            trade=mapping[task_id].trade,
            critical=task_id in critical_set,
        )
        for task_id in order
    )
    return ExecutionPlan(scheduled, project_duration, critical_path)


def cumulative_cost_by_day(plan: ExecutionPlan) -> list[tuple[float, float]]:
    """Simple finish-day cashflow assuming task cost is recognized on task completion."""
    events = sorted(
        (task.earliest_finish_day, task.cost)
        for task in plan.tasks
        if task.cost is not None and task.cost >= 0
    )
    running = 0.0
    out: list[tuple[float, float]] = []
    for day, cost in events:
        running += float(cost)
        out.append((day, running))
    return out
