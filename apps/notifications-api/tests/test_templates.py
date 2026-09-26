import pytest

from notifications_app.templates import (
    TemplateValidationError,
    render_template,
    template_fields,
    validate_template,
)


def test_render_template_accepts_exact_variables() -> None:
    title, body = render_template(
        "Termen {resource_id}",
        "Acțiune: {action}",
        ["resource_id", "action"],
        {"resource_id": "abc", "action": "due"},
    )
    assert title == "Termen abc"
    assert body == "Acțiune: due"


@pytest.mark.parametrize(
    ("value", "variables"),
    [
        ("{user.name}", ["user.name"]),
        ("{user[0]}", ["user[0]"]),
        ("{value!r}", ["value"]),
        ("{value:>10}", ["value"]),
    ],
)
def test_template_rejects_expression_or_formatting(value: str, variables: list[str]) -> None:
    with pytest.raises(TemplateValidationError):
        validate_template(value, "Static", variables)


def test_template_rejects_unknown_declared_and_runtime_variables() -> None:
    with pytest.raises(TemplateValidationError, match="Unknown"):
        validate_template("{secret}", "Static", ["allowed"])
    with pytest.raises(TemplateValidationError, match="unknown"):
        render_template("{allowed}", "Static", ["allowed"], {"other": "value"})


def test_template_fields_never_evaluates_values() -> None:
    assert template_fields("Document {resource_id}") == {"resource_id"}
