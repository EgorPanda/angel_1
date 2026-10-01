import pytest

from app.core.errors import PermissionDenied, ValidationError
from app.core.permissions import PermissionMode
from app.core.tools import Tool, ToolRegistry, ToolContext, ToolResult


class DummyTool(Tool):
    module = "notes"
    name = "dummy_create"
    description = "dummy"
    permission = "notes.create"

    async def run(self, validated, ctx):
        return {"id": "ok"}


class InvalidTool(Tool):
    module = "notes"
    name = "dummy_dup"
    description = "duplicate"
    permission = "notes.create"


async def test_registry_register_get_list(core):
    registry = ToolRegistry()
    tool = DummyTool()
    assert registry.get("dummy_create") is None
    registry.register(tool)
    assert registry.get("dummy_create") is tool
    assert "dummy_create" in [t.name for t in registry.list()]
    registry.unregister("dummy_create")
    assert registry.get("dummy_create") is None
    with pytest.raises(KeyError):
        registry.require("nope")


async def test_tool_validation_error(core):
    class SchemaTool(Tool):
        module = "notes"
        name = "schema_tool"
        description = "d"
        permission = "notes.create"
        input_schema = None
        async def run(self, validated, ctx):
            return validated

    from pydantic import BaseModel, Field

    class Input(BaseModel):
        title: str = Field(min_length=1)

    SchemaTool.input_schema = Input
    tool = SchemaTool()
    ctx = ToolContext(user_id="u", correlation_id="c", core=core)
    with pytest.raises(ValidationError):
        await tool.execute({"title": ""}, ctx)
    with pytest.raises(ValidationError):
        await tool.execute("not-a-dict", ctx)


async def test_tool_execute_calls_service(core):
    tool = DummyTool()
    ctx = ToolContext(user_id=core.user_id(), correlation_id="c1", core=core)
    result = await tool.execute({"title": "x"}, ctx)
    assert result.success
    assert result.data == {"id": "ok"}


async def test_forbidden_tool_raises(core):
    core.permissions.set_rule("notes.create", "forbid", core.user_id())

    class F(Tool):
        module = "notes"
        name = "f_tool"
        description = "f"
        permission = "notes.create"
        async def run(self, validated, ctx):
            return {}

    ctx = ToolContext(user_id=core.user_id(), correlation_id="c", core=core)
    with pytest.raises(PermissionDenied):
        await F().execute({}, ctx)
    core.permissions.reset_rule("notes.create", core.user_id())


async def test_confirmation_tool_returns_needs_confirmation(core):
    class DeleteTool(Tool):
        module = "notes"
        name = "del_tool"
        description = "del"
        permission = "notes.delete"
        default_mode = PermissionMode.CONFIRM
        async def run(self, validated, ctx):
            return {"deleted": True}

    ctx = ToolContext(user_id=core.user_id(), correlation_id="c", core=core)
    out = await DeleteTool().execute({"note_id": "1"}, ctx)
    assert out.needs_confirmation
    assert out.confirmation_id is not None


async def test_create_note_tool_via_ai_tool(core):
    from app.modules.notes import tools as notes_tools

    service = core.get_module("notes").service
    tool_list = notes_tools.build_tools(service)
    create_tool = next(t for t in tool_list if t.name == "create_note")
    ctx = ToolContext(user_id=core.user_id(), correlation_id="c", core=core)
    result = await create_tool.execute({"title": "Тул-заметка", "tags": ["tool"]}, ctx)
    assert result.success
    assert result.data["title"] == "Тул-заметка"
    notes = service.search(query="Тул-заметка")
    assert len(notes) == 1