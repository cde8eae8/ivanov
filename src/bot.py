from io import BytesIO
import telebot
from db import models
import exceptions
import user_service as US
import phrases_service as PS
import pandas as pd


def _with_user(*, create: bool, require_roles: set[models.Role] | None = None):
    require_roles = require_roles or []

    def _decorator(f):
        def _impl(self: "Bot", message: telebot.types.Message, *args, **kwargs):
            try:
                with self._create_session() as session:
                    user_service: US.UserService = self._user_service
                    user = user_service.get_user(session, message.chat.id)
                    if not user and create:
                        user = user_service.create_user(session, message.chat.id)
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
            except exceptions.RolesAreRequired:
                self._bot.send_message(message.chat.id, "The action is forbidden")

        return _impl

    return _decorator


class Bot:
    def __init__(
        self,
        bot: telebot.TeleBot,
        create_session,
        user_service: US.UserService,
        phrases_service: PS.PhrasesService,
    ):
        self._bot = bot
        self._create_session = create_session
        self._user_service = user_service
        self._phrases_service = phrases_service

        message_handlers = (
            (self._start, {"start"}),
            (self._help, {"help"}),
            (self._stop, {"stop"}),
            (self._edit, {"edit"}),
        )
        for handler, commands in message_handlers:
            self._bot.message_handler(commands=list(commands))(handler)
        self._bot.message_handler(func=lambda _: True, content_types=["document"])(
            self._document_handler
        )
        self.wait_for_file = {}

    def start_bot(self):
        # set error handler
        self._bot.infinity_polling()

    def stop_bot(self):
        self._bot.stop_bot()

    @_with_user(create=True)
    def _start(self, message: telebot.types.Message, *, session, user):
        self._user_service.change_role(session, user, models.Role.SEND_PHRASES, True)
        if user.is_admin():
            self._bot.send_message(
                message.chat.id, "Hello! You're subscribed now.\nAnd you're an admin"
            )
        else:
            self._bot.send_message(message.chat.id, "Hello! You're subscribed now")

    @_with_user(create=True)
    def _stop(self, message: telebot.types.Message, *, session, user):
        self._user_service.change_role(session, user, models.Role.SEND_PHRASES, False)
        self._bot.send_message(message.chat.id, "You're unsubscribed now")

    @_with_user(create=False)
    def _help(self, message: telebot.types.Message, *, session, user):
        self._bot.send_message(message.chat.id, "Help")

    @_with_user(create=False, require_roles={models.Role.ADMIN})
    def _edit(self, message: telebot.types.Message, *, session, user):
        sent_message = self._bot.send_message(
            message.chat.id, "Reply to this message with a table with new phrases"
        )
        self.wait_for_file[message.chat.id] = sent_message.id

    @_with_user(create=False)
    def _document_handler(self, message: telebot.types.Message, *, session, user):
        if not user.is_admin():
            return
        if not message.reply_to_message:
            return
        message_id = self.wait_for_file.get(message.chat.id)
        if message_id is None:
            self._bot.send_message(
                message.chat.id, "Has no active edit request, send /edit command again"
            )
            return
        if message_id != message.reply_to_message.id:
            self._bot.send_message(
                message.chat.id,
                "Active edit request is bound to another message, send /edit command again",
            )
            return
        file_info = self._bot.get_file(message.document.file_id)
        if file_info.file_size > 200 * 1024:
            self._bot.send_message(message.chat.id, "File is too big")
            return
        # TODO: maybe replace with database UI
        file = self._bot.download_file(file_info.file_path)
        if file_info.file_path.endswith(".csv"):
            try:
                df = pd.read_csv(BytesIO(file), dtype=str)
            except pd.errors.EmptyDataError as e:
                self._bot.send_message(message.chat.id, "Empty file")
                return
            except Exception as e:
                self._bot.send_message(
                    message.chat.id, "Bad file format, unknown error"
                )
                return
        else:
            self._bot.send_message(message.chat.id, "Bad file format")
            return
        column = "Цитаты"
        if df.columns.shape != (1,) or df.columns != [column]:
            self._bot.send_message(
                message.chat.id, f"Bad file format, expected 1 column '{column}'"
            )
            return
        df = df.fillna("")
        phrases = df["Цитаты"].tolist()
        self._phrases_service.add_phrases(session, phrases)
        self.wait_for_file[message.chat.id] = None
