"""
tests/conftest.py – Shared fixtures for all tests.
"""
import datetime
import pytest


@pytest.fixture()
def cutoff_date() -> datetime.date:
    return datetime.date(2016, 12, 31)
