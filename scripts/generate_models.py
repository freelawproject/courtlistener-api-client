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


SEARCH_FILTERS: dict[str, Any] = {
    "court": {
        "type": "MultipleChoiceFilter",
        "choices": COURT_CHOICES,
        "search_types": ["o", "r", "rd", "d", "p", "oa"],
    },
    "q": {
        "type": "CharFilter",
        "search_types": ["o", "r", "rd", "d", "p", "oa"],
    },
    "semantic": {
        "type": "BooleanFilter",
        "search_types": ["o"],
    },
    "available_only": {
        "type": "BooleanFilter",
        "search_types": ["r", "rd", "d"],
    },
    "case_name": {
        "type": "CharFilter",
        "search_types": ["o", "r", "rd", "d", "oa"],
    },
    "description": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "docket_number": {
        "type": "CharFilter",
        "search_types": ["o", "r", "rd", "d", "oa"],
    },
    "nature_of_suit": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "cause": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "filed_before": {
        "type": "RelativeDateFilter",
        "search_types": ["o", "r", "rd", "d"],
    },
    "filed_after": {
        "type": "RelativeDateFilter",
        "search_types": ["o", "r", "rd", "d"],
    },
    "entry_date_filed_before": {
        "type": "RelativeDateFilter",
        "search_types": ["r", "rd", "d"],
    },
    "entry_date_filed_after": {
        "type": "RelativeDateFilter",
        "search_types": ["r", "rd", "d"],
    },
    "document_number": {
        "type": "NumberFilter",
        "search_types": ["r", "rd", "d"],
    },
    "attachment_number": {
        "type": "NumberFilter",
        "search_types": ["r", "rd", "d"],
    },
    "assigned_to": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "referred_to": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "party_name": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "atty_name": {
        "type": "CharFilter",
        "search_types": ["r", "rd", "d"],
    },
    "judge": {
        "type": "CharFilter",
        "search_types": ["o", "oa"],
    },
    "citation": {
        "type": "CharFilter",
        "search_types": ["o"],
    },
    "neutral_cite": {
        "type": "CharFilter",
        "search_types": ["o"],
    },
    "stat_Published": {
        "type": "BooleanFilter",
        "search_types": ["o"],
    },
    "stat_Unpublished": {
        "type": "BooleanFilter",
        "search_types": ["o"],
    },
    "stat_Errata": {
        "type": "BooleanFilter",
        "search_types": ["o"],
    },
    "stat_Separate": {
        "type": "BooleanFilter",
        "search_types": ["o"],
    },
    "stat_In_chambers": {
        "type": "BooleanFilter",
        "alias": "stat_In-chambers",
        "search_types": ["o"],
    },
    "stat_Relating_to": {
        "type": "BooleanFilter",
        "alias": "stat_Relating-to",
        "search_types": ["o"],
    },
    "stat_Unknown": {
        "type": "BooleanFilter",
        "search_types": ["o"],
    },
    "cited_gt": {
        "type": "NumberFilter",
        "search_types": ["o"],
    },
    "cited_lt": {
        "type": "NumberFilter",
        "search_types": ["o"],
    },
    "name": {
        "type": "CharFilter",
        "search_types": ["p"],
    },
    "born_before": {
        "type": "RelativeDateFilter",
        "search_types": ["p"],
    },
    "born_after": {
        "type": "RelativeDateFilter",
        "search_types": ["p"],
    },
    "dob_city": {
        "type": "CharFilter",
        "search_types": ["p"],
    },
    "dob_state": {
        "type": "ChoiceFilter",
        "choices": STATE_CHOICES,
        "search_types": ["p"],
    },
    "school": {
        "type": "CharFilter",
        "search_types": ["p"],
    },
    "appointer": {
        "type": "CharFilter",
        "search_types": ["p"],
    },
    "selection_method": {
        "type": "ChoiceFilter",
        "choices": SELECTION_METHOD_CHOICES,
        "search_types": ["p"],
    },
    "political_affiliation": {
        "type": "ChoiceFilter",
        "choices": POLITICAL_AFFILIATION_CHOICES,
        "search_types": ["p"],
    },
    "argued_before": {
        "type": "RelativeDateFilter",
        "search_types": ["oa"],
    },
    "argued_after": {
        "type": "RelativeDateFilter",
        "search_types": ["oa"],
    },
}

