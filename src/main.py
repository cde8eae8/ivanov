import collections
import contextlib
import dataclasses
import enum
import os
import telebot
import queue
import datetime as dt
import threading
import json
import pathlib
import sqlalchemy
import sqlalchemy.exc

import bot
import error_handler
import timer
from db import models
import user_service as US
import phrases_service as PS
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session

DEFAULT_WORKING_DIR = pathlib.Path.home() / '.ivanov'

def expected_exception(e: Exception):
    return error_handler.ExceptionInfo(e, True)

def unexpected_exception(e: Exception):
    info = expected_exception(e)
    info.was_expected = False
    return info

class Config:
    @dataclasses.dataclass
    class ErrorMail:
        from_addr: str
        password: str
        to_addr: str
        
    bot_token: str
    working_dir: pathlib.Path
    start_time: dt.datetime
    period_between_messages: dt.timedelta
    error_mail: "Config.ErrorMail"

    def __init__(self, config_path: pathlib.Path) -> None:
        if not config_path.is_file():
            raise RuntimeError(f'Config {config_path} is not a file')

        with open(config_path, 'r') as f:
            self._config = json.load(f)

        self.bot_token = self._config['token']
        self.working_dir = pathlib.Path(self._config.get('working_dir', DEFAULT_WORKING_DIR))
        self.start_time = dt.datetime.fromisoformat(self._config['time']['start_time'])
        period_between_messages = dt.datetime.strptime(self._config['time']['period_between_messages'],"%H:%M:%S")
        self.period_between_messages = dt.timedelta(
            hours=period_between_messages.hour, 
            minutes=period_between_messages.minute, 
            seconds=period_between_messages.second)
        self.error_mail = Config.ErrorMail(**self._config['error_mail'])

class BotThread:
    def __init__(self, bot: bot.Bot):
        self._bot = bot
        self._bot_thread = None

    def start(self):
        self._bot_thread = threading.Thread(target=self._do_start_bot)
        self._bot_thread.start()

    def stop(self):
        self._bot.stop_bot()

    def python_thread(self):
        return self._bot_thread

    def _do_start_bot(self):
        self._bot.start_bot()

class TimerEvent:
    pass

class BotExceptionHandler(telebot.ExceptionHandler):
    def __init__(self, error_handler: error_handler.ErrorHandlersService):
        self._error_handler = error_handler

    def handle(self, e: Exception):
        self._error_handler.notify(
            unexpected_exception(e)
        )
        

class App:
    def __init__(self, config_path):
        self._config = Config(config_path)
        self._error_handlers = error_handler.ErrorHandlersService(
            [
                error_handler.LoggerNotifier(),
                error_handler.MailErrorHandler(
                    self._config.error_mail.from_addr, 
                    self._config.error_mail.password, 
                    self._config.error_mail.to_addr, 
                    "Ivanov bot error"),
            ]
        )
        self._config.working_dir.mkdir(exist_ok=True)
        self._engine = models.init_db(f"sqlite:///{self._config.working_dir / "iv.db"}")
        self._create_session = scoped_session(sessionmaker(self._engine))
        self._user_service = US.UserService()
        self._error_handlers.add_handler(
            error_handler.TelegramErrorHandler(
                self._config.bot_token,
                self._user_service.get_admin_chats(self._create_session())
            )
        )
        self._phrases_service = PS.PhrasesService()
        self._events = queue.Queue()
        self._bot = bot.Bot(telebot.TeleBot(
            self._config.bot_token,
            exception_handler=BotExceptionHandler()), self._create_session, self._user_service, self._phrases_service)
        self._bot_thread = BotThread(self._bot)
        self._timer = timer.TimerThread(
            timer.PeriodicWakeupController(self._config.start_time, self._config.period_between_messages).next_wakeup,
            lambda: self._events.put(TimerEvent()))

    # TODO maybe save for every user x phrase day when it was sended? 
    # it allows to distinguish users which already got phrase today 
    # before bot failure
    def start(self):
        self._bot_thread.start()
        self._timer.start()
        try:
            with (
                contextlib.suppress(), 
                self._error_handlers.notify_about_exceptions(unexpected_exception)):
                while True:
                    try:
                        event = self._events.get(timeout=5)
                        if isinstance(event, TimerEvent):
                            self._send_phrases()
                    except queue.Empty:
                        pass
        finally:
            while True:
                try:
                    threads = (self._bot_thread, self._timer)
                    for thread in threads:
                        thread.stop()
                    for thread in threads:
                        t = thread.python_thread()
                        print(f'waiting for {t.name} thread...')
                        if t.is_alive():
                            t.join()
                    break
                except BaseException as e:
                    print(f'{e} ignored, waiting for thread exit')

    def _send_phrases(self):
        with self._create_session() as session:
            bot = telebot.TeleBot(self._config.bot_token)
            class SendResult(enum.Enum):
                SUCCESS = 1
                NO_PHRASES = 2
                MESSAGE_ERROR = 3
            results = collections.defaultdict(list)
            phrases = list(self._phrases_service.get_random_phrases(session))
            for user_id, chat_id, phrase_id, phrase in phrases:
                message = phrase or 'We do not have phrases for you :('
                try:
                    bot.send_message(
                        chat_id,
                        text=message
                    )
                except Exception as e:
                    self._error_handlers.notify(expected_exception(e))
                    results[SendResult.MESSAGE_ERROR].append(e)
                    continue
                if phrase is None:
                    results[SendResult.NO_PHRASES].append(user_id)
                    continue
                results[SendResult.SUCCESS].append((user_id, phrase_id))
            try:
                if results[SendResult.SUCCESS]:
                    session.execute(sqlalchemy
                        .insert(models.UsedPhrases)
                        .values(results[SendResult.SUCCESS]))
            except sqlalchemy.exc.SQLAlchemyError as e:
                self._error_handlers.notify(expected_exception(e))
            if results[SendResult.MESSAGE_ERROR]:
                messages = results[SendResult.MESSAGE_ERROR]
                self._error_handlers.notify(expected_exception(RuntimeError(
                    f'failed to send some messages {len(messages)}, reasons: {set(str(m) for m in messages)}'
                )))
            if results[SendResult.NO_PHRASES]:
                messages = results[SendResult.NO_PHRASES]
                self._error_handlers.notify(expected_exception(RuntimeError(
                    f'no phrases for {len(messages)} users'
                )))
            # TODO: collect results and update database one time at the end
            session.commit()


if __name__ == "__main__":
    config = os.environ.get('IVANOV_CONFIG', DEFAULT_WORKING_DIR / 'config.json')
    app = App(config)
    app.start()