from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_database_url
from app.db.models import Base


def create_database_engine(database_url=None):
    """
    creates a SQLAlchemy engine for the configured database
    :param database_url: optional database connection string override
    :returns: configured SQLAlchemy engine
    """
    connection_string = database_url or get_database_url()

    return create_engine(connection_string, pool_pre_ping=True)


def create_session_factory(engine):
    """
    creates a database session factory bound to an engine
    :param engine: SQLAlchemy database engine
    :returns: configured SQLAlchemy session factory
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def database_session(session_factory):
    """
    provides a transactional database session
    :param session_factory: factory used to create the database session
    :returns: transactional SQLAlchemy session
    """
    session = session_factory()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_database(engine=None):
    """
    creates database tables defined by the SQLAlchemy models
    :param engine: optional SQLAlchemy database engine
    :returns: none
    """
    database_engine = engine or create_database_engine()

    Base.metadata.create_all(database_engine)