SEARCH_ORDERINGS = [
    {
        "value": "score desc",
        "display_name": "Relevance",
        "search_types": ["o", "r", "rd", "d", "p", "oa"],
    },
    {
        "value": "dateFiled desc",
        "display_name": "Newest Cases First",
        "search_types": ["o", "r", "rd", "d"],
    },
    {
        "value": "dateFiled asc",
        "display_name": "Oldest Cases First",
        "search_types": ["o", "r", "rd", "d"],
    },
    {
        "value": "citeCount desc",
        "display_name": "Most Cited First",
        "search_types": ["o"],
    },
    {
        "value": "citeCount asc",
        "display_name": "Least Cited First",
        "search_types": ["o"],
    },
    {
        "value": "entry_date_filed desc",
        "display_name": "Newest Documents First",
        "search_types": ["r", "rd", "d"],
    },
    {
        "value": "entry_date_filed asc",
        "display_name": "Oldest Documents First",
        "search_types": ["r", "rd", "d"],
    },
    {
        "value": "name_reverse asc",
        "display_name": "Last Name",
        "search_types": ["p"],
    },
    {
        "value": "dob desc,name_reverse asc",
        "display_name": "Most Recently Born",
        "search_types": ["p"],
    },
    {
        "value": "dob asc,name_reverse asc",
        "display_name": "Least Recently Born",
        "search_types": ["p"],
    },
    {
        "value": "dod desc,name_reverse asc",
        "display_name": "Most Recently Deceased",
        "search_types": ["p"],
    },
    {
        "value": "dateArgued desc",
        "display_name": "Newest First",
        "search_types": ["oa"],
    },
    {
        "value": "dateArgued asc",
        "display_name": "Oldest First",
        "search_types": ["oa"],
    },
]


