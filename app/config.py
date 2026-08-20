import os

from dotenv import load_dotenv

load_dotenv()


def is_database_configured():
    """
    checks whether database persistence is configured
    :returns: true when a database connection string is configured
    """
    return bool(os.getenv("DATABASE_URL", "").strip())


def get_database_url():
    """
    returns the validated PostgreSQL connection string from the environment
    :returns: configured PostgreSQL connection string
    """
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    if not database_url.startswith("postgresql+psycopg://"):
        raise ValueError(
            "DATABASE_URL must use the postgresql+psycopg:// connection format"
        )

    return database_url
