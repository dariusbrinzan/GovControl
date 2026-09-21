import pytest
from pydantic import ValidationError

from app.schemas.platform import DepartmentCreate


def test_department_code_is_normalized() -> None:
    department = DepartmentCreate(name=" Legal Department ", code=" legal ")

    assert department.name == "Legal Department"
    assert department.code == "LEGAL"


def test_department_name_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        DepartmentCreate(name="   ")
