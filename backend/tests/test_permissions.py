from app.core.permissions import Decision, PermissionMode, hash_params


async def test_default_mode_allows(core):
    decision = core.permissions.request("notes.read", "get_note", {"note_id": "1"}, PermissionMode.ALLOW, "00000000-0000-4000-8000-000000000001")
    assert decision.allowed


async def test_forbid_denies(core):
    core.permissions.set_rule("notes.delete", PermissionMode.FORBID, "00000000-0000-4000-8000-000000000001")
    decision = core.permissions.request("notes.delete", "delete_note", {"note_id": "1"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001")
    assert decision.mode == PermissionMode.FORBID
    assert not decision.allowed


async def test_confirm_flow_requires_approval(core):
    decision = core.permissions.request("notes.delete", "delete_note", {"note_id": "n1"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001", "РЈРґР°Р»РёС‚СЊ Р·Р°РјРµС‚РєСѓ")
    assert decision.needs_confirmation
    assert decision.confirmation_id is not None

    pending = core.permissions.pending("00000000-0000-4000-8000-000000000001")
    assert len(pending) == 1

    core.permissions.resolve(decision.confirmation_id, approve=True, user_id="00000000-0000-4000-8000-000000000001")

    decision2 = core.permissions.request("notes.delete", "delete_note", {"note_id": "n1"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001")
    assert decision2.allowed


async def test_confirm_requires_matching_params(core):
    core.permissions.request("notes.delete", "delete_note", {"note_id": "n1"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001", "")
    confirmed_records = core.permissions.pending("00000000-0000-4000-8000-000000000001")
    core.permissions.resolve(confirmed_records[0].id, approve=True, user_id="00000000-0000-4000-8000-000000000001")

    other = core.permissions.request("notes.delete", "delete_note", {"note_id": "n2"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001")
    assert other.needs_confirmation


async def test_deny_does_not_allow(core):
    decision = core.permissions.request("notes.delete", "delete_note", {"note_id": "n1"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001")
    core.permissions.resolve(decision.confirmation_id, approve=False, user_id="00000000-0000-4000-8000-000000000001")
    decision2 = core.permissions.request("notes.delete", "delete_note", {"note_id": "n1"}, PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001")
    assert decision2.needs_confirmation


async def test_rule_override_and_reset(core):
    core.permissions.set_rule("notifications.send", PermissionMode.ALLOW, "00000000-0000-4000-8000-000000000001")
    assert core.permissions.mode_for("notifications.send", PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001") == PermissionMode.ALLOW
    core.permissions.reset_rule("notifications.send", "00000000-0000-4000-8000-000000000001")
    assert core.permissions.mode_for("notifications.send", PermissionMode.CONFIRM, "00000000-0000-4000-8000-000000000001") == PermissionMode.CONFIRM


def test_hash_stable():
    assert hash_params({"a": 1}) == hash_params({"a": 1})
    assert hash_params({"a": 1}) != hash_params({"a": 2})
