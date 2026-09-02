from __future__ import annotations

import pytest

from core.authorization import authorize_approval, authorize_execution
from core.auth import ActorRole
from core.action_executor import ActionExecutor, draft_email_handler
from core.planner import plan_action


def test_operator_can_execute_allowed_action_for_matching_tenant():
    plan = plan_action("draft", target="ops", action_type="draft_email")
    plan.payload["tenant_id"] = "tenant-a"
    result = authorize_execution("draft_email", tenant_id="tenant-a", plan_tenant_id="tenant-a", actor_role=ActorRole.OPERATOR.value)
    assert result.allowed


def test_viewer_cannot_execute_action():
    result = authorize_execution("update_crm", tenant_id="tenant-a", plan_tenant_id="tenant-a", actor_role=ActorRole.VIEWER.value)
    assert not result.allowed


def test_tenant_mismatch_is_denied():
    result = authorize_execution("update_crm", tenant_id="tenant-a", plan_tenant_id="tenant-b", actor_role=ActorRole.OPERATOR.value)
    assert not result.allowed


def test_only_approver_or_admin_can_approve(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    assert authorize_approval(actor_role="approver").allowed
    assert authorize_approval(actor_role="admin").allowed
    assert not authorize_approval(actor_role="operator").allowed


def test_strict_mode_requires_authenticated_execution_context(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    result = authorize_execution("draft_email", tenant_id=None, plan_tenant_id=None, actor_role=None)
    assert not result.allowed


def test_executor_enforces_role_at_core_boundary(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    plan = plan_action("draft", target="ops", action_type="draft_email")
    plan.payload["tenant_id"] = "tenant-a"
    plan.payload["approved"] = True
    plan.payload["approved_fingerprint"] = plan.payload["action_fingerprint"]
    executor = ActionExecutor({"draft_email": draft_email_handler})
    denied = executor.execute(plan, tenant_id="tenant-a", actor_role="viewer", actor_subject="u1")
    assert denied.status == "blocked"
    allowed = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="u2")
    assert allowed.status == "completed"


def test_separation_of_duties_requires_different_actor(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_SEPARATION_OF_DUTIES", "true")
    plan = plan_action("draft", target="ops", action_type="draft_email")
    plan.payload.update({"tenant_id": "tenant-a", "approved": True, "approved_fingerprint": plan.payload["action_fingerprint"], "approved_by_subject": "same-user"})
    executor = ActionExecutor({"draft_email": draft_email_handler})
    same = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="same-user")
    assert same.status == "blocked"
    different = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="different-user")
    assert different.status == "completed"