def load_search_options():
    search_type_groups = [
        ("o", "opinion-search"),
        ("r", "recap-search"),
        ("rd", "recap-document-search"),
        ("d", "recap-docket-search"),
        ("p", "judge-search"),
        ("oa", "oral-argument-search"),
        (None, "search"),
    ]

    search_options = {}

    for search_type, endpoint_id in search_type_groups:
        filters = {
            k: v
            for k, v in SEARCH_FILTERS.items()
            if search_type is None or search_type in v["search_types"]
        }
        order_by = {
            "type": "ChoiceFilter",
            "choices": [
                {"value": o["value"], "display_name": o["display_name"]}
                for o in SEARCH_ORDERINGS
                if search_type is None or search_type in o["search_types"]
            ],
        }

        if search_type is not None:
            type_filter = {
                "literal_value": search_type,
            }
        else:
            type_filter = {
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

        search_options[endpoint_id] = {
            "endpoint": "/search/",
            "actions": {"POST": {}},
            "filters": {
                "type": type_filter,
                **filters,
                "order_by": order_by,
            },
        }
    return search_options


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


def get_orderings(endpoint_options: dict[str, Any]) -> dict[str, Any] | None:
    """Add order_by filter to the endpoint options."""
    orderings = endpoint_options.get("ordering", [])
    choices = []
    for ordering in orderings:
        display_name = ordering.replace("_", " ").title()
        choices.append(
            {
                "value": ordering,
                "display_name": display_name + " (asc)",
            }
        )
        choices.append(
            {
                "value": "-" + ordering,
                "display_name": display_name + " (desc)",
            }
        )
    if choices:
        return {
            "type": "ChoiceFilter",
            "choices": choices,
        }
    return None


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
    filter_choices: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    """Get choices from the filter or, for NumberInFilter and CharInFilter, fallback to the field."""
    choices = []
    values = set()
    for choice in filter_choices:
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
    lookup_types: list[str],
    choice_key_type: str | None,
) -> tuple[list[str], list[str]]:
    lookup_types = lookup_types if isinstance(lookup_types, list) else []
    python_types = []
    validators = []

    if "in" in lookup_types:
        validators.append("AfterValidator(in_post_validator)")
        if filter_type == "ChoiceFilter":
            filter_type = "MultipleChoiceFilter"

    if filter_type == "RelatedFilter":
        python_types = ["dict[str, Any]"]
        validators.append("BeforeValidator(related_validator)")
    elif filter_type == "CharFilter":
        python_types = ["str"]
    elif filter_type in ["ModelChoiceFilter"]:
        python_types = ["int"]
    elif filter_type == "BooleanFilter":
        python_types = ["bool"]
    elif filter_type == "ChoiceFilter":
        if choice_key_type is not None:
            python_types = [choice_key_type]
            validators.append("BeforeValidator(choice_validator)")
    elif filter_type == "MultipleChoiceFilter":
        if choice_key_type is not None:
            python_types = [f"list[{choice_key_type}]", choice_key_type]
            validators.append("BeforeValidator(multiple_choice_validator)")
    elif filter_type == "MultipleChoiceStringFilter":
        python_types = ["list[str]"]
        validators.append("AfterValidator(comma_separated_post_validator)")
        validators.append("BeforeValidator(multiple_choice_validator)")
        validators.append("BeforeValidator(comma_separated_pre_validator)")
    elif filter_type == "IsoDateTimeFilter":
        python_types = ["datetime"]
    elif filter_type == "DateFilter":
        python_types = ["date"]
    elif filter_type == "NumberFilter":
        python_types = ["int"]
    elif filter_type == "RelativeDateFilter":
        python_types = ["str | date"]
        validators.append("BeforeValidator(relative_date_validator)")

    if "in" in lookup_types:
        for python_type in python_types:
            if "list" not in python_type:
                python_types.append(f"list[{python_type}]")
        if "int" in python_types:
            validators.append("BeforeValidator(try_coerce_ints)")
        validators.append("BeforeValidator(in_pre_validator)")
    python_types = sorted(set(python_types), key=lambda x: len(x))
    return python_types, validators


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
    options = {**options, **load_search_options()}

    # Assemble endpoints data
    endpoints: dict[str, Any] = {}
    for endpoint_id, endpoint_options in options.items():
        fields = endpoint_options.get("actions", {}).get("POST", {})
        filters = endpoint_options.get("filters", {})
        order_by = get_orderings(endpoint_options)
        if order_by:
            filters["order_by"] = order_by
        endpoint_fields = {}

        if fields:
            field_filter_choices = [
                {"value": k, "display_name": v["label"]}
                for k, v in fields.items()
            ]
            filters = {
                "fields": {
                    "type": "MultipleChoiceStringFilter",
                    "choices": field_filter_choices,
                    "description": "Filter field returned in the response.",
                },
                **filters,
            }

        for field_name, filter in filters.items():
            # Get field data
            field = fields.get(field_name, {})
            related_endpoint_id = get_related_endpoint_id(
                filter.get("type"), filter.get("lookup_types", [])
            )
            choices = get_choices(filter.get("choices", []))
            choice_key_type = get_choice_key_type(choices)
            python_types, validators = get_types_and_validators(
                filter.get("type"),
                filter.get("lookup_types"),
                choice_key_type,
            )
            lookup_types = process_lookup_types(filter.get("lookup_types", []))

            # Create query field
            endpoint_fields[field_name] = {
                "id": field_name,
                "alias": filter.get("alias"),
                "lookup_types": lookup_types,
                "choices": choices,
                "description": (
                    field.get("help_text") or filter.get("description")
                ),
                "related_endpoint_id": related_endpoint_id,
                "types": python_types,
                "types_str": " | ".join(python_types),
                "validators": validators,
                "filter_class": None,
                "literal_value": filter.get("literal_value"),
            }
        name = options.get("name") or endpoint_id.replace("-", " ").title()
        description = options.get("description") or f"{name} Endpoint"
        attr_name = endpoint_id.replace("-", "_").replace("/", "_")
        endpoint = endpoint_options.get("endpoint", f"/{endpoint_id}/")
        endpoints[endpoint_id] = {
            "id": endpoint_id,
            "endpoint": endpoint,
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
                filter_types = endpoint_field["types"]
                if any(
                    x in endpoint_field["lookup_types"]
                    for x in ["gt", "gte", "lt", "lte"]
                ) and endpoint_field["types"] == ["str"]:
                    filter_types = ["int"]
                filter_class_json = json.dumps(
                    {
                        "types": filter_types,
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

    # Generate filter classes
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
