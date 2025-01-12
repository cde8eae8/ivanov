import re
import json
import queue
import threading

import sqlalchemy

import main
from db import models
import test.bot


class EventLoop:
    def __init__(self):
        self._mutex = threading.Lock()
        self._queue = queue.Queue()
        self._handlers = {}

    def run(self):
        while True:
            try:
                (key, ev) = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if key == "exit":
                break
            with self._mutex:
                handler = self._handlers[key]
            handler(ev)

    def set_handler(self, key, f):
        with self._mutex:
            self._handlers[key] = f

    def post_event(self, key, ev):
        self._queue.put((key, ev))

    def stop(self):
        self.post_event("exit", None)


class AppThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(target=self._start, name="App")
        self.app = main.App(*args, **kwargs)

    def _start(self):
        self.app.start()

    def stop(self):
        self.app.stop()
        self.join()


def test_send_phrases(tmp_path, testing_db):
    with testing_db.session() as session:
        admin = models.User(chat_id=1000, _is_admin=True, _send_phrases=False)
        user = models.User(chat_id=1001, _is_admin=False, _send_phrases=True)
        user2 = models.User(chat_id=1002, _is_admin=False, _send_phrases=True)
        users = [admin, user, user2]
        session.add_all(users)
        phrase = models.Phrase(text="phrase1")
        session.add(phrase)
        session.add(models.Phrase(text="phrase2"))
        session.commit()
        for u in users:
            session.refresh(u)
        session.refresh(phrase)
        session.execute(
            sqlalchemy.insert(models.UsedPhrases).values(
                {"user_id": user.id, "phrase_id": phrase.id}
            )
        )
        session.commit()
        for u in users:
            session.refresh(u)

    test_bot = test.bot.MockTelebot()

    factories = main.ServiceFactories()
    factories.init_db = lambda *args, **kwargs: testing_db.engine
    factories.create_bot = lambda *args, **kwargs: test_bot
    test_config = {
        "token": "<test token>",
        "time": {
            "start_time": "2025-01-10T22:30:00+03:00",
            "period_between_messages": "0:0:1",
        },
        "working_dir": str(tmp_path),
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(test_config))
    app_thread = AppThread(factories, config_path)
    app_thread.start()

    loop = EventLoop()
    NO_PHRASES = "We do not have phrases for you :("

    class Observer(test.bot.MockTelebotObserver):
        def on_message(self, sent_by_bot, message: test.bot.Message):
            assert sent_by_bot, message
            chat_id = user.chat_id
            if len(test_bot.chats[chat_id]) >= 1:
                assert test_bot.chats[chat_id][0] == "phrase2"
                if len(test_bot.chats[chat_id]) > 1:
                    assert set(test_bot.chats[chat_id][1:]) == {NO_PHRASES}

            chat_id = user2.chat_id
            if len(test_bot.chats[chat_id]) == 2:
                assert set(test_bot.chats[chat_id]) == {"phrase1", "phrase2"}
                if len(test_bot.chats[chat_id]) > 2:
                    assert set(test_bot.chats[chat_id][2:]) == {NO_PHRASES}

            if (
                len(test_bot.chats[user.chat_id]) >= 3
                and len(test_bot.chats[user2.chat_id]) >= 3
                and len(test_bot.chats[admin.chat_id]) >= 1
            ):
                loop.stop()

    test_bot.add_observer(Observer())
    loop.run()
    app_thread.stop()
    assert set(test_bot.chats[user.chat_id][1:]) == {NO_PHRASES}
    assert set(test_bot.chats[user2.chat_id][2:]) == {NO_PHRASES}
    assert len(set(test_bot.chats[admin.chat_id])) == 2
    assert re.match("Error no phrases for 1 users.*", test_bot.chats[admin.chat_id][0])
    assert re.match("Error no phrases for 2 users.*", test_bot.chats[admin.chat_id][1])
