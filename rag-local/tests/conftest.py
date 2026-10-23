"""Shared fixtures for all tests in this project.

Each fixture provides a clean, deterministic test environment.
No test hits a real network or external service.
"""
from __future__ import annotations

import pytest


# Register custom markers in pyproject.toml or pytest.ini
# This conftest ensures consistent fixture loading across test suites.
