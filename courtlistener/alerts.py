from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from urllib.parse import parse_qs, urlencode

from pydantic import BaseModel, BeforeValidator, ConfigDict

from courtlistener.models.endpoints.alerts import AlertsEndpoint
from courtlistener.models.endpoints.docket_alerts import (
    DocketAlertsEndpoint,
)
from courtlistener.resource import Resource
from courtlistener.utils import (
    flatten_filters,
    search_model_validator,
    unflatten_filters,
)

if TYPE_CHECKING:
    from courtlistener.client import CourtListener

# ---------------------------------------------------------------------------
# Pydantic models for create/update validation
# ---------------------------------------------------------------------------

RateType = Literal["rt", "dly", "wly", "mly", "off"]
SearchAlertType = Literal["o", "r", "d", "oa"]
DocketAlertType = Literal[0, 1]


def normalize_search_query(query: str | dict[str, Any] | None) -> str | None:
    """Normalize and validate a search query, returning a URL query string.

    Accepts either a URL query string (e.g. ``"q=test&court=scotus"``)
    or a structured dict (e.g. ``{"q": "test", "court": "scotus"}``).
    In both cases the query is validated against the ``SearchEndpoint``
    model via ``search_model_validator`` and serialized back to a
    canonical query string.
    """
    if query is None:
        return None
    if isinstance(query, str):
        parsed = parse_qs(query, keep_blank_values=True)
        params = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    else:
        params = dict(query)

    params = unflatten_filters(params)
    params.setdefault("type", "o")
    validated = search_model_validator(params)
    flat = flatten_filters(validated)
    flat = {k: v for k, v in flat.items() if v is not None}

    return urlencode(flat, doseq=True)


class SearchAlertCreate(BaseModel):
    """Validation model for creating a search alert."""

    model_config = ConfigDict(extra="forbid")

    name: str
    query: Annotated[
        str | dict[str, Any] | None,
        BeforeValidator(normalize_search_query),
    ]
    rate: RateType
    alert_type: SearchAlertType | None = None


class SearchAlertUpdate(BaseModel):
    """Validation model for updating a search alert."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    query: Annotated[
        str | dict[str, Any] | None,
        BeforeValidator(normalize_search_query),
    ] = None
    rate: RateType | None = None
    alert_type: SearchAlertType | None = None


class DocketAlertCreate(BaseModel):
    """Validation model for creating a docket alert."""

    model_config = ConfigDict(extra="forbid")

    docket: int
    alert_type: DocketAlertType = 1


class DocketAlertUpdate(BaseModel):
    """Validation model for updating a docket alert."""

    model_config = ConfigDict(extra="forbid")

    alert_type: DocketAlertType | None = None


# ---------------------------------------------------------------------------
# Resource subclasses
# ---------------------------------------------------------------------------


class SearchAlerts(Resource):
    """Helper for managing search alerts."""

    def __init__(self, client: CourtListener) -> None:
        super().__init__(client, AlertsEndpoint)

    def create(
        self,
        name: str,
        query: str | dict[str, Any],
        rate: RateType,
        alert_type: SearchAlertType | None = None,
    ) -> dict[str, Any]:
        """Create a new search alert."""
        validated = SearchAlertCreate(
            name=name, query=query, rate=rate, alert_type=alert_type
        )
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            self._client._request("POST", self._endpoint, json=body),
        )

    def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing search alert."""
        validated = SearchAlertUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    def delete(self, id: int) -> None:
        """Delete a search alert."""
        self._client._request("DELETE", f"{self._endpoint}{id}/")


class DocketAlerts(Resource):
    """Helper for managing docket alerts (subscriptions)."""

    def __init__(self, client: CourtListener) -> None:
        super().__init__(client, DocketAlertsEndpoint)

    def create(
        self, docket: int, alert_type: DocketAlertType = 1
    ) -> dict[str, Any]:
        """Create a new docket alert."""
        validated = DocketAlertCreate(docket=docket, alert_type=alert_type)
        return cast(
            dict[str, Any],
            self._client._request(
                "POST", self._endpoint, json=validated.model_dump()
            ),
        )

    def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing docket alert."""
        validated = DocketAlertUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    def delete(self, id: int) -> None:
        """Delete a docket alert."""
        self._client._request("DELETE", f"{self._endpoint}{id}/")

    def subscribe(self, docket: int) -> dict[str, Any]:
        """Subscribe to a docket (convenience for create with type=1)."""
        for alert in self.list(docket=docket):
            return {**alert, "already_subscribed": True}

        return self.create(docket, alert_type=1)

    def unsubscribe(self, docket: int) -> None:
        """Unsubscribe from a docket by docket ID.

        Looks up the alert for the given docket and deletes it.
        Symmetric with :meth:`subscribe`.
        """
        results = self.list(docket=docket)
        for alert in results:
            self.delete(alert["id"])
            return
        raise ValueError(f"No docket alert found for docket {docket}")
