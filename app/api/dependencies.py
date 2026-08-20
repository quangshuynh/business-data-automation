from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import (
    create_database_engine,
    create_session_factory,
    database_session,
)


@lru_cache
def get_api_engine():
    """
    returns the shared SQLAlchemy engine used by the API
    :returns: configured SQLAlchemy database engine
    """
    return create_database_engine()


def get_database_session():
    """
    provides a database session for an API request
    :returns: transactional SQLAlchemy database session
    """
    try:
        session_factory = create_session_factory(get_api_engine())
    except (ValueError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not available",
        ) from error

    try:
        with database_session(session_factory) as session:
            yield session
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database operation failed",
        ) from error
