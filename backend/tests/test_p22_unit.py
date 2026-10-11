"""P2.2 offline contracts and real Argon2id operations; no database access."""
import base64
import hashlib
import importlib
import re

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.models import Appointment, Barber, User


@pytest.fixture
def credentials():
    return importlib.import_module("app.core.credentials")


@pytest.fixture
def session_model():
    return importlib.import_module("app.models.models").AuthSession


def test_role_contract_has_exactly_four_roles_and_no_default():
    role = User.__table__.c.role
    assert role.default is None
    assert role.server_default is None
    assert role.nullable is False
    check = next(c for c in User.__table__.constraints
                 if isinstance(c, CheckConstraint) and c.name == "ck_users_role")
    assert set(re.findall(r"'([^']+)'", str(check.sqltext))) == {
        "owner", "admin", "barber", "client",
    }
    assert User(name="Synthetic", email="synthetic@example.invalid",
                password_hash="unusable-test-marker").role is None


@pytest.mark.parametrize("model,column", [(Barber, "user_id"), (Appointment, "client_user_id")])
def test_historical_identity_links_are_nullable_restrict_foreign_keys(model, column):
    field = model.__table__.c[column]
    assert field.nullable is True
    assert field.default is None and field.server_default is None
    fk, = field.foreign_keys
    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "RESTRICT"


def test_barber_identity_is_unique_and_appointment_identity_is_not():
    uniques = {c.name: tuple(c.columns.keys()) for c in Barber.__table__.constraints
               if isinstance(c, UniqueConstraint)}
    assert uniques["uq_barbers_user_id"] == ("user_id",)
    assert not any(isinstance(c, UniqueConstraint) and "client_user_id" in c.columns
                   for c in Appointment.__table__.constraints)


def test_p0_model_exclusion_statuses_and_required_barber_remain():
    table = Appointment.__table__
    assert table.c.barber_id.nullable is False
    assert table.c.client_name.nullable is False
    assert table.c.client_phone.nullable is False
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert set(re.findall(r"'([^']+)'", checks["ck_appointments_status"])) == {
        "pending", "confirmed", "cancelled", "completed", "no_show",
    }
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "ex_appointments_active_barber_time_overlap EXCLUDE USING gist" in ddl
    assert "barber_id WITH =" in ddl
    assert "tstzrange(starts_at, ends_at, '[)') WITH &&" in ddl
    assert "WHERE (status IN ('pending', 'confirmed'))" in ddl


def test_session_columns_have_only_hashes_and_appropriate_types(session_model):
    table = session_model.__table__
    assert table.name == "auth_sessions"
    assert set(table.c.keys()) == {
        "id", "user_id", "session_token_hash", "csrf_token_hash",
        "created_at", "expires_at", "revoked_at",
    }
    assert tuple(table.primary_key.columns.keys()) == ("id",)
    for name in ("session_token_hash", "csrf_token_hash"):
        assert table.c[name].type.length == 64
        assert table.c[name].nullable is False
    for name in ("created_at", "expires_at", "revoked_at"):
        assert table.c[name].type.timezone is True
    assert table.c.created_at.server_default is not None
    assert table.c.created_at.nullable is False
    assert table.c.expires_at.nullable is False
    assert table.c.revoked_at.nullable is True
    assert table.c.user_id.nullable is False
    fk, = table.c.user_id.foreign_keys
    assert fk.target_fullname == "users.id" and fk.ondelete == "RESTRICT"
    assert any(isinstance(c, UniqueConstraint)
               and c.name == "uq_auth_sessions_session_token_hash"
               and tuple(c.columns.keys()) == ("session_token_hash",)
               for c in table.constraints)


def test_hash_is_argon2id_with_salt_and_positive_work_factors(credentials):
    from argon2 import extract_parameters
    from argon2.low_level import Type

    password = "Synthetic credential for offline tests"
    encoded = credentials.hash_password(password)
    assert bool(encoded != password)
    parameters = extract_parameters(encoded)
    assert parameters.type is Type.ID
    assert parameters.version == 19
    assert parameters.salt_len >= 16
    assert parameters.hash_len >= 16
    assert parameters.memory_cost >= 19456
    assert parameters.time_cost >= 2
    assert parameters.parallelism >= 1


