from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

DocketAlertsType = Literal[0, 1]


class DocketAlertsCreate(BaseModel):
    """Validation model for creating a docket alert."""

    model_config = ConfigDict(extra="forbid")

    docket: int
    alert_type: DocketAlertsType = 1


class DocketAlertsUpdate(BaseModel):
    """Validation model for updating a docket alert."""

    model_config = ConfigDict(extra="forbid")

    alert_type: DocketAlertsType | None = None
