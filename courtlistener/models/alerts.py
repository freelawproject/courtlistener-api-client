from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, urlencode

from pydantic import BaseModel, BeforeValidator, ConfigDict

from courtlistener.utils import (
    flatten_filters,
    search_model_validator,
    unflatten_filters,
)

RateType = Literal["rt", "dly", "wly", "mly", "off"]
SearchAlertType = Literal["o", "r", "d", "oa"]
DocketAlertType = Literal[0, 1]


def normalize_search_query(query: str | dict[str, Any] | None) -> str | None:
    """Normalize and validate a search query, returning a URL query string."""
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
