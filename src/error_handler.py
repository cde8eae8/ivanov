import abc
import contextlib
import dataclasses
import io
import logging
import shlex
import sys
import typing
import telebot
import threading
import traceback

import mail

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class ExceptionInfo:
    exception: Exception
    was_expected: bool = False
    logs: list[str] | None = None
    version: str | None = None
    _command_line: str | None = None
    _thread_name: str | None = None

class ErrorHandler:
    @abc.abstractmethod
    def notify(self, e: ExceptionInfo):
        pass

class LoggerNotifier(ErrorHandler):
    def notify(self, e: ExceptionInfo):
        logger.error(''.join(traceback.format_exception(e.exception)))

class TelegramErrorHandler(ErrorHandler):
    def __init__(self, create_bot, admin_chats: list[int]):
        self._create_bot = create_bot 
        self.admin_chats = admin_chats

    def notify(self, e: ExceptionInfo):
        bot = self._create_bot()
        text_message = _get_default_message(e)
        for chat in self.admin_chats:
            bot.send_message(
                chat,
                text=text_message)
            for i, log in enumerate(e.logs or []):
                bot.send_document(chat, telebot.types.InputFile(io.StringIO(log), f'log{i+1}.txt'))

class MailErrorHandler(ErrorHandler):
    def __init__(self, addr_from, password, email, theme):
        self._addr_from = addr_from
        self._password = password
        self._email = email
        self._theme = theme

    def notify(self, e: ExceptionInfo):
        assert isinstance(e, ExceptionInfo)
        text_message = _get_default_message(e)
        msg = mail.Mail(self._addr_from, self._password, self._email, self._theme, text_message)
        for log in e.logs or []:
            msg.add_attachment(content=log)
        msg.send()


def _get_default_message(e: ExceptionInfo):
    message = ''
    if not e.was_expected:
        message += 'UNEXPECTED ERROR\n\n'
    message += f'Error {str(e.exception)}\n\n'
    message += ''.join(traceback.format_exception(e.exception))
    message += f'command_line: {e._command_line}\n'
    if e.version:
        message += f'version: {e.version}\n'
    message += f'thread: {e._thread_name}\n'
    return message

class ErrorHandlersService:
    def __init__(self, handlers: list[ErrorHandler]|None = None):
        self._handlers = handlers or []

    def add_handler(self, handler: ErrorHandler):
        self._handlers.append(handler)

    def notify(self, e: ExceptionInfo):
        e._command_line = shlex.join(sys.argv)
        e._thread_name = threading.current_thread().name
        for handler in self._handlers:
            try:
                handler.notify(e)
            except:
                traceback.print_exc()
    
    @contextlib.contextmanager
    def notify_about_exceptions(self, make_info: typing.Callable[[Exception], ExceptionInfo]):
        try:
            yield
        except Exception as e:
            self.notify(make_info(e))
        