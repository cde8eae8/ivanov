import logging
import typing
import uuid
import enum
import datetime as dt
from sqlalchemy import PrimaryKeyConstraint, func
from sqlalchemy import StaticPool
from sqlalchemy import create_engine
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Uuid
from sqlalchemy import event
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

logger = logging.getLogger(__name__)

ChatId = typing.NewType("ChatId", int)


class Base(DeclarativeBase):
    pass


class Role(enum.Enum):
    ADMIN = "ADMIN"
    SEND_PHRASES = "SEND_PHRASES"


class User(Base):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4, index=True
    )
    chat_id: Mapped[int] = mapped_column(unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    time_created: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    _is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    _send_phrases: Mapped[bool] = mapped_column(default=False, nullable=False)

    def is_admin(self):
        return self._is_admin

    def send_phrases(self):
        return self._send_phrases

    def has_role(self, role: Role) -> bool:
        if role == Role.ADMIN:
            return self._is_admin
        elif role == Role.SEND_PHRASES:
            return self._send_phrases
        assert False, role

    def set_role(self, role: Role, state: bool) -> None:
        if role == Role.ADMIN:
            self._is_admin = state
        elif role == Role.SEND_PHRASES:
            self._send_phrases = state
        else:
            assert False, f"{role} <- {state}"

    def __repr__(self):
        roles = []
        for role in set(Role):
            if self.has_role(role):
                roles.append(role.value)
        return f"User(id={self.id}, chat_id={self.chat_id}, roles={roles})"


class Phrase(Base):
    __tablename__ = "phrase"
    time_created: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4, nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(100000), unique=True, nullable=False)


class UsedPhrases(Base):
    __tablename__ = "used_phrases"
    user_id = mapped_column(ForeignKey("user_account.id"), nullable=False)
    phrase_id = mapped_column(ForeignKey("phrase.id"), nullable=False)
    time_created: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "phrase_id", name="used_phrases"),
    )


def _common_db_init(engine):
    def _fk_pragma_on_connect(dbapi_con, con_record):
        dbapi_con.execute("pragma foreign_keys=ON")

    event.listen(engine, "connect", _fk_pragma_on_connect)

    Base.metadata.create_all(engine)


def init_db(db_path):
    logger.info(f"Using database {db_path}")
    engine = create_engine(db_path)
    _common_db_init(engine)
    return engine


def init_db_for_testing(echo=False):
    engine = create_engine(
        "sqlite:///:memory:",
        echo=echo,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _common_db_init(engine)
    return engine
