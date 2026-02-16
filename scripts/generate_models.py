import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from courtlistener import CourtListener

BASE_DIR = Path(__file__).parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
ENDPOINTS_DIR = BASE_DIR / "courtlistener" / "models" / "endpoints"
FILTERS_DIR = BASE_DIR / "courtlistener" / "models" / "filters"

RELATED_ENDPOINT_MAP = {
    "opinion-clusters": "clusters",
    "audio-files": "audio",
    "user-tags": "tags",
    "american-bar-association-ratings": "aba-ratings",
}


COURT_CHOICES = json.loads(
    Path(BASE_DIR / "scripts" / "court_choices.json").read_text()
)

STATE_CHOICES = [
    {"value": "AL", "display_name": "Alabama"},
    {"value": "AK", "display_name": "Alaska"},
    {"value": "AS", "display_name": "American Samoa"},
    {"value": "AZ", "display_name": "Arizona"},
    {"value": "AR", "display_name": "Arkansas"},
    {"value": "AA", "display_name": "Armed Forces Americas"},
    {"value": "AE", "display_name": "Armed Forces Europe"},
    {"value": "AP", "display_name": "Armed Forces Pacific"},
    {"value": "CA", "display_name": "California"},
    {"value": "CO", "display_name": "Colorado"},
    {"value": "CT", "display_name": "Connecticut"},
    {"value": "DE", "display_name": "Delaware"},
    {"value": "DC", "display_name": "District of Columbia"},
    {"value": "FL", "display_name": "Florida"},
    {"value": "GA", "display_name": "Georgia"},
    {"value": "GU", "display_name": "Guam"},
    {"value": "HI", "display_name": "Hawaii"},
    {"value": "ID", "display_name": "Idaho"},
    {"value": "IL", "display_name": "Illinois"},
    {"value": "IN", "display_name": "Indiana"},
    {"value": "IA", "display_name": "Iowa"},
    {"value": "KS", "display_name": "Kansas"},
    {"value": "KY", "display_name": "Kentucky"},
    {"value": "LA", "display_name": "Louisiana"},
    {"value": "ME", "display_name": "Maine"},
    {"value": "MD", "display_name": "Maryland"},
    {"value": "MA", "display_name": "Massachusetts"},
    {"value": "MI", "display_name": "Michigan"},
    {"value": "MN", "display_name": "Minnesota"},
    {"value": "MS", "display_name": "Mississippi"},
    {"value": "MO", "display_name": "Missouri"},
    {"value": "MT", "display_name": "Montana"},
    {"value": "NE", "display_name": "Nebraska"},
    {"value": "NV", "display_name": "Nevada"},
    {"value": "NH", "display_name": "New Hampshire"},
    {"value": "NJ", "display_name": "New Jersey"},
    {"value": "NM", "display_name": "New Mexico"},
    {"value": "NY", "display_name": "New York"},
    {"value": "NC", "display_name": "North Carolina"},
    {"value": "ND", "display_name": "North Dakota"},
    {"value": "MP", "display_name": "Northern Mariana Islands"},
    {"value": "OH", "display_name": "Ohio"},
    {"value": "OK", "display_name": "Oklahoma"},
    {"value": "OR", "display_name": "Oregon"},
    {"value": "PA", "display_name": "Pennsylvania"},
    {"value": "PR", "display_name": "Puerto Rico"},
    {"value": "RI", "display_name": "Rhode Island"},
    {"value": "SC", "display_name": "South Carolina"},
    {"value": "SD", "display_name": "South Dakota"},
    {"value": "TN", "display_name": "Tennessee"},
    {"value": "WY", "display_name": "Wyoming"},
    {"value": "TX", "display_name": "Texas"},
    {"value": "UT", "display_name": "Utah"},
    {"value": "VT", "display_name": "Vermont"},
    {"value": "VI", "display_name": "Virgin Islands"},
    {"value": "VA", "display_name": "Virginia"},
    {"value": "WA", "display_name": "Washington"},
    {"value": "WV", "display_name": "West Virginia"},
    {"value": "WI", "display_name": "Wisconsin"},
]


SELECTION_METHOD_CHOICES = [
    {
        "value": "e_part",
        "display_name": "Partisan Election",
    },
    {
        "value": "appoine_non_parttment",
        "display_name": "Non-Partisan Election",
    },
    {
        "value": "a_pres",
        "display_name": "Appointment (President)",
    },
    {
        "value": "a_gov",
        "display_name": "Appointment (Governor)",
    },
    {
        "value": "a_legis",
        "display_name": "Appointment (Legislature)",
    },
    {
        "value": "a_judge",
        "display_name": "Appointment (Judge)",
    },
    {
        "value": "ct_trans",
        "display_name": "Transferred (Court Restructuring)",
    },
]


