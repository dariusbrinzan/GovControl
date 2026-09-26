from string import Formatter


class TemplateValidationError(ValueError):
    pass


def template_fields(value: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, format_spec, conversion in Formatter().parse(value):
        if field_name is None:
            continue
        if not field_name or "." in field_name or "[" in field_name or format_spec or conversion:
            raise TemplateValidationError(
                "Only simple placeholders without formatting are allowed."
            )
        fields.add(field_name)
    return fields


def validate_template(title: str, body: str, allowed_variables: list[str]) -> None:
    used = template_fields(title) | template_fields(body)
    allowed = set(allowed_variables)
    unknown = used - allowed
    unused = allowed - used
    if unknown:
        raise TemplateValidationError(f"Unknown template variables: {', '.join(sorted(unknown))}")
    if unused:
        raise TemplateValidationError(f"Unused allowed variables: {', '.join(sorted(unused))}")


def render_template(
    title: str, body: str, allowed_variables: list[str], variables: dict[str, str]
) -> tuple[str, str]:
    validate_template(title, body, allowed_variables)
    expected = set(allowed_variables)
    provided = set(variables)
    if expected != provided:
        missing = expected - provided
        unknown = provided - expected
        detail = []
        if missing:
            detail.append(f"missing: {', '.join(sorted(missing))}")
        if unknown:
            detail.append(f"unknown: {', '.join(sorted(unknown))}")
        raise TemplateValidationError("Invalid template variables (" + "; ".join(detail) + ")")
    safe = {key: str(value) for key, value in variables.items()}
    return title.format_map(safe), body.format_map(safe)
