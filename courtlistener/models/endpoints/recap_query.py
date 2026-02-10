from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import AfterValidator, BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter2, Filter8
from courtlistener.utils import (
    choice_validator,
    in_post_validator,
    in_pre_validator,
    related_validator,
)


class RecapQueryEndpoint(Endpoint):
    """Recap Query Endpoint"""

    endpoint: ClassVar[str] = "/recap-query/"
    endpoint_id: ClassVar[str] = "recap-query"
    endpoint_name: ClassVar[str] = "Recap Query"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    date_created: Annotated[
        None | datetime | Filter8,
        Field(
            None,
        ),
    ]
    date_modified: Annotated[
        None | datetime | Filter8,
        Field(
            None,
        ),
    ]
    date_upload: Annotated[
        None | datetime | Filter8,
        Field(
            None,
        ),
    ]
    document_type: Annotated[
        None | int,
        Field(
            None,
            json_schema_extra={
                "choices": [
                    {"value": 1, "display_name": "PACER Document"},
                    {"value": 2, "display_name": "Attachment"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    document_number: Annotated[
        None | str | Filter2,
        Field(
            None,
        ),
    ]
    pacer_doc_id: Annotated[
        None | str | list[str],
        Field(
            None,
            description="The ID of the document in PACER.",
        ),
        AfterValidator(in_post_validator),
        BeforeValidator(in_pre_validator),
    ]
    is_available: Annotated[
        None | bool,
        Field(
            None,
        ),
    ]
    sha1: Annotated[
        None | str,
        Field(
            None,
        ),
    ]
    ocr_status: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    is_free_on_pacer: Annotated[
        None | bool,
        Field(
            None,
        ),
    ]
    docket_entry: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "DocketEntriesEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    tags: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "TagsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
