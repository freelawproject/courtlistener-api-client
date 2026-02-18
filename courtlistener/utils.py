import re
from contextlib import suppress
from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter, ValidationInfo

if TYPE_CHECKING:
    from courtlistener.models import Endpoint


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
    extra = getattr(field, "json_schema_extra", {})
    related_class_name = extra.get("related_class_name", None)
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
    extra = getattr(field, "json_schema_extra", {})
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
    return None


def choice_validator(value: Any, info: ValidationInfo) -> None | int | str:
    if value is None:
        return None
    choice_dict = get_choice_dict_from_info(info)
    valid_value = get_valid_choice(value, choice_dict)
    if valid_value is not None:
        return valid_value
    raise ValueError(f"{info.field_name} must be one of {choice_dict}")


def multiple_choice_validator(
    values: Any, info: ValidationInfo
) -> None | int | str | list[int | str]:
    if values is None:
        return None
    choice_dict = get_choice_dict_from_info(info)
    values_list = values if isinstance(values, list) else [values]
    valid_values = []
    for value in values_list:
        valid_value = get_valid_choice(value, choice_dict)
        if valid_value is None:
            raise ValueError(
                f"Invalid value '{value}' for {info.field_name}. Must be in {choice_dict}"
            )
        valid_values.append(valid_value)
    return valid_values[0] if len(valid_values) == 1 else valid_values


def in_pre_validator(value: Any, info: ValidationInfo) -> list[int | str]:
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
    value: list[int | str], info: ValidationInfo
) -> list[int | str]:
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

    endpoint_type = data.pop("type", "o")

    endpoint_model = ENDPOINTS[endpoint_types[endpoint_type]]
    return endpoint_model(**data).model_dump(by_alias=True)
