"""
Lightweight agent loop: Planner → Tool Selector → Executor → Memory → Evaluator.

Custom framework (no LangChain/CrewAI) for predictable production behavior.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Protocol

from app.agents.core.logger import AgentDecisionLogger
from app.agents.models.schemas import (
    AgentGoal,
    AgentPlan,
    AgentRunResult,
    AgentTask,
    EvaluationResult,
    StepResult,
    TaskStatus,
    ToolResult,
)


class AgentTool(Protocol):
    name: str
    description: str

    def execute(self, **kwargs: Any) -> ToolResult: ...


class AgentMemory:
    """In-run context store — prior step outputs feed downstream tasks."""

    def __init__(self):
        self._store: dict[str, Any] = {}
        self._history: list[dict[str, Any]] = []

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value
        self._history.append({"action": "set", "key": key, "value": value})

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def update(self, data: dict[str, Any]) -> None:
        self._store.update(data)
        self._history.append({"action": "update", "keys": list(data.keys())})

    @property
    def context(self) -> dict[str, Any]:
        return dict(self._store)

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)


class BasePlanner(ABC):
    @abstractmethod
    def plan(self, goal: AgentGoal, memory: AgentMemory) -> AgentPlan: ...


class BaseToolSelector(ABC):
    @abstractmethod
    def select(self, task: AgentTask, tools: dict[str, AgentTool], memory: AgentMemory) -> str: ...


class Executor:
    """Runs a task against a selected tool with retry logic."""

    def __init__(self, decision_logger: AgentDecisionLogger):
        self._logger = decision_logger

    def run(
        self,
        task: AgentTask,
        tool: AgentTool,
        memory: AgentMemory,
        max_retries: int | None = None,
    ) -> StepResult:
        retries = max_retries if max_retries is not None else task.max_retries
        last_error = ""
        params = {**task.parameters, **memory.context}

        for attempt in range(1, retries + 2):
            task.status = TaskStatus.RETRYING if attempt > 1 else TaskStatus.RUNNING
            self._logger.log(
                "execute",
                f"Executing task '{task.name}' via tool '{tool.name}'",
                task_id=task.id,
                tool=tool.name,
                attempt=attempt,
            )
            start = time.perf_counter()
            try:
                result = tool.execute(**params)
                result.duration_ms = (time.perf_counter() - start) * 1000
            except Exception as exc:
                result = ToolResult(success=False, error=str(exc))
                result.duration_ms = (time.perf_counter() - start) * 1000

            if result.success:
                task.status = TaskStatus.COMPLETED
                memory.set(f"step_{task.id}", result.output)
                memory.set(task.name, result.output)
                return StepResult(
                    task_id=task.id,
                    task_name=task.name,
                    tool_name=tool.name,
                    result=result,
                    reasoning=f"Task completed on attempt {attempt}",
                    attempt=attempt,
                )

            last_error = result.error or "Unknown error"
            self._logger.log(
                "retry",
                f"Task '{task.name}' failed: {last_error}",
                task_id=task.id,
                attempt=attempt,
            )

        task.status = TaskStatus.FAILED
        return StepResult(
            task_id=task.id,
            task_name=task.name,
            tool_name=tool.name,
            result=ToolResult(success=False, error=last_error),
            reasoning=f"Failed after {retries + 1} attempts",
            attempt=retries + 1,
        )


class Evaluator(ABC):
    @abstractmethod
    def evaluate_step(
        self, task: AgentTask, step: StepResult, goal: AgentGoal, memory: AgentMemory
    ) -> EvaluationResult: ...

    @abstractmethod
    def evaluate_final(
        self, goal: AgentGoal, steps: list[StepResult], memory: AgentMemory
    ) -> EvaluationResult: ...


class AgentLoop:
    """
    Orchestrates the full agent pipeline:
    Goal → Plan → [Select Tool → Execute → Evaluate]* → Final Evaluation
    """

    def __init__(
        self,
        agent_name: str,
        planner: BasePlanner,
        tool_selector: BaseToolSelector,
        evaluator: Evaluator,
        tools: dict[str, AgentTool],
        decision_logger: AgentDecisionLogger | None = None,
        log_dir: str | None = None,
    ):
        self.agent_name = agent_name
        self.planner = planner
        self.tool_selector = tool_selector
        self.evaluator = evaluator
        self.tools = tools
        self._logger = decision_logger or AgentDecisionLogger(log_dir=log_dir)
        self.executor = Executor(self._logger)

    def run(self, goal: AgentGoal) -> AgentRunResult:
        memory = AgentMemory()
        memory.update(goal.context)

        self._logger.log("plan", f"Planning for goal: {goal.description}", goal=goal.description)
        plan = self.planner.plan(goal, memory)
        self._logger.log(
            "plan",
            f"Plan created with {len(plan.tasks)} tasks",
            reasoning=plan.reasoning,
            task_names=[t.name for t in plan.tasks],
        )

        run = AgentRunResult(
            agent_name=self.agent_name,
            goal=goal.description,
            status="running",
            plan=plan,
            decisions=self._logger.decisions,
        )

        steps: list[StepResult] = []
        evaluations: list[EvaluationResult] = []
        completed_task_ids: set[str] = set()

        for task in plan.tasks:
            if task.depends_on and not all(dep in completed_task_ids for dep in task.depends_on):
                self._logger.log("execute", f"Skipping '{task.name}' — dependencies not met", task_id=task.id)
                continue

            tool_name = task.tool_name or self.tool_selector.select(task, self.tools, memory)
            self._logger.log(
                "select_tool",
                f"Selected tool '{tool_name}' for task '{task.name}'",
                task_id=task.id,
                tool=tool_name,
            )

            tool = self.tools.get(tool_name)
            if not tool:
                step = StepResult(
                    task_id=task.id,
                    task_name=task.name,
                    tool_name=tool_name,
                    result=ToolResult(success=False, error=f"Tool not found: {tool_name}"),
                    reasoning="Tool missing from registry",
                )
                task.status = TaskStatus.FAILED
            else:
                step = self.executor.run(task, tool, memory)

            steps.append(step)
            eval_result = self.evaluator.evaluate_step(task, step, goal, memory)
            evaluations.append(eval_result)

            self._logger.log(
                "evaluate",
                f"Step evaluation: score={eval_result.score:.2f} passed={eval_result.passed}",
                task_id=task.id,
                feedback=eval_result.feedback,
            )

            if step.result.success:
                completed_task_ids.add(task.id)

            if eval_result.should_retry and eval_result.retry_task_id:
                retry_task = next((t for t in plan.tasks if t.id == eval_result.retry_task_id), None)
                if retry_task and retry_task.id not in completed_task_ids:
                    retry_tool_name = retry_task.tool_name or self.tool_selector.select(
                        retry_task, self.tools, memory
                    )
                    retry_tool = self.tools.get(retry_tool_name)
                    if retry_tool:
                        retry_step = self.executor.run(retry_task, retry_tool, memory)
                        steps.append(retry_step)
                        completed_task_ids.add(retry_task.id) if retry_step.result.success else None

        final_eval = self.evaluator.evaluate_final(goal, steps, memory)
        evaluations.append(final_eval)

        failed = sum(1 for s in steps if not s.result.success)
        run.steps = steps
        run.evaluations = evaluations
        run.decisions = self._logger.decisions
        run.final_output = memory.context
        run.completed_at = datetime.now(timezone.utc)

        if failed == 0 and final_eval.passed:
            run.status = "completed"
        elif failed < len(steps):
            run.status = "partial"
        else:
            run.status = "failed"

        self._logger.log(
            "complete",
            f"Agent run {run.status}",
            run_id=run.run_id,
            steps=len(steps),
            final_score=final_eval.score,
        )
        self._logger.persist_run(run)
        return run
