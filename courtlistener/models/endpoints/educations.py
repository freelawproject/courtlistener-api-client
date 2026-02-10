from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter4, Filter8
from courtlistener.utils import (
    choice_validator,
    related_validator,
)


class EducationsEndpoint(Endpoint):
    """Educations Endpoint"""

    endpoint: ClassVar[str] = "/educations/"
    endpoint_id: ClassVar[str] = "educations"
    endpoint_name: ClassVar[str] = "Educations"

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
    degree_year: Annotated[
        None | int,
        Field(
            None,
            description="The year the degree was awarded.",
        ),
    ]
    degree_detail: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="Detailed degree description, e.g. including major.",
        ),
    ]
    degree_level: Annotated[
        None | str,
        Field(
            None,
            description="Normalized degree level, e.g. BA, JD.",
            json_schema_extra={
                "choices": [
                    {"value": "ba", "display_name": "Bachelor's (e.g. B.A.)"},
                    {"value": "ma", "display_name": "Master's (e.g. M.A.)"},
                    {"value": "jd", "display_name": "Juris Doctor (J.D.)"},
                    {"value": "llm", "display_name": "Master of Laws (LL.M)"},
                    {
                        "value": "llb",
                        "display_name": "Bachelor of Laws (e.g. LL.B)",
                    },
                    {"value": "jsd", "display_name": "Doctor of Law (J.S.D)"},
                    {
                        "value": "phd",
                        "display_name": "Doctor of Philosophy (PhD)",
                    },
                    {"value": "aa", "display_name": "Associate (e.g. A.A.)"},
                    {"value": "md", "display_name": "Medical Degree (M.D.)"},
                    {
                        "value": "mba",
                        "display_name": "Master of Business Administration (M.B.A.)",
                    },
                    {
                        "value": "cfa",
                        "display_name": "Accounting Certification (C.P.A., C.M.A., C.F.A.)",
                    },
                    {"value": "cert", "display_name": "Certificate"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    person: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "PeopleEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    school: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "SchoolsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
