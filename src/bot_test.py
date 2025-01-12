import bot as B
import pytest
import collections
import dataclasses
from db import models
import user_service as US
import phrases_service as PS
from test.test_helpers import testing_db
import test.bot

def assert_compare_users(user, chat_id, is_admin, send_phrases):
    assert user.chat_id == chat_id 
    assert user._is_admin == is_admin
    assert user._send_phrases == send_phrases

@dataclasses.dataclass
class BotEnvironment:
    bot: test.bot.MockTelebot
    user_service: US.UserService
    phrases_service: US.UserService

@pytest.fixture
def bot_environment(testing_db):
    bot_impl = test.bot.MockTelebot()
    user_service = US.UserService()
    phrases_service = PS.PhrasesService()
    B.Bot(bot_impl, testing_db.session, user_service, phrases_service)
    yield BotEnvironment(bot_impl, user_service, phrases_service)


def test_bot_commands(testing_db, bot_environment):
    expected_chats = collections.defaultdict(list)
    session = testing_db.session()
    user_service = bot_environment.user_service
    bot = bot_environment.bot

    assert user_service.get_user(session, 1) is None
    user1 = 100
    user2 = 200

    bot.user_message(user1, 'start')
    expected_chats[user1].append("Hello! You're subscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, True)
    assert session.query(models.User).count() == 1

    bot.user_message(user1, 'stop')
    expected_chats[user1].append("You're unsubscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, False)
    assert session.query(models.User).count() == 1

    bot.user_message(user1, 'help')
    expected_chats[user1].append("Help")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, False)
    assert session.query(models.User).count() == 1

    bot.user_message(user1, 'start')
    expected_chats[user1].append("Hello! You're subscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, True)
    assert session.query(models.User).count() == 1

    bot.user_message(user2, 'start')
    expected_chats[user2].append("Hello! You're subscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, True)
    assert_compare_users(user_service.get_user(session, user2), user2, False, True)
    assert session.query(models.User).count() == 2

    bot.user_message(user1, 'edit')
    expected_chats[user1].append("The action is forbidden")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, True)
    assert_compare_users(user_service.get_user(session, user2), user2, False, True)
    assert session.query(models.User).count() == 2

    bot.user_message(user2, 'stop')
    expected_chats[user2].append("You're unsubscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, True)
    assert_compare_users(user_service.get_user(session, user2), user2, False, False)
    assert session.query(models.User).count() == 2

    bot.user_message(user1, 'start')
    expected_chats[user1].append("Hello! You're subscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, user1), user1, False, True)
    assert_compare_users(user_service.get_user(session, user2), user2, False, False)
    assert session.query(models.User).count() == 2

def test_bot_admin_commands(testing_db, bot_environment):
    user_service = bot_environment.user_service
    bot = bot_environment.bot
    expected_chats = collections.defaultdict(list)

    admin = 1000
    session = testing_db.session()
    session.add(models.User(chat_id=admin, _is_admin=True, _send_phrases=False))
    session.commit()

    assert_compare_users(user_service.get_user(session, admin), admin, True, False)
    assert session.query(models.User).count() == 1

    bot.user_message(admin, 'start')
    expected_chats[admin].append("Hello! You're subscribed now.\nAnd you're an admin")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, admin), admin, True, True)
    assert session.query(models.User).count() == 1

    bot.user_message(admin, 'stop')
    expected_chats[admin].append("You're unsubscribed now")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, admin), admin, True, False)
    assert session.query(models.User).count() == 1

    bot.user_message(admin, 'edit')
    expected_chats[admin].append("Reply to this message with a table with new phrases")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, admin), admin, True, False)
    assert session.query(models.User).count() == 1

def test_bot_add_phrases(testing_db, bot_environment):
    user_service = bot_environment.user_service
    bot = bot_environment.bot
    expected_chats = collections.defaultdict(list)

    bot.add_file('phrases1.csv', '''Цитаты
phrase1
phrase2
phrase3
'''.encode('utf-8'))
    bot.add_file('phrases2.csv', '''Цитаты
phrase5
phrase1
phrase3
phrase4
'''.encode('utf-8'))

    admin = 1000
    session = testing_db.session()
    session.add(models.User(chat_id=admin, _is_admin=True, _send_phrases=False))
    session.commit()

    bot.user_message(admin, 'edit')
    expected_chats[admin].append("Reply to this message with a table with new phrases")
    assert bot.chats == expected_chats
    assert_compare_users(user_service.get_user(session, admin), admin, True, False)
    assert session.query(models.User).count() == 1

    assert bot.chats == expected_chats

    bot.user_message(admin, reply_to=bot.full_chats[admin][0], file=test.bot.File('phrases1.csv'))

    phrases = set(p.text for p in session.query(models.Phrase).all())
    assert phrases == {
        'phrase1', 'phrase2', 'phrase3'
    }

    bot.user_message(admin, 'edit')
    bot.user_message(admin, reply_to=bot.full_chats[admin][1], file=test.bot.File('phrases1.csv'))

    phrases = set(p.text for p in session.query(models.Phrase).all())
    assert phrases == {
        'phrase1', 'phrase2', 'phrase3'
    }

    bot.user_message(admin, 'edit')
    bot.user_message(admin, reply_to=bot.full_chats[admin][2], file=test.bot.File('phrases2.csv'))

    phrases = set(p.text for p in session.query(models.Phrase).all())
    assert phrases == {
        'phrase1', 'phrase2', 'phrase3', 'phrase4', 'phrase5'
    }