import difflib
import re
from collections.abc import Iterable
from contextlib import suppress
from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter, ValidationInfo

if TYPE_CHECKING:
    from courtlistener.models import Endpoint


def did_you_mean(value: Any, choices: Iterable[Any]) -> str:
    """Suggest near-miss matches for value from choices."""
    originals: dict[str, str] = {}
    for choice in choices:
        originals.setdefault(str(choice).casefold(), str(choice))
    matches = difflib.get_close_matches(
        str(value).casefold(), list(originals), n=3, cutoff=0.6
    )
    if not matches:
        return ""
    return f" Did you mean: {', '.join(originals[m] for m in matches)}?"


def flatten_filters(
    filters: dict[str, Any], prefix: str = ""
) -> dict[str, Any]:
    """Flatten nested filter dicts into double-underscore notation."""
    result: dict[str, Any] = {}

    for key, value in filters.items():
        full_key = f"{prefix}__{key}" if prefix else key

        if isinstance(value, dict):
            result.update(flatten_filters(value, full_key))
        else:
            result[full_key] = value

    return result


def unflatten_filters(filters: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in filters.items():
        if "__" in key:
            parts = key.split("__", 1)
            key = parts[0]
            value = {parts[1]: value}

        if isinstance(value, dict):
            result[key] = result.get(key, {})
            if not isinstance(result[key], dict):
                raise ValueError(f"Incompatible values for {key}")
            for subkey, subvalue in value.items():
                if subkey in result[key]:
                    raise ValueError(
                        f"Incompatible values for {key}__{subkey}"
                    )
                result[key][subkey] = subvalue
        else:
            if key in result:
                raise ValueError(f"Incompatible values for {key}")
            result[key] = value

    for key, value in result.items():
        if isinstance(value, dict):
            result[key] = unflatten_filters(value)
    return result


def validate_model_fields(
    model: type["Endpoint"], fields: str | list[str]
) -> list[str]:
    if isinstance(fields, str):
        fields = fields.split(",")
    # Don't enforce choices if no `fields` field.
    if "fields" in model.model_fields:
        extra = model.model_fields["fields"].json_schema_extra
        if isinstance(extra, dict):
            choices = extra.get("choices")
            if isinstance(choices, list):
                values = []
                for choice in choices:
                    if isinstance(choice, dict):
                        values.append(choice["value"])
                invalid_fields = [f for f in fields if f not in values]
                if invalid_fields:
                    suggestions = "".join(
                        did_you_mean(f, values) for f in invalid_fields
                    )
                    raise ValueError(
                        f"Invalid fields: {invalid_fields}.{suggestions}\n"
                        f"Fields must be one of: {values}"
                    )
    return fields


def get_endpoint_model_from_info(info: ValidationInfo) -> type["Endpoint"]:
    from courtlistener.models import ENDPOINTS

    if info.config is not None:
        model_name = info.config["title"]
        for model in ENDPOINTS.values():
            if model.__name__ == model_name:
                return model
    raise ValueError(f"Model for {info.field_name} not found")


def related_validator(
    value: Any, info: ValidationInfo
) -> str | int | dict[str, Any] | None:
    from courtlistener.models import ENDPOINTS

    if value is None or isinstance(value, str | int):
        return value

    model = get_endpoint_model_from_info(info)
    field = model.model_fields[str(info.field_name)]
    extra = getattr(field, "json_schema_extra", None) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Invalid value '{value}' for {info.field_name}")
    value = {k: v for k, v in value.items() if v is not None}
    related_class_name = extra.get("related_class_name", None)
    if related_class_name is None:
        # Return raw value if there isn't a schema for the related field.
        return value
    related_model = None
    for model in ENDPOINTS.values():
        if model.__name__ == related_class_name:
            related_model = model
            break
    if related_model is None:
        raise ValueError(f"Related model for {info.field_name} not found")
    return related_model.model_validate(value).model_dump(by_alias=True)


def get_choice_dict_from_info(
    info: ValidationInfo,
) -> dict[str, str] | dict[int, str]:
    """Get the choice dictionary for a field."""
    model = get_endpoint_model_from_info(info)
    field = model.model_fields[str(info.field_name)]
    extra = getattr(field, "json_schema_extra", None) or {}
    choices = extra.get("choices", [])
    return {choice["value"]: choice["display_name"] for choice in choices}


def get_valid_choice(
    choice: str | int | None, choice_dict: dict[str, str] | dict[int, str]
) -> str | int | None:
    """Get a valid choice from a choice dictionary.

    Falls back to the display name if the choice is not found in values.
    Returns None if choice is not valid.
    """
    if choice in choice_dict:
        return choice
    for value, display_name in choice_dict.items():
        if choice == display_name:
            return value
    # Tolerate string-typed numerics for int-keyed choices
    if isinstance(choice, str) and choice.lstrip("-").isdigit():
        as_int = int(choice)
        if as_int in choice_dict:
            return as_int
    return None


def invalid_choice_error(
    field_name: str | None,
    value: Any,
    invalid_parts: list[Any],
    choice_dict: dict[str, str] | dict[int, str],
) -> ValueError:
    """Build a compact invalid-choice error with near-miss suggestions."""
    candidates = list(choice_dict) + list(choice_dict.values())
    suggestions = "".join(
        did_you_mean(part, candidates) for part in invalid_parts
    )
    return ValueError(
        f"Invalid value '{value}' for {field_name}.{suggestions} "
        "MCP clients can use the `get_choices` tool to list valid values."
    )


def choice_validator(value: Any, info: ValidationInfo) -> None | int | str:
    if value is None:
        return None
    choice_dict = get_choice_dict_from_info(info)
    valid_value = get_valid_choice(value, choice_dict)
    if valid_value is not None:
        return valid_value
    raise invalid_choice_error(info.field_name, value, [value], choice_dict)


def multiple_choice_validator(
    values: Any, info: ValidationInfo
) -> None | int | str | list[int | str]:
    if values is None:
        return None
    choice_dict = get_choice_dict_from_info(info)
    values_list = values if isinstance(values, list) else [values]
    valid_values: list[int | str] = []
    for value in values_list:
        # Strip stray leading/trailing delimiters
        cleaned = value.strip(" ,\t\r\n") if isinstance(value, str) else value
        valid_value = get_valid_choice(cleaned, choice_dict)
        if valid_value is not None:
            valid_values.append(valid_value)
            continue
        # Fallback for space- or comma-separated values
        tokens = (
            [t for t in re.split(r"[,\s]+", cleaned) if t]
            if isinstance(cleaned, str)
            else []
        )
        token_values = [get_valid_choice(t, choice_dict) for t in tokens]
        if len(tokens) > 1 and all(v is not None for v in token_values):
            valid_values.extend(token_values)  # type: ignore[arg-type]
            continue
        # Suggest per token only when some token is independently valid
        if len(tokens) > 1 and any(v is not None for v in token_values):
            invalid_parts = [
                t for t, v in zip(tokens, token_values) if v is None
            ]
        else:
            invalid_parts = [cleaned]
        raise invalid_choice_error(
            info.field_name, value, invalid_parts, choice_dict
        )
    return valid_values[0] if len(valid_values) == 1 else valid_values


def in_pre_validator(
    value: Any, info: ValidationInfo
) -> list[int | str] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("in")
        if isinstance(value, str):
            value = value.split(",")
    if isinstance(value, int | str):
        return [value]
    if isinstance(value, list):
        valid_values = []
        for v in value:
            if not isinstance(v, int | str):
                raise ValueError(f"Invalid value '{v}' for {info.field_name}")
            valid_values.append(v)
        return valid_values
    raise ValueError(f"Invalid value '{value}' for {info.field_name}")


def try_coerce_ints(
    value: list[int | str] | int | str, info: ValidationInfo
) -> list[int | str] | int | str:
    if isinstance(value, int | str):
        try:
            return int(value)
        except ValueError:
            return value
    valid_values = []
    for v in value:
        if isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                pass
        valid_values.append(v)
    return valid_values


def in_post_validator(
    value: int | str | list[int | str], info: ValidationInfo
) -> int | str | dict[str, str]:
    if isinstance(value, list):
        return {"in": ",".join([str(v) for v in value])}
    return value


def comma_separated_pre_validator(
    value: Any, info: ValidationInfo
) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(",")
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise ValueError(f"Invalid value '{value}' for {info.field_name}")


def comma_separated_post_validator(
    value: str | list[str], info: ValidationInfo
) -> str:
    if isinstance(value, list):
        return ",".join([str(v) for v in value])
    return value


def is_relative_date_string(value: str) -> bool:
    units = r"(d|days?|m|months?|y|years?)"

    formats = [
        rf"(\d+\s*{units}\s*ago)",
        rf"(-\d+\s*{units})",
        rf"(past\s*\d+\s*{units})",
    ]

    relative_date_pattern = re.compile(
        rf"^({'|'.join(formats)})$", re.IGNORECASE
    )
    return relative_date_pattern.match(value) is not None


def relative_date_validator(
    value: Any, info: ValidationInfo
) -> None | str | date:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        if is_relative_date_string(value):
            return value
        date_adapter = TypeAdapter(date)
        with suppress(Exception):
            return date_adapter.validate_python(value)
    raise ValueError(
        f"'{value}' is not a valid value for {info.field_name}. "
        f"Expected a date or a pattern like '3 days ago', '-2m', 'past 1 year'."
    )


def search_model_validator(data):
    from courtlistener.models import ENDPOINTS

    endpoint_types = {
        "o": "opinion_search",
        "r": "recap_search",
        "d": "recap_docket_search",
        "rd": "recap_document_search",
        "p": "judge_search",
        "oa": "oral_argument_search",
    }

    endpoint_type = data.pop("type") or "o"

    endpoint_model = ENDPOINTS[endpoint_types[endpoint_type]]
    data = {k: v for k, v in data.items() if v is not None}
    return endpoint_model(**data).model_dump(by_alias=True)
