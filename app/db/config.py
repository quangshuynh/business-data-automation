import os


def is_database_configured():
    """
    checks whether database persistence is configured
    :returns: true when a database connection string is configured
    """
    return bool(os.getenv("DATABASE_URL"))


def get_database_url():
    """
    returns the PostgreSQL connection string from the environment
    :returns: configured PostgreSQL connection string
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    return database_url
