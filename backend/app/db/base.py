"""Base declarativa compartilhada por todos os modelos."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Todo modelo herda daqui — é o que o Alembic usa como metadata."""
