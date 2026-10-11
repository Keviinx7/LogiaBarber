from unittest.mock import MagicMock

import pytest

from tests.p0_database import TARGET, require_target_connection, require_target_url
from tests import p0_database


@pytest.mark.parametrize("name", ["logia_barber", "logia_barber_test", "another_test", "postgres", "logia_barber_p0_test_extra"])
def test_wrong_database_url_is_rejected(name):
    with pytest.raises(ValueError):
        require_target_url(f"postgresql+psycopg:///{name}")


@pytest.mark.parametrize("actual", ["logia_barber", "other_test", "postgres"])
def test_wrong_actual_database_is_rejected(actual):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (actual,)
    with pytest.raises(ValueError):
        require_target_connection(connection)
    cursor.execute.assert_called_once_with("SELECT current_database()")
    connection.rollback.assert_called_once_with()


def test_exact_target_is_accepted():
    assert require_target_url(f"postgresql+psycopg:///{TARGET}").database == TARGET
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (TARGET,)
    require_target_connection(connection)


@pytest.mark.parametrize("readonly", [False, True])
def test_engine_keeps_physical_guard_and_enforces_readonly_when_requested(monkeypatch, readonly):
    factory, listen = MagicMock(), MagicMock()
    monkeypatch.setattr(p0_database, "create_engine", factory)
    monkeypatch.setattr(p0_database.event, "listen", listen)
    engine = p0_database.test_engine(f"postgresql+psycopg:///{TARGET}", readonly=readonly)
    assert engine is factory.return_value
    options = factory.call_args.kwargs["connect_args"]["options"]
    expected = "-c statement_timeout=15000 -c lock_timeout=10000"
    assert options == expected + (" -c default_transaction_read_only=on" if readonly else "")
    listen.assert_called_once_with(engine, "connect", require_target_connection)
