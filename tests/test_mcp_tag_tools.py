"""Tests for the tag MCP tools."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.add_docket_to_tag_tool import AddDocketToTagTool
from courtlistener.mcp.tools.create_tag_tool import CreateTagTool
from courtlistener.mcp.tools.delete_tag_tool import DeleteTagTool
from courtlistener.mcp.tools.remove_docket_from_tag_tool import (
    RemoveDocketFromTagTool,
)
from courtlistener.mcp.tools.update_tag_tool import UpdateTagTool

pytestmark = pytest.mark.asyncio

TAG = {"id": 5, "name": "patents", "published": False}
DOCKET_TAG = {"id": 9, "tag": 5, "docket": 123}
DUPLICATE = {
    "non_field_errors": ["The fields user, name must make a unique set."]
}


def _api_error(status_code: int, detail) -> CourtListenerAPIError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return CourtListenerAPIError(status_code, detail, response)


def _client_cm(client):
    cm = MagicMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = False
    return cm


def _tool(monkeypatch, tool_cls, method, result):
    """A tool whose client's *method* (``"tags.create"``) returns or
    raises *result*."""
    client = AsyncMock()
    mock = AsyncMock()
    if isinstance(result, BaseException):
        mock.side_effect = result
    else:
        mock.return_value = result
    resource, name = method.split(".")
    setattr(getattr(client, resource), name, mock)
    tool = tool_cls()
    monkeypatch.setattr(
        type(tool), "get_client", lambda self: _client_cm(client)
    )
    return tool, mock


class TestCreateTag:
    async def test_creates_the_tag(self, monkeypatch):
        tool, create = _tool(monkeypatch, CreateTagTool, "tags.create", TAG)

        result = await tool.call({"name": "patents", "title": "Patents"})

        create.assert_awaited_once_with(
            name="patents", title="Patents", description=None, published=None
        )
        assert result == TAG

    async def test_duplicate_name_returns_clean_message(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch,
            CreateTagTool,
            "tags.create",
            _api_error(400, DUPLICATE),
        )

        result = await tool.call({"name": "patents"})

        assert result == "You already have a tag named 'patents'."

    async def test_other_400_returns_detail(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch,
            CreateTagTool,
            "tags.create",
            _api_error(400, {"name": ["Enter a valid slug."]}),
        )

        result = await tool.call({"name": "patents"})

        assert result.startswith("Could not create tag:")
        assert "valid slug" in result

    async def test_server_error_still_raises(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch, CreateTagTool, "tags.create", _api_error(500, "boom")
        )

        with pytest.raises(CourtListenerAPIError):
            await tool.call({"name": "patents"})

    @pytest.mark.parametrize("name", ["two words", "a/b", "x" * 51])
    async def test_schema_rejects_names_that_are_not_slugs(self, name):
        errors = list(
            CreateTagTool().input_validator.iter_errors({"name": name})
        )
        assert errors

    async def test_schema_accepts_a_slug(self):
        validator = CreateTagTool().input_validator
        assert not list(validator.iter_errors({"name": "patent-cases_2"}))


class TestUpdateTag:
    async def test_passes_only_the_fields_given(self, monkeypatch):
        tool, update = _tool(monkeypatch, UpdateTagTool, "tags.update", TAG)

        await tool.call({"tag_id": 5, "published": True, "description": ""})

        update.assert_awaited_once_with(5, published=True, description="")

    async def test_nothing_to_change(self, monkeypatch):
        tool, update = _tool(monkeypatch, UpdateTagTool, "tags.update", TAG)

        result = await tool.call({"tag_id": 5})

        update.assert_not_awaited()
        assert result.startswith("Nothing to change")

    @pytest.mark.parametrize(
        "status, message",
        [
            (404, "No tag found with id 5."),
            (403, "Tag 5 belongs to another user."),
        ],
    )
    async def test_a_tag_the_user_cannot_change(
        self, monkeypatch, status, message
    ):
        tool, _ = _tool(
            monkeypatch,
            UpdateTagTool,
            "tags.update",
            _api_error(status, {"detail": "…"}),
        )

        result = await tool.call({"tag_id": 5, "title": "x"})

        assert result.startswith(message)

    async def test_rename_to_a_taken_name(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch,
            UpdateTagTool,
            "tags.update",
            _api_error(400, DUPLICATE),
        )

        result = await tool.call({"tag_id": 5, "name": "taken"})

        assert result == "You already have a tag named 'taken'."


class TestDeleteTag:
    async def test_deletes_the_tag(self, monkeypatch):
        tool, delete = _tool(monkeypatch, DeleteTagTool, "tags.delete", None)

        result = await tool.call({"tag_id": 5})

        delete.assert_awaited_once_with(5)
        assert result == "Deleted tag 5."

    @pytest.mark.parametrize(
        "status, message",
        [
            (404, "No tag found with id 5."),
            (403, "Tag 5 belongs to another user."),
        ],
    )
    async def test_a_tag_the_user_cannot_delete(
        self, monkeypatch, status, message
    ):
        tool, _ = _tool(
            monkeypatch,
            DeleteTagTool,
            "tags.delete",
            _api_error(status, {"detail": "…"}),
        )

        assert (await tool.call({"tag_id": 5})).startswith(message)

    async def test_server_error_still_raises(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch, DeleteTagTool, "tags.delete", _api_error(500, "boom")
        )

        with pytest.raises(CourtListenerAPIError):
            await tool.call({"tag_id": 5})


class TestAddDocketToTag:
    async def test_adds_the_docket(self, monkeypatch):
        tool, add = _tool(
            monkeypatch, AddDocketToTagTool, "docket_tags.add", DOCKET_TAG
        )

        result = await tool.call({"tag_id": 5, "docket_id": 123})

        add.assert_awaited_once_with(5, 123)
        assert result == DOCKET_TAG

    @pytest.mark.parametrize(
        "detail, message",
        [
            (
                {"tag": ['Invalid pk "5" - object does not exist.']},
                "You have no tag with id 5.",
            ),
            (
                {"docket": ['Invalid pk "123" - object does not exist.']},
                "No docket found with id 123.",
            ),
            (
                {
                    "non_field_errors": [
                        "The fields docket, tag must make a unique set."
                    ]
                },
                "Docket 123 is already in tag 5.",
            ),
            ("Bad request", "Could not add docket 123 to tag 5: Bad request"),
        ],
    )
    async def test_400s_return_clean_messages(
        self, monkeypatch, detail, message
    ):
        tool, _ = _tool(
            monkeypatch,
            AddDocketToTagTool,
            "docket_tags.add",
            _api_error(400, detail),
        )

        result = await tool.call({"tag_id": 5, "docket_id": 123})

        assert result.startswith(message)

    async def test_server_error_still_raises(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch,
            AddDocketToTagTool,
            "docket_tags.add",
            _api_error(503, "down"),
        )

        with pytest.raises(CourtListenerAPIError):
            await tool.call({"tag_id": 5, "docket_id": 123})


class TestRemoveDocketFromTag:
    async def test_removes_the_docket(self, monkeypatch):
        tool, remove = _tool(
            monkeypatch, RemoveDocketFromTagTool, "docket_tags.remove", None
        )

        result = await tool.call({"tag_id": 5, "docket_id": 123})

        remove.assert_awaited_once_with(5, 123)
        assert result == "Removed docket 123 from tag 5."

    async def test_docket_not_in_tag(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch,
            RemoveDocketFromTagTool,
            "docket_tags.remove",
            ValueError("Docket 123 is not in tag 5"),
        )

        result = await tool.call({"tag_id": 5, "docket_id": 123})

        assert result == "Docket 123 isn't in tag 5."

    async def test_another_users_tag(self, monkeypatch):
        tool, _ = _tool(
            monkeypatch,
            RemoveDocketFromTagTool,
            "docket_tags.remove",
            _api_error(403, {"detail": "…"}),
        )

        result = await tool.call({"tag_id": 5, "docket_id": 123})

        assert result.startswith("Tag 5 belongs to another user.")