POLITICAL_AFFILIATION_CHOICES = [
    {
        "value": "d",
        "display_name": "Democratic",
    },
    {
        "value": "r",
        "display_name": "Republican",
    },
    {
        "value": "i",
        "display_name": "Independent",
    },
    {
        "value": "g",
        "display_name": "Green",
    },
    {
        "value": "l",
        "display_name": "Libertarian",
    },
    {
        "value": "f",
        "display_name": "Federalist",
    },
    {
        "value": "w",
        "display_name": "Whig",
    },
    {
        "value": "j",
        "display_name": "Jeffersonian Republican",
    },
    {
        "value": "u",
        "display_name": "National Union",
    },
    {
        "value": "z",
        "display_name": "Reform Party",
    },
]


OPINION_SEARCH_OPTIONS: dict[str, Any] = {
    "endpoint": "/search/",
    "actions": {
        "POST": {
            "cited_gt": {
                "type": "integer",
            },
            "cited_lt": {
                "type": "integer",
            },
        }
    },
    "filters": {
        "type": {
            "literal_value": "o",
        },
        "court": {
            "type": "MultipleChoiceFilter",
            "choices": COURT_CHOICES,
        },
        "q": {
            "type": "CharFilter",
        },
        "semantic": {
            "type": "BooleanFilter",
        },
        "case_name": {
            "type": "CharFilter",
        },
        "judge": {
            "type": "CharFilter",
        },
        "stat_Published": {
            "type": "BooleanFilter",
        },
        "stat_Unpublished": {
            "type": "BooleanFilter",
        },
        "stat_Errata": {
            "type": "BooleanFilter",
        },
        "stat_Separate": {
            "type": "BooleanFilter",
        },
        "stat_In_chambers": {
            "type": "BooleanFilter",
            "alias": "stat_In-chambers",
        },
        "stat_Relating_to": {
            "type": "BooleanFilter",
            "alias": "stat_Relating-to",
        },
        "stat_Unknown": {
            "type": "BooleanFilter",
        },
        "filed_before": {
            "type": "RelativeDateFilter",
        },
        "filed_after": {
            "type": "RelativeDateFilter",
        },
        "citation": {
            "type": "CharFilter",
        },
        "neutral_cite": {
            "type": "CharFilter",
        },
        "docket_number": {
            "type": "CharFilter",
        },
        "cited_gt": {
            "type": "NumberFilter",
        },
        "cited_lt": {
            "type": "NumberFilter",
        },
    },
}


RECAP_SEARCH_OPTIONS: dict[str, Any] = {
    "endpoint": "/search/",
    "actions": {
        "POST": {
            "document_number": {
                "type": "integer",
            },
            "attachment_number": {
                "type": "integer",
            },
        }
    },
    "filters": {
        "type": {
            "literal_value": "r",
        },
        "court": {
            "type": "MultipleChoiceFilter",
            "choices": COURT_CHOICES,
        },
        "q": {
            "type": "CharFilter",
        },
        "semantic": {
            "type": "BooleanFilter",
        },
        "available_only": {
            "type": "BooleanFilter",
        },
        "case_name": {
            "type": "CharFilter",
        },
        "description": {
            "type": "CharFilter",
        },
        "docket_number": {
            "type": "CharFilter",
        },
        "nature_of_suit": {
            "type": "CharFilter",
        },
        "cause": {
            "type": "CharFilter",
        },
        "filed_before": {
            "type": "RelativeDateFilter",
        },
        "filed_after": {
            "type": "RelativeDateFilter",
        },
        "entry_date_filed_before": {
            "type": "RelativeDateFilter",
        },
        "entry_date_filed_after": {
            "type": "RelativeDateFilter",
        },
        "document_number": {
            "type": "NumberFilter",
        },
        "attachment_number": {
            "type": "NumberFilter",
        },
        "assigned_to": {
            "type": "CharFilter",
        },
        "referred_to": {
            "type": "CharFilter",
        },
        "party_name": {
            "type": "CharFilter",
        },
        "atty_name": {
            "type": "CharFilter",
        },
    },
}


RECAP_DOCKET_SEARCH_OPTIONS: dict[str, Any] = RECAP_SEARCH_OPTIONS.copy()
RECAP_DOCKET_SEARCH_OPTIONS["filters"]["type"] = {
    "literal_value": "d",
}


