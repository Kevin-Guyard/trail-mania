"""Initialization of the local SQLite database."""

import os
from pathlib import Path
from sqlite3 import Connection

from sqlalchemy import (
    URL,
    Engine,
    Integer,
    MetaData,
    create_engine,
    event,
    inspect,
    select,
)
from sqlalchemy.pool import ConnectionPoolEntry

from trail_mania.models import Base


def get_database_path() -> Path:
    """Resolve the SQLite path in Flet storage or the direct-run fallback.

    Returns
    -------
    pathlib.Path
        Database file inside FLET_APP_STORAGE_DATA, or the project's .flet/storage/data directory.

    Notes
    -----
    This function resolves the location only; it does not create the
    directory or file. An empty storage environment variable uses the fallback.
    """
    storage_directory = os.environ.get("FLET_APP_STORAGE_DATA")
    if storage_directory:
        return Path(storage_directory) / "trail_mania.db"

    project_directory = Path(__file__).resolve().parents[2]
    return project_directory / ".flet" / "storage" / "data" / "trail_mania.db"


def create_database_engine() -> Engine:
    """Create a SQLite engine that enables foreign keys on every connection.

    Returns
    -------
    sqlalchemy.Engine
        New engine for persistent storage; the caller owns disposal.

    Raises
    ------
    OSError
        If the storage directory cannot be created or accessed.

    Notes
    -----
    Creates the parent directory when missing. Table initialization is
    separate, and the engine connects lazily on its first database operation.
    """
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(database_path)))
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def _enable_foreign_keys(connection: Connection, connection_record: ConnectionPoolEntry) -> None:
    """Enable SQLite foreign keys outside any active transaction.

    Parameters
    ----------
    connection : sqlite3.Connection
        DBAPI connection supplied by SQLAlchemy's pool connect event.
    connection_record : sqlalchemy.pool.ConnectionPoolEntry
        Pool entry required by the event signature; otherwise unused.

    Notes
    -----
    The original autocommit mode is restored even if the PRAGMA fails.
    Foreign keys must be enabled per connection for cascades and
    referential checks to apply to every session write.
    """
    # PRAGMA must run outside a transaction, including with newer sqlite3 defaults.
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    finally:
        connection.autocommit = previous_autocommit


def initialize_database() -> None:
    """Create missing tables and migrate supported legacy detail columns.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If table creation or migration fails.
    OSError
        If persistent storage cannot be prepared.

    Notes
    -----
    Existing rows are preserved and no seed data is inserted. The
    temporary initialization engine is always disposed.
    """
    engine = create_database_engine()
    try:
        Base.metadata.create_all(engine)
        _migrate_detail_tables(engine)
    finally:
        engine.dispose()


def _migrate_detail_tables(engine: Engine) -> None:
    """Rebuild legacy detail tables while preserving their existing rows.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        SQLite engine whose current tables have already been created.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If inspection, copying or table replacement fails; the migration rolls back.

    Notes
    -----
    Only integer inclination columns and non-nullable weather columns
    trigger replacement. The current model supplies the updated schema.
    Copying rows and replacing tables share one explicit transaction,
    including under sqlite3's legacy transaction mode.
    """
    with engine.begin() as connection:
        # Legacy sqlite3 mode does not start a transaction for DDL. An explicit
        # BEGIN keeps the copy, drop and rename operations atomic in that mode.
        connection.exec_driver_sql("BEGIN")
        for table in Base.metadata.sorted_tables:
            if "inclination" not in table.c:
                continue
            columns = inspect(connection).get_columns(table.name)
            columns_by_name = {column["name"]: column for column in columns}
            old_inclination = isinstance(columns_by_name["inclination"]["type"], Integer)
            required_weather = not columns_by_name["weather"]["nullable"]
            if not old_inclination and not required_weather:
                continue

            metadata = MetaData()
            # Resolve the replacement table's foreign key against its parent.
            Base.metadata.tables["sessions"].to_metadata(metadata)
            replacement = table.to_metadata(metadata, name=f"_{table.name}_migration")
            replacement.create(connection)
            connection.execute(
                replacement.insert().from_select(
                    [column.name for column in table.c],
                    select(*table.c),
                )
            )
            table.drop(connection)
            connection.exec_driver_sql(f'ALTER TABLE "{replacement.name}" RENAME TO "{table.name}"')
