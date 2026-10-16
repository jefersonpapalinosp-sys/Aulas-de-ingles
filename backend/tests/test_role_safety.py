import pytest

from app.db.role_safety import connect_args, validate_identity


@pytest.mark.parametrize("purpose", ["runtime", "worker"])
def test_papel_sem_ddl_ou_heranca(purpose):
    row = [f"aulas_{purpose}", f"aulas_{purpose}", *([False] * 8)]
    validate_identity(row, purpose)
    for index in range(2, 10):
        wrong = [*row]
        wrong[index] = True
        with pytest.raises(RuntimeError):
            validate_identity(wrong, purpose)
    with pytest.raises(RuntimeError):
        validate_identity(["aulas", "aulas", *([False] * 8)], purpose)


def test_migrador_assume_owner_mas_nao_e_superuser():
    row = ["aulas_owner", "aulas_migrator", *([False] * 5), False, True, True]
    validate_identity(row, "migrator")
    assert connect_args("migrator") == {"server_settings": {"role": "aulas_owner"}}
    assert connect_args("runtime") == {}
    assert connect_args("runtime", {"statement_timeout": "30000", "lock_timeout": "5000"}) == {
        "server_settings": {"statement_timeout": "30000", "lock_timeout": "5000"}
    }
    assert connect_args("migrator", {"statement_timeout": "30000"}) == {
        "server_settings": {"statement_timeout": "30000", "role": "aulas_owner"}
    }
    with pytest.raises(RuntimeError):
        validate_identity(["aulas_owner", "aulas_migrator", True, *row[3:]], "migrator")