def test_password_correct_incorrect_and_independent_verifier(credentials):
    from argon2 import PasswordHasher

    password = "Synthetic correct credential"
    encoded = credentials.hash_password(password)
    assert credentials.verify_password(password, encoded) is True
    assert credentials.verify_password("Synthetic wrong credential", encoded) is False
    assert PasswordHasher().verify(encoded, password) is True


@pytest.mark.parametrize("password,changed", [
    ("  synthetic password  ", "synthetic password"),
    (" synthetic", "synthetic"),
    ("synthetic ", "synthetic"),
    ("\t synthetic\n", "synthetic"),
    ("\u00a0synthetic\u00a0", "synthetic"),
    ("contraseña 🔐 日本語", "contrasena 🔐 日本語"),
    ("caf\u00e9", "cafe\u0301"),
], ids=["both-spaces", "leading", "trailing", "tabs-newline", "nbsp", "unicode", "no-normalization"])
def test_password_bytes_preserve_whitespace_and_unicode(credentials, password, changed):
    encoded = credentials.hash_password(password)
    assert credentials.verify_password(password, encoded) is True
    assert credentials.verify_password(changed, encoded) is False


@pytest.mark.parametrize("password", ["", " ", "a"], ids=["empty", "space", "short"])
def test_hash_utility_does_not_invent_business_password_policy(credentials, password):
    assert credentials.verify_password(password, credentials.hash_password(password)) is True


def test_repeated_password_gets_independent_random_salt(credentials):
    password = "Synthetic salt check"
    first = credentials.hash_password(password)
    second = credentials.hash_password(password)
    assert bool(first != second)
    assert credentials.verify_password(password, first) is True
    assert credentials.verify_password(password, second) is True


@pytest.mark.parametrize("malformed", ["", "not-a-hash", "$argon2id$", "$argon2id$v=19$m=bad,t=2,p=1$x$x"],
                         ids=["empty", "plain", "truncated", "invalid-parameters"])
def test_invalid_hash_fails_closed(credentials, malformed):
    assert credentials.verify_password("Synthetic malformed-hash check", malformed) is False


def test_credentials_do_not_emit_passwords_hashes_or_tokens(credentials, caplog, capsys):
    password = "Synthetic no-logging check"
    encoded = credentials.hash_password(password)
    credentials.verify_password(password, encoded)
    credentials.verify_password("wrong synthetic password", encoded)
    captured = capsys.readouterr()
    emitted = caplog.text + captured.out + captured.err
    assert bool(password not in emitted)
    assert bool(encoded not in emitted)


@pytest.mark.parametrize("value", [None, b"synthetic", 123], ids=["none", "bytes", "integer"])
def test_password_helpers_reject_invalid_types_without_coercion(credentials, value):
    with pytest.raises(TypeError):
        credentials.hash_password(value)
    assert credentials.verify_password(value, "invalid-hash") is False
    assert credentials.verify_password("synthetic", value) is False


def test_tokens_are_independent_and_have_256_bits_of_random_material(credentials):
    tokens = [credentials.generate_token() for _ in range(16)]
    assert len(set(tokens)) == len(tokens)
    assert all(len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) >= 32
               for token in tokens)


def test_token_digest_is_sha256_and_preserves_exact_secret(credentials):
    token = credentials.generate_token()
    digest = credentials.hash_token(token)
    assert bool(digest == hashlib.sha256(token.encode("utf-8")).hexdigest())
    assert bool(digest != token)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert bool(credentials.hash_token(token) == digest)
    assert bool(credentials.hash_token(" " + token) != digest)
    assert bool(credentials.hash_token("synthetic 🔐") == hashlib.sha256("synthetic 🔐".encode()).hexdigest())


def test_token_helpers_emit_no_secrets(credentials, caplog, capsys):
    token = credentials.generate_token()
    digest = credentials.hash_token(token)
    captured = capsys.readouterr()
    emitted = caplog.text + captured.out + captured.err
    assert bool(token not in emitted and digest not in emitted)
