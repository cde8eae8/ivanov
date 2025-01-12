import dataclasses
import typing
import pytest
import sqlalchemy
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from db import models


@dataclasses.dataclass
class Database:
    engine: sqlalchemy.Engine
    session: typing.Callable[[], sqlalchemy.orm.Session]


@pytest.fixture
def testing_db():
    engine = models.init_db_for_testing()
    yield Database(engine, scoped_session(sessionmaker(engine)))