RECAP_DOCUMENT_SEARCH_OPTIONS: dict[str, Any] = RECAP_SEARCH_OPTIONS.copy()
RECAP_DOCUMENT_SEARCH_OPTIONS["filters"]["type"] = {
    "literal_value": "rd",
}


JUDGE_SEARCH_OPTIONS: dict[str, Any] = {
    "endpoint": "/search/",
    "actions": {"POST": {}},
    "filters": {
        "type": {
            "literal_value": "p",
        },
        "court": {
            "type": "MultipleChoiceFilter",
            "choices": COURT_CHOICES,
        },
        "q": {
            "type": "CharFilter",
        },
        "semantic": {
            "type": "BooleanFilter",
        },
        "name": {
            "type": "CharFilter",
        },
        "born_before": {
            "type": "RelativeDateFilter",
        },
        "born_after": {
            "type": "RelativeDateFilter",
        },
        "dob_city": {
            "type": "CharFilter",
        },
        "dob_state": {
            "type": "ChoiceFilter",
            "choices": STATE_CHOICES,
        },
        "school": {
            "type": "CharFilter",
        },
        "appointer": {
            "type": "CharFilter",
        },
        "selection_method": {
            "type": "ChoiceFilter",
            "choices": SELECTION_METHOD_CHOICES,
        },
        "political_affiliation": {
            "type": "ChoiceFilter",
            "choices": POLITICAL_AFFILIATION_CHOICES,
        },
    },
}


ORAL_ARGUMENT_SEARCH_OPTIONS: dict[str, Any] = {
    "endpoint": "/search/",
    "actions": {"POST": {}},
    "filters": {
        "type": {
            "literal_value": "oa",
        },
        "court": {
            "type": "MultipleChoiceFilter",
            "choices": COURT_CHOICES,
        },
        "q": {
            "type": "CharFilter",
        },
        "semantic": {
            "type": "BooleanFilter",
        },
        "case_name": {
            "type": "CharFilter",
        },
        "judge": {
            "type": "CharFilter",
        },
        "argued_before": {
            "type": "RelativeDateFilter",
        },
        "argued_after": {
            "type": "RelativeDateFilter",
        },
        "docket_number": {
            "type": "CharFilter",
        },
    },
}


SEARCH_OPTIONS: dict[str, Any] = {
    "endpoint": "/search/",
    "actions": {
        "POST": {
            **OPINION_SEARCH_OPTIONS["actions"]["POST"],
            **RECAP_SEARCH_OPTIONS["actions"]["POST"],
            **JUDGE_SEARCH_OPTIONS["actions"]["POST"],
            **ORAL_ARGUMENT_SEARCH_OPTIONS["actions"]["POST"],
        }
    },
    "filters": {
        **OPINION_SEARCH_OPTIONS["filters"],
        **RECAP_SEARCH_OPTIONS["filters"],
        **JUDGE_SEARCH_OPTIONS["filters"],
        **ORAL_ARGUMENT_SEARCH_OPTIONS["filters"],
    },
}


SEARCH_OPTIONS["filters"]["type"] = {
    "type": "ChoiceFilter",
    "choices": [
        {
            "value": "o",
            "display_name": "Opinion",
        },
        {
            "value": "r",
            "display_name": "Recap",
        },
        {
            "value": "rd",
            "display_name": "Document",
        },
        {
            "value": "d",
            "display_name": "Docket",
        },
        {
            "value": "p",
            "display_name": "Judge",
        },
        {
            "value": "oa",
            "display_name": "Oral Argument",
        },
    ],
}


def to_title_case(s: str) -> str:
    return (
        s.replace("_", " ")
        .replace("-", " ")
        .replace("/", " ")
        .title()
        .replace(" ", "")
    )


def get_options() -> dict[str, Any]:
    """Get options from the API"""
    options = {}
    client = CourtListener()
    endpoints_list = client._request("GET", "/")
    for endpoint_id in endpoints_list:
        try:
            options[endpoint_id] = client._request(
                "OPTIONS", f"/{endpoint_id}/"
            )
        except Exception as e:
            print(f"Error getting options for {endpoint_id}: {e}")
            continue
    return options


def process_lookup_types(lookup_types: list[str] | str) -> list[str]:
    """Process lookup types, remove "exact" and "in"."""
    if isinstance(lookup_types, list):
        lookup_types = [x for x in lookup_types if x not in ["exact", "in"]]
        return sorted(set(lookup_types))
    return []


