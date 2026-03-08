"""Tests for demo module."""

from demo import hello


def test_hello():
    """Test the hello function."""
    result = hello()
    assert result == "Hello from demo!"
    assert isinstance(result, str)
