"""Automation run recording: one record per workflow execution, plus per-agent metrics."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import storage
from .util import new_id, utcnow_iso

MAX_LOG_LINES = 500
MAX_RUNS_KEPT = 500


class RunRecorder:
    def __init__(self, workflow: str, trigger: str | None = None):
        self.id = new_id("run")
        self.workflow = workflow
        self.trigger = trigger or _detect_trigger()
        self.started_at = utcnow_iso()
        self._t0 = time.monotonic()
        self.log: list[dict[str, str]] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.content_ids: list[str] = []
        self.agent_events: list[dict[str, Any]] = []
        self.client = None  # OpenRouterClient, attached by the pipeline for usage totals

    def info(self, message: str) -> None:
        self._add("info", message)

    def warn(self, message: str) -> None:
        self.warnings.append(message[:500])
        self._add("warning", message)

    def error(self, message: str) -> None:
        self.errors.append(message[:500])
        self._add("error", message)

    def say(self, level: str, message: str) -> None:
        {"warning": self.warn, "error": self.error}.get(level, self.info)(message)

    def _add(self, level: str, message: str) -> None:
        print(f"[{level.upper():7}] {message}", flush=True)
        if len(self.log) < MAX_LOG_LINES:
            self.log.append({"at": utcnow_iso(), "level": level, "message": message[:1000]})

    def agent_result(self, agent: str, ok: bool, tokens: int | None, error: str | None = None) -> None:
        self.agent_events.append({"agent": agent, "ok": ok, "tokens": tokens or 0, "error": error,
                                  "at": utcnow_iso()})

    def record(self, status: str) -> dict[str, Any]:
        totals = getattr(self.client, "totals", None)
        return {
            "id": self.id, "workflow": self.workflow,
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_url": _github_run_url(),
            "trigger": self.trigger, "started_at": self.started_at, "completed_at": utcnow_iso(),
            "duration_ms": int((time.monotonic() - self._t0) * 1000), "status": status,
            "ai_requests": totals.requests if totals else 0,
            "tokens": {"prompt": totals.prompt_tokens if totals else None,
                       "completion": totals.completion_tokens if totals else None,
                       "total": totals.total_tokens if totals else None},
            "models": list(totals.models) if totals else [],
            "content_ids": self.content_ids, "errors": self.errors, "warnings": self.warnings, "log": self.log,
        }

    def save(self, status: str) -> None:
        with storage.transaction("automation_runs") as doc:
            doc["items"].append(self.record(status))
            if len(doc["items"]) > MAX_RUNS_KEPT:
                del doc["items"][: len(doc["items"]) - MAX_RUNS_KEPT]
        if self.agent_events:
            with storage.transaction("agent_metrics") as doc:
                for ev in self.agent_events:
                    stat = doc["agents"].setdefault(ev["agent"], {"executions": 0, "successes": 0, "failures": 0,
                                                                  "total_tokens": 0})
                    stat["executions"] += 1
                    stat["successes" if ev["ok"] else "failures"] += 1
                    stat["total_tokens"] = stat.get("total_tokens", 0) + ev["tokens"]
                    stat["last_execution_at"] = ev["at"]
                    stat["last_status"] = "success" if ev["ok"] else "failed"
                    stat["last_error"] = (ev["error"] or "")[:300] or None


@contextmanager
def recorded_run(workflow: str, trigger: str | None = None) -> Iterator[RunRecorder]:
    """Always persists a run record, even if the body raises."""
    rec = RunRecorder(workflow, trigger)
    rec.info(f"run {rec.id} started ({workflow}, trigger={rec.trigger})")
    status = "failed"
    try:
        yield rec
        status = "partial" if rec.errors else "success"
    except Exception as exc:
        rec.error(f"run aborted: {type(exc).__name__}: {exc}")
        raise
    finally:
        rec.info(f"run finished with status {status}")
        try:
            rec.save(status)
        except Exception as exc:  # never mask the original error
            print(f"[ERROR  ] could not save run record: {exc}", flush=True)


def _detect_trigger() -> str:
    event = os.environ.get("GITHUB_EVENT_NAME")
    if not event:
        return "local"
    if event == "workflow_dispatch" and os.environ.get("TEKTIZEN_TRIGGER") == "dashboard":
        return "dashboard"
    return event if event in {"schedule", "workflow_dispatch", "push"} else "workflow_dispatch"


def _github_run_url() -> str | None:
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None
