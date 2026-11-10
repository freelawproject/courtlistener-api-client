"""Integration tests for the Tags and DocketTags helpers.

Like the alert tests, one sequential lifecycle per resource, starting
with a sweep: a tag left behind by an interrupted run would make every
later ``create`` 400, since names are unique per user.
"""

from contextlib import suppress

import pytest

from courtlistener.exceptions import CourtListenerAPIError


@pytest.mark.integration
class TestTagsIntegration:
    """Tag and docket-tag lifecycle against docket 68571705 (a known
    docket), with a private tag."""

    NAME = "sdk-test-lifecycle"
    DOCKET_ID = 68571705

    def _sweep(self, client):
        for orphan in client.tags.list(name=self.NAME, published=False):
            client.tags.delete(orphan["id"])

    def test_tag_lifecycle(self, client):
        self._sweep(client)
        tag = None
        stage = "create"
        try:
            tag = client.tags.create(name=self.NAME, title="SDK test")
            assert tag["name"] == self.NAME
            assert tag["published"] is False

            stage = "create-duplicate"
            with pytest.raises(CourtListenerAPIError) as excinfo:
                client.tags.create(name=self.NAME)
            assert excinfo.value.status_code == 400
            assert "unique set" in str(excinfo.value.detail)

            stage = "update"
            updated = client.tags.update(tag["id"], description="Updated")
            assert updated["description"] == "Updated"

            stage = "add"
            added = client.docket_tags.add(tag["id"], self.DOCKET_ID)
            assert added["tag"] == tag["id"]
            assert added["docket"] == self.DOCKET_ID
            assert "already_tagged" not in added

            stage = "add-idempotent"
            again = client.docket_tags.add(tag["id"], self.DOCKET_ID)
            assert again["id"] == added["id"]
            assert again["already_tagged"] is True

            stage = "remove"
            client.docket_tags.remove(tag["id"], self.DOCKET_ID)

            stage = "remove-when-absent"
            with pytest.raises(ValueError):
                client.docket_tags.remove(tag["id"], self.DOCKET_ID)

            stage = "delete"
            client.tags.delete(tag["id"])

            stage = "verify-delete"
            with pytest.raises(CourtListenerAPIError) as excinfo:
                client.tags.get(tag["id"])
            assert excinfo.value.status_code == 404
            tag = None
        except CourtListenerAPIError as exc:
            pytest.fail(f"tag lifecycle failed at stage {stage!r}: {exc}")
        finally:
            if tag is not None:
                with suppress(CourtListenerAPIError):
                    client.tags.delete(tag["id"])
