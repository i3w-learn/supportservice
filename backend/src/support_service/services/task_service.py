"""Cloud Tasks: work that has to happen after the request that caused it.

Cloud Run freezes the CPU once a response is sent, so "download this photo"
or "check this ticket in 24 hours" is handed to Cloud Tasks, which calls back
into /tasks/* (tasks_controller) right away, or at `at`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2

SECRET_HEADER = "X-Tasks-Secret"

log = logging.getLogger(__name__)
_client: tasks_v2.CloudTasksClient | None = None


def enqueue(path: str, payload: dict[str, Any], *, at: datetime | None = None) -> None:
    """Never raises: a lost task costs one photo or one reminder, but raising
    here would fail the whole inbound message it was queued from."""
    try:
        _create(path, payload, at)
    except Exception:
        log.exception("Could not enqueue task %s", path)


def _create(path: str, payload: dict[str, Any], at: datetime | None) -> None:
    global _client
    if _client is None:
        _client = tasks_v2.CloudTasksClient()

    parent = _client.queue_path(
        os.environ["GOOGLE_CLOUD_PROJECT"],
        os.environ.get("TASKS_LOCATION", "asia-south1"),
        os.environ.get("TASKS_QUEUE", "support-tasks"),
    )
    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=os.environ["SERVICE_URL"] + path,
            headers={
                "Content-Type": "application/json",
                SECRET_HEADER: os.environ["WEBHOOK_SECRET"],
            },
            body=json.dumps(payload).encode(),
        )
    )
    if at is not None:
        schedule = timestamp_pb2.Timestamp()
        schedule.FromDatetime(at)
        task.schedule_time = schedule

    _client.create_task(parent=parent, task=task)
