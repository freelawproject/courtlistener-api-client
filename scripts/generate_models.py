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
