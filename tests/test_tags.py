"""Integration tests for the Tags and DocketTags helpers.

Like the alert tests, one sequential lifecycle, starting with a sweep: a
tag left behind by an interrupted run would make every later ``create``
400, since names are unique per user.
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

            stage = "update"
            updated = client.tags.update(tag["id"], description="Updated")
            assert updated["description"] == "Updated"
            assert updated["title"] == "SDK test"

            stage = "add-docket"
            docket_tag = client.docket_tags.create(tag["id"], self.DOCKET_ID)
            assert docket_tag["tag"] == tag["id"]
            assert docket_tag["docket"] == self.DOCKET_ID

            stage = "find-docket-tag"
            found = list(
                client.docket_tags.list(tag=tag["id"], docket=self.DOCKET_ID)
            )
            assert [d["id"] for d in found] == [docket_tag["id"]]

            stage = "remove-docket"
            client.docket_tags.delete(docket_tag["id"])
            assert not list(
                client.docket_tags.list(tag=tag["id"], docket=self.DOCKET_ID)
            )

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
