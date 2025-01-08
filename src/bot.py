import telebot
from db import models
import exceptions
import user_service as US
import sqlalchemy

def _with_user(*, create: bool, require_roles: set[models.Role] | None=None):
    require_roles = require_roles or []
    def _decorator(f):
        def _impl(self, message: telebot.types.Message, *args, **kwargs):
            with self._create_session() as session:
                user_service: US.UserService = self._user_service
                user = user_service.get_user(session, message.chat.id)
                print(f'got user {user}')
                if not user and create:
                    print(f'create user')
                    user = user_service.create_user(session, message.chat.id)
                print(f'using user {user}')
                if require_roles:
                    if not user:
                        raise exceptions.RolesAreRequired(require_roles)
                    absent_roles = set()
                    for role in require_roles:
                        if not user.has_role(role):
                            absent_roles.add(role)
                    if absent_roles:
                        raise exceptions.RolesAreRequired(list(absent_roles))
                kwargs["user"] = user
                kwargs["session"] = session
                f(self, message, *args, **kwargs)

        return _impl
    return _decorator

class Bot:
    def __init__(self, token, create_session, user_service: US.UserService):
        self._token = token
        self._bot = telebot.TeleBot(self._token)
        self._create_session = create_session
        self._user_service = user_service

        message_handlers = (
            (self._start, {'start'}),
            (self._help, {'help'}),
            (self._stop, {'stop'}),
            (self._edit, {'edit'}),
        )
        for handler, commands in message_handlers:
            self._bot.message_handler(commands=list(commands))(handler)

    def start_bot(self):
        # set error handler
        self._bot.infinity_polling()

    def stop_bot(self):
        self._bot.stop_bot()

    @_with_user(create=True)
    def _start(self, message, *, session, user):
        print('start', user)
        self._user_service.change_role(session, user, models.Role.SEND_PHRASES, True)
        if user.is_admin():
            self._bot.send_message(message.chat.id, "Hello! You're subscribed now.\nAnd you're an admin")
        else:
            self._bot.send_message(message.chat.id, "Hello! You're subscribed now")

    @_with_user(create=True)
    def _stop(self, message, *, session, user):
        print('stop', user)
        self._user_service.change_role(session, user, models.Role.SEND_PHRASES, False)
        self._bot.send_message(message.chat.id, "You're unsubscribed now")

    @_with_user(create=False)
    def _help(self, message, *, session, user):
        self._bot.send_message(message.chat.id, "Help")

    @_with_user(create=False, require_roles={models.Role.ADMIN})
    def _edit(self, message, *, session, user):
        print('edit', user)
        self._bot.send_message(message.chat.id, "Reply to this message with a table with new phrases")