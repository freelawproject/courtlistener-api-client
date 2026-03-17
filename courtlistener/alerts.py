from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from courtlistener.models.endpoints.alerts import AlertsEndpoint
from courtlistener.models.endpoints.docket_alerts import (
    DocketAlertsEndpoint,
)
from courtlistener.resource import Resource
from courtlistener.utils import choice_validator

if TYPE_CHECKING:
    from courtlistener.client import CourtListener

# ---------------------------------------------------------------------------
# Pydantic models for create/update validation
# ---------------------------------------------------------------------------

_RATE_CHOICES = [
    {"value": "rt", "display_name": "Real Time"},
    {"value": "dly", "display_name": "Daily"},
    {"value": "wly", "display_name": "Weekly"},
    {"value": "mly", "display_name": "Monthly"},
    {"value": "off", "display_name": "Off"},
]

_SEARCH_ALERT_TYPE_CHOICES = [
    {"value": "d", "display_name": "Dockets only"},
    {"value": "r", "display_name": "Dockets and filings"},
]

_DOCKET_ALERT_TYPE_CHOICES = [
    {"value": 0, "display_name": "Unsubscription"},
    {"value": 1, "display_name": "Subscription"},
]


class SearchAlertCreate(BaseModel):
    """Validation model for creating a search alert."""

    model_config = ConfigDict(extra="forbid")

    name: str
    query: str
    rate: Annotated[
        str,
        Field(json_schema_extra={"choices": _RATE_CHOICES}),
        BeforeValidator(choice_validator),
    ]
    alert_type: Annotated[
        str | None,
        Field(
            None,
            json_schema_extra={"choices": _SEARCH_ALERT_TYPE_CHOICES},
        ),
        BeforeValidator(choice_validator),
    ]


class SearchAlertUpdate(BaseModel):
    """Validation model for updating a search alert."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(None)]
    query: Annotated[str | None, Field(None)]
    rate: Annotated[
        str | None,
        Field(
            None,
            json_schema_extra={"choices": _RATE_CHOICES},
        ),
        BeforeValidator(choice_validator),
    ]
    alert_type: Annotated[
        str | None,
        Field(
            None,
            json_schema_extra={"choices": _SEARCH_ALERT_TYPE_CHOICES},
        ),
        BeforeValidator(choice_validator),
    ]


class DocketAlertCreate(BaseModel):
    """Validation model for creating a docket alert."""

    model_config = ConfigDict(extra="forbid")

    docket: int
    alert_type: Annotated[
        int,
        Field(
            1,
            json_schema_extra={"choices": _DOCKET_ALERT_TYPE_CHOICES},
        ),
        BeforeValidator(choice_validator),
    ]


class DocketAlertUpdate(BaseModel):
    """Validation model for updating a docket alert."""

    model_config = ConfigDict(extra="forbid")

    alert_type: Annotated[
        int | None,
        Field(
            None,
            json_schema_extra={"choices": _DOCKET_ALERT_TYPE_CHOICES},
        ),
        BeforeValidator(choice_validator),
    ]


# ---------------------------------------------------------------------------
# Resource subclasses
# ---------------------------------------------------------------------------


class SearchAlerts(Resource[AlertsEndpoint]):
    """Helper for managing search alerts.

    Provides CRUD operations on the /alerts/ endpoint with
    client-side validation via pydantic models.
    """

    def __init__(self, client: CourtListener) -> None:
        super().__init__(client, AlertsEndpoint)

    def create(
        self,
        name: str,
        query: str,
        rate: str,
        alert_type: str | None = None,
    ) -> dict[str, Any]:
        """Create a new search alert.

        Args:
            name: A descriptive name for the alert.
            query: The search query string.
            rate: Notification rate (rt, dly, wly, mly, off).
            alert_type: Optional alert type (d or r).

        Returns:
            The created alert as a dictionary.

        Raises:
            ValidationError: If any field value is invalid.
        """
        validated = SearchAlertCreate(
            name=name, query=query, rate=rate, alert_type=alert_type
        )
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            self._client._request("POST", self._endpoint, json=body),
        )

    def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing search alert.

        Args:
            id: The alert ID.
            **data: Fields to update (e.g. name, query, rate,
                alert_type).

        Returns:
            The updated alert as a dictionary.

        Raises:
            ValidationError: If any field value is invalid.
        """
        validated = SearchAlertUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    def delete(self, id: int) -> None:
        """Delete a search alert.

        Args:
            id: The alert ID to delete.
        """
        self._client._request("DELETE", f"{self._endpoint}{id}/")


class DocketAlerts(Resource[DocketAlertsEndpoint]):
    """Helper for managing docket alerts (subscriptions).

    Provides CRUD operations on the /docket-alerts/ endpoint with
    client-side validation via pydantic models.
    """

    def __init__(self, client: CourtListener) -> None:
        super().__init__(client, DocketAlertsEndpoint)

    def create(self, docket: int, alert_type: int = 1) -> dict[str, Any]:
        """Create a new docket alert.

        Args:
            docket: The docket ID to subscribe to.
            alert_type: 0 for unsubscription, 1 for subscription.

        Returns:
            The created docket alert as a dictionary.

        Raises:
            ValidationError: If *alert_type* is invalid.
        """
        validated = DocketAlertCreate(docket=docket, alert_type=alert_type)
        return cast(
            dict[str, Any],
            self._client._request(
                "POST", self._endpoint, json=validated.model_dump()
            ),
        )

    def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing docket alert.

        Args:
            id: The docket alert ID.
            **data: Fields to update (e.g. alert_type).

        Returns:
            The updated docket alert as a dictionary.

        Raises:
            ValidationError: If *alert_type* in *data* is invalid.
        """
        validated = DocketAlertUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    def delete(self, id: int) -> None:
        """Delete a docket alert.

        Args:
            id: The docket alert ID to delete.
        """
        self._client._request("DELETE", f"{self._endpoint}{id}/")

    def subscribe(self, docket: int) -> dict[str, Any]:
        """Subscribe to a docket (convenience for create with type=1).

        Args:
            docket: The docket ID to subscribe to.

        Returns:
            The created subscription as a dictionary.
        """
        return self.create(docket, alert_type=1)

    def unsubscribe(self, docket: int) -> None:
        """Unsubscribe from a docket by docket ID.

        Looks up the alert for the given docket and deletes it.
        Symmetric with :meth:`subscribe`.

        Args:
            docket: The docket ID to unsubscribe from.

        Raises:
            ValueError: If no alert exists for the given docket.
        """
        results = self.list(docket=docket)
        for alert in results:
            self.delete(alert["id"])
            return
        raise ValueError(f"No docket alert found for docket {docket}")