def get_related_endpoint_id(
    filter_type: str, lookup_types: list[str] | str
) -> str | None:
    """Get the related endpoint ID from the lookup types, fallback to hardcoded mapping."""
    if filter_type == "RelatedFilter" and isinstance(lookup_types, str):
        related_endpoint_id = (
            lookup_types.split("'")[1].replace(" ", "-").lower()
        )
        related_endpoint_id = RELATED_ENDPOINT_MAP.get(
            related_endpoint_id, related_endpoint_id
        )
        if related_endpoint_id is None:
            print(f"Related endpoint {related_endpoint_id} not found")
        return related_endpoint_id
    return None


def get_choices(
    filter_type: str,
    filter_choices: list[dict[str, str | int]],
    field_choices: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    """Get choices from the filter or, for NumberInFilter and CharInFilter, fallback to the field."""
    choices = []
    values = set()
    if filter_choices:
        for choice in filter_choices:
            if choice["value"] not in values:
                choices.append(choice)
                values.add(choice["value"])
        return choices
    if filter_type in ["NumberInFilter", "CharInFilter"]:
        for choice in field_choices:
            if choice["value"] not in values:
                choices.append(choice)
                values.add(choice["value"])
    return choices


def get_choice_key_type(choices: list[dict[str, str | int]]) -> str | None:
    if choices:
        if isinstance(choices[0]["value"], int):
            return "int"
        return "str"
    return None


def get_types_and_validators(
    filter_type: str,
    field_type: str,
    lookup_types: list[str],
    choice_key_type: str | None,
) -> tuple[list[str], list[str]]:
    python_types = []
    validators = []
    if filter_type == "RelatedFilter":
        python_types = ["dict[str, Any]"]
        validators.append("BeforeValidator(related_validator)")
    elif filter_type == "CharFilter":
        python_types = ["str"]
    elif filter_type in ["NumberRangeFilter", "ModelChoiceFilter"]:
        python_types = ["int"]
    elif filter_type == "BooleanFilter":
        python_types = ["bool"]
    elif filter_type == "NumberInFilter":
        python_types = ["list[int]", "int"]
        validators.append("AfterValidator(in_post_validator)")
        if choice_key_type is not None:
            validators.append("BeforeValidator(multiple_choice_validator)")
        validators.append("BeforeValidator(try_coerce_ints)")
        validators.append("BeforeValidator(in_pre_validator)")
    elif filter_type == "CharInFilter":
        python_types = ["list[str]", "str"]
        validators.append("AfterValidator(in_post_validator)")
        if choice_key_type is not None:
            validators.append("BeforeValidator(multiple_choice_validator)")
        validators.append("BeforeValidator(in_pre_validator)")
    elif filter_type == "ChoiceFilter":
        if choice_key_type is not None:
            python_types = [choice_key_type]
            validators.append("BeforeValidator(choice_validator)")
    elif filter_type == "MultipleChoiceFilter":
        if choice_key_type is not None:
            python_types = [f"list[{choice_key_type}]", choice_key_type]
            validators.append("BeforeValidator(multiple_choice_validator)")
    elif filter_type == "NumberFilter":
        if field_type == "datetime" or "hour" in lookup_types:
            python_types = ["datetime"]
        elif field_type == "date" or "year" in lookup_types:
            python_types = ["date"]
        elif field_type in ["integer", "field"]:
            python_types = ["int"]
    elif filter_type == "RelativeDateFilter":
        python_types = ["str | date"]
        validators.append("BeforeValidator(relative_date_validator)")
    return sorted(python_types, key=lambda x: len(x)), validators


def get_endpoint_data(cache_path: str | Path | None = None) -> dict[str, Any]:
    # Load options from cache or API
    cache_path = Path(cache_path) if cache_path is not None else None
    if cache_path is not None and cache_path.exists():
        options = json.loads(cache_path.read_text())
    else:
        options = get_options()
        if cache_path is not None:
            cache_path.write_text(json.dumps(options, indent=2))

    # Add custom endpoints
    options["opinion-search"] = OPINION_SEARCH_OPTIONS
    options["recap-search"] = RECAP_SEARCH_OPTIONS
    options["recap-docket-search"] = RECAP_DOCKET_SEARCH_OPTIONS
    options["recap-document-search"] = RECAP_DOCUMENT_SEARCH_OPTIONS
    options["judge-search"] = JUDGE_SEARCH_OPTIONS
    options["oral-argument-search"] = ORAL_ARGUMENT_SEARCH_OPTIONS
    options["search"] = SEARCH_OPTIONS

    # Assemble endpoints data
    endpoints: dict[str, Any] = {}
    for endpoint_id, endpoint_options in options.items():
        fields = endpoint_options.get("actions", {}).get("POST", {})
        filters = endpoint_options.get("filters", {})
        endpoint_fields = {}
        for field_name, filter in filters.items():
            # Get field data
            field = fields.get(field_name, {})
            lookup_types = process_lookup_types(filter.get("lookup_types", []))
            related_endpoint_id = get_related_endpoint_id(
                filter.get("type"), filter.get("lookup_types", [])
            )
            choices = get_choices(
                filter.get("type"),
                filter.get("choices", []),
                field.get("choices", []),
            )
            choice_key_type = get_choice_key_type(choices)
            python_types, validators = get_types_and_validators(
                filter.get("type"),
                field.get("type"),
                lookup_types,
                choice_key_type,
            )
            # Create query field
            endpoint_fields[field_name] = {
                "id": field_name,
                "lookup_types": lookup_types,
                "choices": choices,
                "description": field.get("help_text"),
                "related_endpoint_id": related_endpoint_id,
                "types": python_types,
                "types_str": " | ".join(python_types),
                "validators": validators,
                "filter_class": None,
            }
        name = options.get("name") or endpoint_id.replace("-", " ").title()
        description = options.get("description") or f"{name} Endpoint"
        attr_name = endpoint_id.replace("-", "_").replace("/", "_")
        endpoints[endpoint_id] = {
            "id": endpoint_id,
            "endpoint": f"/{endpoint_id}/",
            "name": name,
            "description": description,
            "attr_name": attr_name,
            "class_name": to_title_case(endpoint_id) + "Endpoint",
            "fields": endpoint_fields,
        }

    filter_classes_json = []
    for endpoint in endpoints.values():
        for endpoint_field in endpoint["fields"].values():
            if endpoint_field["types"] and endpoint_field["lookup_types"]:
                filter_class_json = json.dumps(
                    {
                        "types": endpoint_field["types"],
                        "lookup_types": endpoint_field["lookup_types"],
                    },
                    indent=2,
                    sort_keys=True,
                )
                if filter_class_json not in filter_classes_json:
                    filter_classes_json.append(filter_class_json)
                endpoint_field["filter_class"] = filter_classes_json.index(
                    filter_class_json
                )

            if endpoint_field["related_endpoint_id"]:
                related_endpoint = endpoints.get(
                    endpoint_field["related_endpoint_id"], {}
                )
                related_id_field = related_endpoint.get("fields", {}).get(
                    "id", {}
                )
                endpoint_field["related_id_types_str"] = related_id_field.get(
                    "types_str"
                )
                endpoint_field["related_attr_name"] = related_endpoint.get(
                    "attr_name"
                )
                endpoint_field["related_class_name"] = related_endpoint.get(
                    "class_name"
                )

            if not endpoint_field["types"]:
                print(
                    f"NOT IMPLEMENTED: {endpoint['id']} {endpoint_field['id']}"
                )

    filter_classes = {
        i: json.loads(filter_class_json)
        for i, filter_class_json in enumerate(filter_classes_json)
    }
    filter_classes = dict(
        sorted(filter_classes.items(), key=lambda x: len(x[1]["lookup_types"]))
    )
    for i, filter_class in enumerate(filter_classes.values()):
        print(filter_class)
        filter_class["class_name"] = f"Filter{i + 1}"
        filter_class["types_str"] = " | ".join(filter_class["types"])
    for endpoint in endpoints.values():
        for endpoint_field in endpoint["fields"].values():
            if endpoint_field.get("filter_class"):
                endpoint_field["filter_class"] = filter_classes[
                    endpoint_field["filter_class"]
                ]["class_name"]

    return {
        "endpoints": endpoints,
        "filters": filter_classes,
    }


if __name__ == "__main__":
    load_dotenv()

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    data = get_endpoint_data(BASE_DIR / "cached_options.json")

    # Generate Filters Module
    FILTERS_DIR.mkdir(parents=True, exist_ok=True)

    for filter in data["filters"].values():
        (FILTERS_DIR / (filter["class_name"].lower() + ".py")).write_text(
            env.get_template("filter.jinja2").render(filter=filter)
        )

    (FILTERS_DIR / "__init__.py").write_text(
        env.get_template("filters_init.jinja2").render(
            filters=data["filters"].values(),
        )
    )

    # Generate Endpoints Module
    ENDPOINTS_DIR.mkdir(parents=True, exist_ok=True)

    for endpoint in data["endpoints"].values():
        (ENDPOINTS_DIR / (endpoint["attr_name"] + ".py")).write_text(
            env.get_template("endpoint.jinja2").render(endpoint=endpoint)
        )

    (ENDPOINTS_DIR / "__init__.py").write_text(
        env.get_template("endpoints_init.jinja2").render(
            endpoints=data["endpoints"].values(),
        )
    )
