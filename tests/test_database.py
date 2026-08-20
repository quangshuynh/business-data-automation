from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.db import database
from app.db.config import get_database_url


SCHEMA_PATH = Path(__file__).parents[1] / "app" / "db" / "schema.sql"


def test_get_database_url_reads_environment_variable(monkeypatch):
    """
    tests that database configuration is read from the environment
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    database_url = "postgresql://user:password@localhost:5432/business_data"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert get_database_url() == database_url


def test_get_database_url_requires_environment_variable(monkeypatch):
    """
    tests that missing database configuration raises an error
    :param monkeypatch: pytest fixture for changing environment variables
    :returns: none
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(
        ValueError,
        match="DATABASE_URL environment variable is required",
    ):
        get_database_url()


def test_schema_defines_tables_and_relationships():
    """
    tests that the database schema defines required tables and foreign keys
    :returns: none
    """
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    assert "create table if not exists customers" in schema
    assert "create table if not exists orders" in schema
    assert "create table if not exists payments" in schema
    assert "references customers (customer_id)" in schema
    assert "references orders (order_id)" in schema


def test_initialize_database_executes_schema(monkeypatch):
    """
    tests that database initialization executes the project schema
    :param monkeypatch: pytest fixture for replacing the database connection
    :returns: none
    """
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(database, "connect_to_database", lambda: connection)

    database.initialize_database()

    expected_schema = SCHEMA_PATH.read_text(encoding="utf-8")
    cursor.execute.assert_called_once_with(expected_schema)
