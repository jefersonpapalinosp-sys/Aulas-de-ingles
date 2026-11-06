"""Base declarativa compartilhada por todos os modelos."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Todo modelo herda daqui — é o que o Alembic usa como metadata."""

    metadata = MetaData(
        naming_convention={
            "pk": "%(table_name)s_pkey",
            "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
            "uq": "%(table_name)s_%(column_0_N_name)s_key",
            "ix": "ix_%(column_0_label)s",
            "ck": "ck_%(table_name)s_%(column_0_name)s",
        }
    )
