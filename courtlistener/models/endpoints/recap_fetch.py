from typing import Annotated, ClassVar

from pydantic import AfterValidator, BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.utils import (
    choice_validator,
    in_post_validator,
    in_pre_validator,
    try_coerce_ints,
)


class RecapFetchEndpoint(Endpoint):
    """Recap Fetch Endpoint"""

    endpoint: ClassVar[str] = "/recap-fetch/"
    endpoint_id: ClassVar[str] = "recap-fetch"
    endpoint_name: ClassVar[str] = "Recap Fetch"

    status: Annotated[
        None | int | list[int],
        Field(
            None,
            description="The current status of this request. Possible values are: (1): Awaiting processing in queue., (2): Item processed successfully., (3): Item encountered an error while processing., (4): Item is currently being processed., (5): Item failed processing, but will be retried., (6): Item failed validity tests., (7): There was insufficient metadata to complete the task.",
        ),
        AfterValidator(in_post_validator),
        BeforeValidator(try_coerce_ints),
        BeforeValidator(in_pre_validator),
    ]
    request_type: Annotated[
        None | int,
        Field(
            None,
            description="The type of object that is requested",
            json_schema_extra={
                "choices": [
                    {"value": 1, "display_name": "HTML Docket"},
                    {"value": 2, "display_name": "PDF"},
                    {"value": 3, "display_name": "Attachment Page"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    court: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    docket: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    pacer_case_id: Annotated[
        None | str | list[str],
        Field(
            None,
            description="The case ID provided by PACER for the case to update (must be used in combination with the court field).",
        ),
        AfterValidator(in_post_validator),
        BeforeValidator(in_pre_validator),
    ]
    docket_number: Annotated[
        None | str,
        Field(
            None,
            description="The docket number of a case to update (must be used in combination with the court field).",
        ),
    ]
