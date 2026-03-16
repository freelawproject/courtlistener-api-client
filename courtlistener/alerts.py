from __future__ import annotations

from typing import TYPE_CHECKING, Any

from courtlistener.models.endpoints.alerts import AlertsEndpoint
from courtlistener.models.endpoints.docket_alerts import (
    DocketAlertsEndpoint,
)
from courtlistener.resource import Resource

if TYPE_CHECKING:
    from courtlistener.client import CourtListener

VALID_RATES = {"rt", "dly", "wly", "mly", "off"}
VALID_SEARCH_ALERT_TYPES = {"d", "r"}
VALID_DOCKET_ALERT_TYPES = {0, 1}


class SearchAlerts(Resource[AlertsEndpoint]):
    """Helper for managing search alerts.

    Provides CRUD operations on the /alerts/ endpoint with
    client-side validation of ``rate`` and ``alert_type`` values.
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
            ValueError: If *rate* or *alert_type* is invalid.
        """
        _validate_rate(rate)
        if alert_type is not None:
            _validate_search_alert_type(alert_type)

        body: dict[str, Any] = {
            "name": name,
            "query": query,
            "rate": rate,
        }
        if alert_type is not None:
            body["alert_type"] = alert_type

        result = self._client._request(
            "POST", self._endpoint, json=body
        )
        assert isinstance(result, dict)
        return result

    def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing search alert.

        Args:
            id: The alert ID.
            **data: Fields to update (e.g. name, query, rate,
                alert_type).

        Returns:
            The updated alert as a dictionary.

        Raises:
            ValueError: If *rate* or *alert_type* in *data* is invalid.
        """
        if "rate" in data:
            _validate_rate(data["rate"])
        if "alert_type" in data:
            _validate_search_alert_type(data["alert_type"])

        result = self._client._request(
            "PATCH", f"{self._endpoint}{id}/", json=data
        )
        assert isinstance(result, dict)
        return result

    def delete(self, id: int) -> None:
        """Delete a search alert.

        Args:
            id: The alert ID to delete.
        """
        self._client._request("DELETE", f"{self._endpoint}{id}/")


class DocketAlerts(Resource[DocketAlertsEndpoint]):
    """Helper for managing docket alerts (subscriptions).

    Provides CRUD operations on the /docket-alerts/ endpoint with
    client-side validation of ``alert_type`` values.
    """

    def __init__(self, client: CourtListener) -> None:
        super().__init__(client, DocketAlertsEndpoint)

    def create(
        self, docket: int, alert_type: int = 1
    ) -> dict[str, Any]:
        """Create a new docket alert.

        Args:
            docket: The docket ID to subscribe to.
            alert_type: 0 for unsubscription, 1 for subscription.

        Returns:
            The created docket alert as a dictionary.

        Raises:
            ValueError: If *alert_type* is invalid.
        """
        _validate_docket_alert_type(alert_type)

        result = self._client._request(
            "POST",
            self._endpoint,
            json={"docket": docket, "alert_type": alert_type},
        )
        assert isinstance(result, dict)
        return result

    def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing docket alert.

        Args:
            id: The docket alert ID.
            **data: Fields to update (e.g. alert_type).

        Returns:
            The updated docket alert as a dictionary.

        Raises:
            ValueError: If *alert_type* in *data* is invalid.
        """
        if "alert_type" in data:
            _validate_docket_alert_type(data["alert_type"])

        result = self._client._request(
            "PATCH", f"{self._endpoint}{id}/", json=data
        )
        assert isinstance(result, dict)
        return result

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

    def unsubscribe(self, id: int) -> None:
        """Unsubscribe from a docket alert (convenience for delete).

        Args:
            id: The docket alert ID to remove.
        """
        self.delete(id)


def _validate_rate(rate: str) -> None:
    if rate not in VALID_RATES:
        raise ValueError(
            f"Invalid rate {rate!r}. "
            f"Must be one of: {', '.join(sorted(VALID_RATES))}"
        )


def _validate_search_alert_type(alert_type: str) -> None:
    if alert_type not in VALID_SEARCH_ALERT_TYPES:
        raise ValueError(
            f"Invalid alert_type {alert_type!r}. "
            f"Must be one of: "
            f"{', '.join(sorted(VALID_SEARCH_ALERT_TYPES))}"
        )


def _validate_docket_alert_type(alert_type: int) -> None:
    if alert_type not in VALID_DOCKET_ALERT_TYPES:
        raise ValueError(
            f"Invalid alert_type {alert_type!r}. "
            f"Must be one of: "
            f"{', '.join(str(v) for v in sorted(VALID_DOCKET_ALERT_TYPES))}"
        )
