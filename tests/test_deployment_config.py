"""Unit tests for the deployment checks serve.py applies (Unit 6).

deployment_problems() is a pure function, so each rule is tested by handing it
a settings dictionary rather than by changing the environment. Black-box: the
tests state what must stop a deployment and what may only warn.
"""
import pytest

from config import KNOWN_PLACEHOLDER_SECRETS, deployment_problems

GOOD = {"SECRET_KEY": "8f" * 32, "DEBUG": False, "SESSION_COOKIE_SECURE": True,
        "SHOW_DEMO_ACCOUNTS": False}


def check(mode="production", database_ok=True, demo=(), writable=True, **overrides):
    settings = dict(GOOD, **overrides)
    return deployment_problems(settings, mode, database_ok, list(demo), writable)


def levels(found):
    return [level for level, _ in found]


@pytest.mark.blackbox
def test_a_correct_production_configuration_has_no_problems():
    assert check() == []


@pytest.mark.blackbox
@pytest.mark.parametrize("secret", sorted(KNOWN_PLACEHOLDER_SECRETS) + ["short", ""])
@pytest.mark.parametrize("mode", ["production", "demo"])
def test_a_published_or_short_secret_stops_every_mode(secret, mode):
    """Anyone who has read the repository could sign a session cookie."""
    assert "error" in levels(check(mode=mode, SECRET_KEY=secret))


@pytest.mark.blackbox
@pytest.mark.parametrize("mode", ["production", "demo"])
def test_debug_mode_stops_every_mode(mode):
    assert "error" in levels(check(mode=mode, DEBUG=True))


@pytest.mark.blackbox
def test_an_unreachable_database_or_evidence_folder_stops_the_start():
    assert levels(check(database_ok=False)) == ["error"]
    assert levels(check(writable=False)) == ["error"]


@pytest.mark.blackbox
@pytest.mark.parametrize("overrides", [{"SESSION_COOKIE_SECURE": False},
                                       {"SHOW_DEMO_ACCOUNTS": True}])
def test_demo_settings_are_errors_in_production_and_warnings_in_a_demo(overrides):
    assert levels(check(mode="production", **overrides)) == ["error"]
    assert levels(check(mode="demo", **overrides)) == ["warning"]


@pytest.mark.blackbox
def test_an_account_on_the_demonstration_password_blocks_production():
    """A default credential left in place is the misconfiguration this exists for."""
    found = check(demo=["Abdullah.Aljilani", "Auditor01"])
    assert levels(found) == ["error"]
    assert "2 active account(s)" in found[0][1]
    assert levels(check(mode="demo", demo=["Auditor01"])) == ["warning"]
