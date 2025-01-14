from db import models
import exceptions
from sqlalchemy import select


# TODO: make thread safe
class UserService:
    def __init__(self):
        pass

    def get_admin_chats(self, session) -> list[models.ChatId] | None:
        stmt = select(models.User).where(models.User._is_admin)
        admins = session.execute(stmt).all()
        return [u[0].chat_id for u in admins]

    def get_user(self, session, chat_id: models.ChatId) -> models.User | None:
        stmt = select(models.User).where(models.User.chat_id == chat_id)
        user = session.execute(stmt).one_or_none()
        if user is None:
            return None
        return user[0]

    def create_user(
        self, session, chat_id: models.ChatId, username: str
    ) -> models.User:
        # TODO: handle concurrent insertion of one user
        # TODO: make session external to functions (see sqlalchemy docs)
        user = models.User(chat_id=chat_id, username=username)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    def change_role(
        self, session, user: models.User, role: models.Role, state: bool
    ) -> None:
        if role == models.Role.ADMIN and not user.is_admin():
            raise exceptions.RolesAreRequired(models.Role.ADMIN)
        # TODO: handle concurrent update
        user.set_role(role, state)
        session.commit()
