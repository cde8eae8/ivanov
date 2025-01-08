from db import models
import exceptions
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
import sqlalchemy
from sqlalchemy import select
from sqlalchemy import insert
from sqlalchemy import update


# TODO: make thread safe
class UserService:
    def __init__(self):
        pass
        
    def get_user(self, session, chat_id: models.ChatId) -> models.User | None:
        stmt = select(models.User).where(models.User.chat_id == chat_id)
        user = session.execute(stmt).one_or_none()
        if user is None:
            return None
        return user[0]

    def create_user(self, session, chat_id: models.ChatId) -> models.User:
        # TODO: handle concurrent insertion of one user
        # TODO: make session external to functions (see sqlalchemy docs)
        user = models.User(chat_id=chat_id)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    def change_role(self, session, user: models.User, role: models.Role, state: bool) -> None:
        if role == models.Role.ADMIN and not user.is_admin():
            raise exceptions.RolesAreRequired(models.Role.ADMIN)
        # TODO: handle concurrent update
        user.set_role(role, state)
        session.commit()
        
    def get_users_with_role(self, session, role: models.Role) -> list[models.User]:
        stmt = select(models.User).where(role in models.User.roles)
        return list(session.execute(stmt).all())