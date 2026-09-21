import pytest
from pydantic import ValidationError

from app.schemas.platform import DepartmentCreate, UserCreate


def test_department_code_is_normalized() -> None:
    department = DepartmentCreate(name=" Legal Department ", code=" legal ")

    assert department.name == "Legal Department"
    assert department.code == "LEGAL"


def test_department_name_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        DepartmentCreate(name="   ")


def test_user_email_is_normalized() -> None:
    user = UserCreate(email="Officer@EXAMPLE.COM", display_name=" Legal Officer ")

    assert user.email == "officer@example.com"
    assert user.display_name == "Legal Officer"


def test_user_email_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", display_name="Legal Officer")
