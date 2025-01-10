import os
import telebot
import queue
import datetime as dt
import threading
import json
import pathlib
import sqlalchemy

import bot
import timer
from db import models
import user_service as US
import phrases_service as PS
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session

DEFAULT_WORKING_DIR = pathlib.Path.home() / '.ivanov'

class Config:
    bot_token: str
    working_dir: pathlib.Path
    start_time: dt.datetime
    period_between_messages: dt.timedelta

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

class BotThread:
    def __init__(self, bot: bot.Bot):
        self._bot = bot
        self._bot_thread = None

    def start(self):
        self._bot_thread = threading.Thread(target=self._do_start_bot)
        self._bot_thread.start()

    def stop(self):
        self._bot.stop_bot()
        self._bot_thread.join()

    def _do_start_bot(self):
        self._bot.start_bot()

class TimerEvent:
    pass

class App:
    def __init__(self, config_path):
        self._config = Config(config_path)
        self._config.working_dir.mkdir(exist_ok=True)
        self._engine = models.init_db(f"sqlite:///{self._config.working_dir / "iv.db"}")
        self._create_session = scoped_session(sessionmaker(self._engine))
        self._user_service = US.UserService()
        self._phrases_service = PS.PhrasesService()
        self._events = queue.Queue()
        self._bot = bot.Bot(telebot.TeleBot(self._config.bot_token), self._create_session, self._user_service, self._phrases_service)
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
            while True:
                try:
                    event = self._events.get(timeout=5)
                    if isinstance(event, TimerEvent):
                        self._send_phrases()
                except queue.Empty:
                    pass
        finally:
            threads = (self._bot_thread, self._timer)
            for thread in threads:
                print('waiting for thread...')
                thread.stop()
            print('exit')

    def _send_phrases(self):
        with self._create_session() as session:
            bot = telebot.TeleBot(self._config.bot_token)
            for user_id, chat_id, phrase_id, phrase in \
                    self._phrases_service.get_random_phrases(session):
                message = phrase or 'We do not have phrases for you :('
                bot.send_message(
                    chat_id,
                    text=message
                )
                session.execute(sqlalchemy
                    .insert(models.UsedPhrases)
                    .values(user_id=user_id, phrase_id=phrase_id))
                # TODO: collect results and update database one time at the end
                session.commit()


if __name__ == "__main__":
    config = os.environ.get('IVANOV_CONFIG', DEFAULT_WORKING_DIR / 'config.json')
    app = App(config)
    app.start()