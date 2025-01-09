import dataclasses
from db import models
import collections
import sqlalchemy
from phrases_service import PhrasesService
from test_helpers import testing_db

@dataclasses.dataclass
class DatabaseState:
    users: dict[models.ChatId, list[str]]
    additional_phrases: list[str]

def init_database(session, state: DatabaseState):
    phrases = set(state.additional_phrases)
    for chat_id, send_phrases, user_phrases in state.users:
        session.add(models.User(chat_id=chat_id, _send_phrases=send_phrases))
        phrases.update(user_phrases)
    for phrase in phrases:
        session.add(models.Phrase(text=phrase))
    session.commit()

    users = {user.chat_id: user for user in session.query(models.User).all()}
    phrases = {p.text: p for p in session.query(models.Phrase).all()}
    values = []
    for chat_id, _, user_phrases in state.users:
        for used_phrase in user_phrases:
            values.append((users[chat_id].id, phrases[used_phrase].id))
    session.execute(sqlalchemy.insert(models.UsedPhrases).values(values))
    session.commit()

def test_select_random_phrase_for_each_user(testing_db):
    session = testing_db.session()

    init_database(session,
        DatabaseState(
            users=[
                (100, True, ['p1', 'p2', 'p3']),
                (101, False, ['p1', 'p2', 'p3']),
                (200, True, []),
                (201, True, ['p1', 'p2', 'p3', 'p4']),
            ],
            additional_phrases=[]
        ))

    for i in range(10):
        phrases = list(PhrasesService().get_random_phrases(session))
        user_to_phrase = {p[1]: p[3] for p in phrases}
        assert len(user_to_phrase) == 3
        assert user_to_phrase[100] == 'p4'
        assert 101 not in user_to_phrase
        assert user_to_phrase[200] in ['p1', 'p2', 'p3', 'p4']
        assert user_to_phrase[201] == None

def test_select_random_phrase_uniform_distribution(testing_db):
    session = testing_db.session()

    init_database(session,
        DatabaseState(
            users=[
                (-1, False, ['p1', 'p2', 'p3']),
                (100, True, ['p1', 'p2']),
                (200, True, ['p3', 'p4']),
            ],
            additional_phrases=['p5']
        ))

    freq = collections.defaultdict(lambda: 0)
    n_iters = 1000
    for _ in range(n_iters):
        phrases = list(PhrasesService().get_random_phrases(session))
        user_to_phrase = {p[1]: p[3] for p in phrases}
        assert len(user_to_phrase) == 2
        assert -1 not in user_to_phrase
        assert user_to_phrase[100] in {'p3', 'p4', 'p5'}
        assert user_to_phrase[200] in {'p1', 'p2', 'p5'}
        for user_phrase in user_to_phrase.items():
            freq[user_phrase] += 1
        
    freq = {k: v/n_iters for k, v in freq.items()}
    for phrase_freq in freq.values():
        assert abs(phrase_freq - 1/3) < 0.05