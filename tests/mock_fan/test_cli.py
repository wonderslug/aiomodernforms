"""Unit tests for mock_fan.__main__ argument parsing."""

import pytest

from mock_fan.__main__ import _parse_args


def test_generation_is_required():
    """--generation is required; omitting it is a usage error."""
    with pytest.raises(SystemExit):
        _parse_args([])


def test_defaults():
    """host/port/breeze default sensibly when only --generation is given."""
    args = _parse_args(["--generation", "gen1_2"])
    assert args.generation == "gen1_2"
    assert args.breeze is False
    assert args.host == "0.0.0.0"
    assert args.port == 8080


def test_breeze_flag_and_overrides():
    """--breeze, --host, and --port are parsed correctly when given."""
    args = _parse_args(
        ["--generation", "gen3", "--breeze", "--host", "127.0.0.1", "--port", "9090"]
    )
    assert args.generation == "gen3"
    assert args.breeze is True
    assert args.host == "127.0.0.1"
    assert args.port == 9090


def test_invalid_generation_rejected():
    """An unrecognized --generation value is a usage error."""
    with pytest.raises(SystemExit):
        _parse_args(["--generation", "gen99"])


def test_light_defaults_to_true():
    """--light defaults to True when neither --light nor --no-light is given."""
    args = _parse_args(["--generation", "gen1_2"])
    assert args.light is True


def test_no_light_flag():
    """--no-light sets args.light to False."""
    args = _parse_args(["--generation", "gen1_2", "--no-light"])
    assert args.light is False


def test_explicit_light_flag():
    """--light explicitly sets args.light to True."""
    args = _parse_args(["--generation", "gen1_2", "--light"])
    assert args.light is True


def test_gen4_generation_accepted():
    """--generation gen4 is a valid choice, distinct from the PROFILES dict."""
    args = _parse_args(["--generation", "gen4"])
    assert args.generation == "gen4"


def test_lights_defaults_to_one():
    """--lights defaults to 1 when omitted."""
    args = _parse_args(["--generation", "gen4"])
    assert args.lights == 1


def test_lights_explicit_value():
    """--lights accepts an explicit integer count."""
    args = _parse_args(["--generation", "gen4", "--lights", "3"])
    assert args.lights == 3


def test_lights_zero():
    """--lights 0 is accepted (a Gen4 fan with no lights)."""
    args = _parse_args(["--generation", "gen4", "--lights", "0"])
    assert args.lights == 0
