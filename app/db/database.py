from pathlib import Path

from app.db.config import get_database_url


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect_to_database():
    """
    creates a connection to the configured PostgreSQL database
    :returns: open PostgreSQL database connection
    """
    import psycopg

    return psycopg.connect(get_database_url())


def initialize_database():
    """
    creates the PostgreSQL tables defined by the project schema
    :returns: none
    """
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema)
