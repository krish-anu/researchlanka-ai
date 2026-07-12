from typing import Any

def describe_value(
    value: Any,
    *,
    depth: int = 0,
    max_depth: int = 2,
    max_dict_keys: int = 12,
) -> Any:
    """
    Return a compact type/shape description
    for a JSON value.
    """

    if depth >= max_depth:
        return type(value).__name__

    if isinstance(value, dict):
        if depth > 0 and len(value) > max_dict_keys:
            sample = list(value.items())[:max_dict_keys]

            return {
                "type": "dict",
                "keys_count": len(value),
                "sample": {
                    key: describe_value(
                        child,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_dict_keys=max_dict_keys,
                    )
                    for key, child in sample
                },
            }

        return {
            key: describe_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                max_dict_keys=max_dict_keys,
            )
            for key, child in value.items()
        }

    if isinstance(value, list):
        if not value:
            return "list[empty]"

        return {
            "type": "list",
            "length": len(value),
            "first_item": describe_value(
                value[0],
                depth=depth + 1,
                max_depth=max_depth,
                max_dict_keys=max_dict_keys,
            ),
        }

    return type(value).__name__
