"""
Tests for adx_exporter.
Run locally with: pytest tests/ -v
"""

import os
import sys

from datetime import datetime, timedelta

# Make sure project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from function_app import kusto_val, sanitise_row
from queries import QUERIES, safe_tag

QUERIES_DIR = os.path.join(os.path.dirname(__file__), "..", "queries")
INIT_PY = os.path.join(QUERIES_DIR, "__init__.py")


# ── 1. __init__.py — every .kql file on disk must be referenced ───────────

def test_every_kql_file_referenced_in_init():
    """
    Every .kql file in queries/ must be referenced in queries/__init__.py.
    If you add a new .kql file, you must also add it to the QUERIES list.
    """
    init_content = open(INIT_PY).read()
    kql_files = [f for f in os.listdir(QUERIES_DIR) if f.endswith(".kql")]

    missing = []
    for filename in kql_files:
        if filename not in init_content:
            missing.append(filename)

    assert not missing, (
        f"These .kql files are not referenced in queries/__init__.py:\n"
        + "\n".join(f"  - {f}" for f in missing)
        + "\n\nAdd each one to the QUERIES list in queries/__init__.py"
    )


# ── 2. QUERIES list — every entry must be valid and complete ──────────────

def test_queries_list_not_empty():
    """QUERIES list must have at least one entry."""
    assert len(QUERIES) > 0, "QUERIES list in __init__.py is empty"


def test_every_query_has_required_fields():
    """Every query in QUERIES must have all 5 required fields."""
    required = {"name", "metric_name", "metric_value_col", "tags_fn", "kql"}
    for q in QUERIES:
        missing = required - q.keys()
        assert not missing, (
            f"Query '{q.get('name', 'unknown')}' is missing fields: {missing}"
        )


def test_every_query_kql_not_empty():
    """Every query's KQL string must not be empty."""
    for q in QUERIES:
        assert q["kql"].strip() != "", (
            f"Query '{q['name']}' has an empty KQL string"
        )


def test_every_query_tags_fn_is_callable():
    """Every query's tags_fn must be a callable (lambda or function)."""
    for q in QUERIES:
        assert callable(q["tags_fn"]), (
            f"Query '{q['name']}' tags_fn is not callable"
        )


# ── 3. sanitise_row — cleans ADX row data before sending to Datadog ──────

def test_sanitise_row_none_becomes_unknown():
    """None values must be replaced with the string 'unknown'."""
    row = {"Account": None, "TruckName": "Truck1"}
    result = sanitise_row(row)
    assert result["Account"] == "unknown"
    assert result["TruckName"] == "Truck1"


def test_sanitise_row_converts_numbers_to_string():
    """Numeric values must be converted to strings."""
    row = {"Count": 42, "Value": 3.14}
    result = sanitise_row(row)
    assert result["Count"] == "42"
    assert result["Value"] == "3.14"


def test_sanitise_row_empty_row():
    """Empty row must return empty dict without crashing."""
    assert sanitise_row({}) == {}


# ── 4. safe_tag — builds Datadog tags from row values ────────────────────

def test_safe_tag_normal():
    """Normal tag must be built as key:value."""
    assert safe_tag("account", "Verifi") == "account:Verifi"


def test_safe_tag_none_becomes_unknown():
    """None value must become 'unknown' so Datadog tag is never empty."""
    assert safe_tag("account", None) == "account:unknown"


def test_safe_tag_colon_in_value_replaced():
    """
    Colons inside tag values break Datadog — they must be replaced with _.
    e.g. "some:value" → "account:some_value"
    """
    assert safe_tag("account", "some:value") == "account:some_value"


def test_safe_tag_number_value():
    """Numeric values must be converted to string in the tag."""
    assert safe_tag("count", 42) == "count:42"


# ── 5. kusto_val — converts ADX column values to safe Python types ────────

def test_kusto_val_none_returns_none():
    """None must pass through as None (handled separately by sanitise_row)."""
    assert kusto_val(None) is None


def test_kusto_val_number_becomes_string():
    """Numbers must be converted to strings."""
    assert kusto_val(42) == "42"


def test_kusto_val_datetime_becomes_iso():
    """Datetime values must be converted to ISO format string."""
    dt = datetime(2024, 1, 15, 10, 30, 0)
    assert kusto_val(dt) == "2024-01-15T10:30:00"


def test_kusto_val_timedelta_becomes_string():
    """Timedelta values must be converted to string."""
    result = kusto_val(timedelta(seconds=90))
    assert isinstance(result, str)
    assert result != ""
