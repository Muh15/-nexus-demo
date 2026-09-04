from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.action_executor import ActionExecutor, draft_email_handler
from core.planner import action_fingerprint, plan_action
from core.runtime import build_runtime
from core.verifier import ActionVerifier, draft_email_verifier

# ...

def test_action_executor_blocks_until_approval_and_then_executes_safe_draft():
    plan = plan_action("إعداد مسودة تفاوض", target="ABC Industrial")
    executor = ActionExecutor({"draft_email": draft_email_handler})
    awaiting = executor.execute(plan)
    assert awaiting.status == "awaiting_approval"
    fingerprint = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
    plan.payload.update({"approved": True, "approved_fingerprint": fingerprint, "approved_by_subject": "approver-1"})
    completed = executor.execute(plan, actor_subject="executor-1")
    assert completed.status == "completed"
    assert completed.output["sent"] is False


def test_action_verifier_confirms_safe_draft_execution():
    plan = plan_action("إعداد مسودة تفاوض", target="ABC Industrial")
    fingerprint = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
    plan.payload.update({"approved": True, "approved_fingerprint": fingerprint, "approved_by_subject": "approver-1"})
    result = ActionExecutor({"draft_email": draft_email_handler}).execute(plan, actor_subject="executor-1")
    verification = ActionVerifier({"draft_email": draft_email_verifier}).verify(result)
    assert verification.status == "verified"
    assert verification.details["sent"] is False


# The remaining smoke tests are defined elsewhere in the file.
