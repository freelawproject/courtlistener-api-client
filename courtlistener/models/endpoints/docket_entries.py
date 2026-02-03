from typing import Any, ClassVar, Annotated
from datetime import datetime, date

from pydantic import Field, ConfigDict, BeforeValidator, AfterValidator

from courtlistener.utils import (
    choice_validator,
    multiple_choice_validator,
    related_validator,
    in_pre_validator,
    try_coerce_ints,
    in_post_validator,
)
from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter5
from courtlistener.models.filters import Filter8
from courtlistener.models.filters import Filter8
from courtlistener.models.filters import Filter7
from courtlistener.models.filters import Filter5


class DocketEntriesEndpoint(Endpoint):
    """Docket Entries Endpoint"""

    endpoint: ClassVar[str] = "/docket-entries/"
    endpoint_id: ClassVar[str] = "docket-entries"
    endpoint_name: ClassVar[str] = "Docket Entries"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    entry_number: Annotated[
        None | bool | Filter5,
        Field(
            None,
            description="# on the PACER docket page. For appellate cases, this may be the internal PACER ID for the document, when an entry ID is otherwise unavailable.",
        ),
    ]
    date_created: Annotated[
        None | datetime | Filter8,
        Field(
            None,
            description="The moment when the item was created.",
        ),
    ]
    date_modified: Annotated[
        None | datetime | Filter8,
        Field(
            None,
            description="The last moment when the item was modified. A value in year 1750 indicates the value is unknown",
        ),
    ]
    date_filed: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="The created date of the Docket Entry according to the court timezone.",
        ),
    ]
    pacer_sequence_number: Annotated[
        None | bool | Filter5,
        Field(
            None,
            description="The de_seqno value pulled out of dockets, RSS feeds, and sundry other pages in PACER. The place to find this is currently in the onclick attribute of the links in PACER. Because we do not have this value for all items in the DB, we do not use this value for anything. Still, we collect it for good measure.",
        ),
    ]
    docket: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "DocketsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    recap_documents: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "RecapDocumentsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    tags: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The tags associated with the docket entry.",
            json_schema_extra={
                "related_class_name": "TagsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]


