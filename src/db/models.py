import typing
import uuid
import enum 
from sqlalchemy import Table
from sqlalchemy import StaticPool
from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Uuid
from sqlalchemy import Enum
from sqlalchemy import ARRAY
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

ChatId = typing.NewType('ChatId', int)

class Base(DeclarativeBase):
    pass

class Role(enum.Enum):
    ADMIN = 'ADMIN'
    SEND_PHRASES = 'SEND_PHRASES'

class User(Base):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[int] = mapped_column(primary_key=True)
    _is_admin: Mapped[bool] = mapped_column(default=False)
    _send_phrases: Mapped[bool] = mapped_column(default=False)

    def is_admin(self):
        return self._is_admin

    def send_phrases(self):
        return self._send_phrases
        
    def has_role(self, role: Role) -> bool:
        if role == Role.ADMIN:
            return self._is_admin
        elif role == Role.SEND_PHRASES:
            return self._send_phrases
        assert False, f'{role} <- {state}'

    def set_role(self, role: Role, state: bool) -> None:
        if role == Role.ADMIN:
            self._is_admin = state
        elif role == Role.SEND_PHRASES:
            self._send_phrases = state
        else:
            assert False, f'{role} <- {state}'

    def __str__(self):
        roles = []
        for role in set(Role):
            if self.has_role(role):
                roles.append(role.value)
        return f'User(chat_id={self.chat_id}, roles={roles})'


class Phrase(Base):
    __tablename__ = "phrase"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(String(100000))

# association_table = Table(
#     "used_phrases",
#     Base.metadata,
#     Column("user_id", ForeignKey("user_account.id")),
#     Column("phrase_id", ForeignKey("phrase.id")),
# )

def init_db():
    engine = create_engine(
        "sqlite:///:memory:", 
        echo=False, 
        connect_args={'check_same_thread':False},
        poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine

init_db_for_testing = init_db