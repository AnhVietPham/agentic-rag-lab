from src.config import get_settings
from src.db.interfaces.base import BaseDatabase
from src.db.interfaces.postgresql import PostgreSQLDatabase
from src.schemas.database.config import PostgresSettings

def make_database() -> BaseDatabase: 
    """Factory function to create a database instance.

    :returns: An instance of the database
    :rtype: BaseDatabase
    """ 
    # Get settings from centralized config
    settings = get_settings()

    # Create PostgresSQL config from settings
    config = PostgresSettings(
        database_url=settings.postgres_database_url,
        echo_sql=settings.postgres_echo_sql,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
    )

    database = PostgreSQLDatabase(config=config)
    database.startup()
    return database