import os
import traceback
import typing
import telebot
import queue
import time
import datetime as dt
import threading
import json
import pathlib
import sqlalchemy

import bot
from db import models
import user_service as US
import phrases_service as PS
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session

class Config:
    bot_token: str
    send_phrases_time: dt.time

    def __init__(self, config_path: pathlib.Path) -> None:
        if not config_path.is_file():
            raise RuntimeError(f'Config {config_path} is not a file')

        with open(config_path, 'r') as f:
            self._config = json.load(f)

        self.bot_token = self._config['token']
        self.send_phrases_time = dt.time.fromisoformat(self._config['send_phrases_time'])

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

class TimerThread:
    def __init__(self, time: dt.time, callback: typing.Callable[[], None]):
        assert time.tzinfo
        self._wakeup_time = time
        self._callback = callback
        self._thread = None
        self._exited = threading.Event()
        self._exited.clear()

    def start(self):
        assert not self._exited.is_set()
        self._thread = threading.Thread(target=self._do_start)
        self._thread.start()

    def stop(self):
        self._exited.set()
        self._thread.join()

    def _do_start(self):
        now = dt.datetime.now(tz=dt.timezone.utc)
        next_wakeup = now
        next_wakeup = dt.datetime.combine(now, self._wakeup_time, self._wakeup_time.tzinfo)
        if next_wakeup.time() < now.time():
            next_wakeup += dt.timedelta(days=1)
        self._next_wakeup = next_wakeup
        while not self._exited.is_set():
            self._sleep(dt.timedelta(seconds=5))

    def _sleep(self, max_sleep: dt.timedelta):
        now = dt.datetime.now(tz=dt.timezone.utc)
        if self._next_wakeup <= now or True:
            self._callback()
            self._next_wakeup += dt.timedelta(days=1)
        assert self._next_wakeup > now
        sleep_time = min(self._next_wakeup - now, max_sleep)
        time.sleep(sleep_time.total_seconds())

class TimerEvent:
    pass

class App:
    def __init__(self, config_path):
        self._engine = models.init_db()
        self._create_session = scoped_session(sessionmaker(self._engine))
        self._user_service = US.UserService()
        self._phrases_service = PS.PhrasesService()
        self._phrases_service.add_phrases(self._create_session(), [
            'p1',
            'p2',
            'p3',
            'p4',
        ])
        self._events = queue.Queue()
        self._config = Config(config_path)
        self._bot = bot.Bot(telebot.TeleBot(self._config.bot_token), self._create_session, self._user_service, self._phrases_service)
        self._bot_thread = BotThread(self._bot)
        self._timer = TimerThread(self._config.send_phrases_time, lambda: self._events.put(TimerEvent()))

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
    config = os.environ.get('IVANOV_CONFIG', pathlib.Path.home() / '.ivanov' / 'config.json')
    app = App(config)
    app.start()