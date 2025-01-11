import collections
import contextlib
import dataclasses
import datetime as dt
import enum
import functools
import json
import logging
import os
import pathlib
import sys
import traceback
import typing
import telebot
import threading
import queue

import sqlalchemy
import sqlalchemy.exc
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session

import bot
import error_handler
import timer
from db import models
import user_service as US
import phrases_service as PS

logger = logging.getLogger(__name__)

DEFAULT_WORKING_DIR = pathlib.Path.home() / '.ivanov'

def expected_exception(exception: Exception):
    logging.getLoggerClass().root.handlers[0].baseFilename
    logs = []
    for handler in logger.root.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                with open(handler.baseFilename, 'rb') as f:
                    f.seek(0, os.SEEK_END)
                    file_size = f.tell()
                    read_size = min(1024*512, file_size)
                    f.seek(-read_size, os.SEEK_END)
                    logs.append(f.read(read_size).decode('utf-8', 'replace'))
            except Exception as e:
                logs.append(f'failed to read log file {''.join(traceback.format_exception(e))}')
    return error_handler.ExceptionInfo(
        exception, 
        True,
        logs=logs,
        version=AppInfo.version)

def unexpected_exception(e: Exception):
    info = expected_exception(e)
    info.was_expected = False
    return info

class AppInfo:
    version: str = (pathlib.Path(__file__).parent.parent / 'VERSION').read_text().strip()

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
    error_mail: typing.Optional["Config.ErrorMail"] = None

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
        if 'error_mail' in self._config:
            self.error_mail = Config.ErrorMail(**self._config['error_mail'])

class BotThread:
    def __init__(self, bot: bot.Bot):
        self._bot = bot
        self._bot_thread = None

    def start(self):
        self._bot_thread = threading.Thread(target=self._do_start_bot, name="BotThread")
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
        self._setup_logger()
        self._error_handlers = error_handler.ErrorHandlersService([])
        self._error_handlers.add_handler(error_handler.LoggerNotifier())
        if self._config.error_mail:
            logging.info("Information about errors will be sent to %s", self._config.error_mail.to_addr)
            self._error_handlers.add_handler(
                error_handler.MailErrorHandler(
                    self._config.error_mail.from_addr, 
                    self._config.error_mail.password, 
                    self._config.error_mail.to_addr, 
                    "Ivanov bot error"),
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
            exception_handler=BotExceptionHandler(self._error_handlers)), self._create_session, self._user_service, self._phrases_service)
        self._bot_thread = BotThread(self._bot)
        self._wakeup_controller = timer.PeriodicWakeupController(self._config.start_time, self._config.period_between_messages)
        self._timer = timer.TimerThread(
            self._wakeup_controller.next_wakeup,
            lambda: self._events.put(TimerEvent()))

    # TODO maybe save for every user x phrase day when it was sended? 
    # it allows to distinguish users which already got phrase today 
    # before bot failure
    def start(self):
        self._bot_thread.start()
        self._timer.start()
        try:
            while True:
                with (
                    contextlib.suppress(Exception),
                    self._error_handlers.notify_about_exceptions(unexpected_exception)):
                    try:
                        event = self._events.get(timeout=5)
                    except queue.Empty:
                        continue
                    if isinstance(event, TimerEvent):
                        self._send_phrases()
        finally:
            logger.info('Exiting main loop...')
            if e := sys.exception():
                logger.exception(e)
            while True:
                try:
                    threads = (self._bot_thread, self._timer)
                    for thread in threads:
                        thread.stop()
                    for thread in threads:
                        t = thread.python_thread()
                        logger.info(f'Waiting for {t.name} thread...')
                        if t.is_alive():
                            t.join()
                    break
                except BaseException as e:
                    logger.error('Exception %s ignored, waiting for thread exit', e)

    def _send_phrases(self):
        logger.info(f'Woke up at {dt.datetime.now(dt.UTC)}, sending phrases')
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
            session.commit()

        logger.info('Next wakeup at %s', self._wakeup_controller.next_wakeup(dt.datetime.now(dt.UTC)))

    def _setup_logger(self):
        log_path = self._config.working_dir / 'logs' / f'{dt.datetime.now().timestamp()}.log'
        log_path.parent.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s][%(threadName)s] %(filename)s:%(lineno)d: %(message)s",
            handlers=[
                logging.FileHandler(log_path, "a", "utf-8"),
                logging.StreamHandler(),
            ],
        )
        logger = logging.getLogger(__name__)
        logger.info("logging to %s", log_path)



if __name__ == "__main__":
    config = os.environ.get('IVANOV_CONFIG', DEFAULT_WORKING_DIR / 'config.json')
    app = App(config)
    app.start()