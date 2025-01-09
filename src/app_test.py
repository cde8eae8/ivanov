from db import models
import collections
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import aliased
import main
from phrases_service import PhrasesService

# random_phrases = main.App._get_random_phrases
# def random_phrases(session):
#     active_users = sqlalchemy.select(models.User.id).where(models.User._send_phrases)
#     all_phrases = (
#         sqlalchemy.select(models.User.id, models.Phrase.id)
#         .join(models.Phrase, sqlalchemy.literal(True))
#         .except_(session.query(models.UsedPhrases)))
#     active_users_subq = active_users.subquery()
#     all_phrases_subq = all_phrases.subquery()
#     user_alias = aliased(models.User, all_phrases_subq, name="user")
#     phrase_alias = aliased(models.Phrase, all_phrases_subq, name="phrase")
#     user_alias2 = aliased(models.User, active_users_subq, name="user2")
#     get_phrases = sqlalchemy.select(active_users_subq, phrase_alias.id).join(
#         all_phrases_subq, 
#         user_alias2.id == user_alias.id, isouter=True).order_by(sqlalchemy.func.random())
#     get_phrases_subq = get_phrases.subquery()
#     user_alias3 = aliased(models.User, get_phrases_subq)

#     grouped_phrases = sqlalchemy.select(get_phrases_subq).group_by(user_alias3.id)

#     return grouped_phrases
    

def test_select_phrases():
    engine = models.init_db_for_testing(echo=False)
    session = scoped_session(sessionmaker(engine))()
    session.add(models.User(chat_id=0, _send_phrases=False))
    session.add(models.User(chat_id=1, _send_phrases=True))
    session.add(models.User(chat_id=2, _send_phrases=True))
    session.add(models.User(chat_id=3, _send_phrases=True))

    for i in range(4):
        session.add(models.Phrase(text='p' + str(i)))
    session.commit()
    users = {user.chat_id: user for user in session.query(models.User).all()}
    phrases = {int(p.text[1:]): p for p in session.query(models.Phrase).all()}
    used_phrases = {
        0: [],
        1: list(range(4)),
        2: [3],
        3: [2],
    }

    values = []
    for user, used_phrase_ids in used_phrases.items():
        for used_phrase_id in used_phrase_ids:
            values.append((users[user].id, phrases[used_phrase_id].id))
    session.execute(sqlalchemy.insert(models.UsedPhrases).values(values))
    session.commit()

    active_users = sqlalchemy.select(models.User.id).where(models.User._send_phrases)
    all_phrases = (
        sqlalchemy.select(models.User.id, models.Phrase.id)#.with_entities(models.User.id, models.Phrase.id)
        .join(models.Phrase, sqlalchemy.literal(True))
        .except_(session.query(models.UsedPhrases)))
    active_users_subq = active_users.subquery()
    all_phrases_subq = all_phrases.subquery()
    user_alias = aliased(models.User, all_phrases_subq, name="user")
    phrase_alias = aliased(models.Phrase, all_phrases_subq, name="phrase")
    user_alias2 = aliased(models.User, active_users_subq, name="user2")
    get_phrases = sqlalchemy.select(active_users_subq, phrase_alias.id).join(
        all_phrases_subq, 
        user_alias2.id == user_alias.id, isouter=True).order_by(sqlalchemy.func.random())

    users = {user.id: user for user in session.query(models.User).all()}
    phrases = {p.id: p for p in session.query(models.Phrase).all()}
    for user_id, phrase_id in session.execute(get_phrases).all():
        user = users[user_id]
        phrase = None
        if phrase_id:
            phrase = phrases[phrase_id].text
    
    get_phrases_subq = get_phrases.subquery()
    user_alias3 = aliased(models.User, get_phrases_subq)

    # grouped_phrases = sqlalchemy.select(get_phrases_subq).group_by(user_alias3.id)
    # grouped_phrases = PhrasesService().get_random_phrases(session)

    sets = collections.defaultdict(lambda: 0)
    iters = 10000
    for i in range(iters):
        pairs = []
        # for user_id, chat_id, phrase_id in session.execute(grouped_phrases).all():
        for user_id, chat_id, phrase_id, phrase in PhrasesService().get_random_phrases(session):
            user = users[user_id]
            phrase = None
            if phrase_id:
                phrase = phrases[phrase_id].text
            pairs.append((user.chat_id, phrase))
        pairs.sort()
        sets[(pairs[1][1], pairs[2][1])] += 1
    values = [(v - iters // 9) / (iters // 9) for v in sets.values()]
    for value in values:
        assert value < 0.05
    