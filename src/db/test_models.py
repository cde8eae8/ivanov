import uuid

import pytest
import sqlalchemy
import sqlalchemy.exc

from . import models


def test_user_table(testing_db):
    with testing_db.session() as session:
        id = uuid.uuid4()
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*UNIQUE.*"):
            session.add(
                models.User(id=id, chat_id=1),
            )
            session.commit()
            session.add(models.User(id=id, chat_id=2))
            session.commit()

    with testing_db.session() as session:
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*UNIQUE.*"):
            session.add_all([models.User(chat_id=3), models.User(chat_id=3)])
            session.commit()

    with testing_db.session() as session:
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*NOT NULL.*"):
            session.add(models.User(chat_id=None))
            session.commit()


def test_phrases_table(testing_db):
    with testing_db.session() as session:
        id = uuid.uuid4()
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*UNIQUE.*"):
            session.add(models.Phrase(id=id, text="1"))
            session.commit()
            session.add(models.Phrase(id=id, text="2"))
            session.commit()

    with testing_db.session() as session:
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*UNIQUE.*"):
            session.add_all([models.Phrase(text="1"), models.Phrase(text="1")])
            session.commit()

    with testing_db.session() as session:
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*NOT NULL.*"):
            session.add(models.Phrase(text=None))
            session.commit()


def test_used_phrases_table(testing_db):
    id = uuid.uuid4()
    id2 = uuid.uuid4()
    with testing_db.session() as session:
        # check foreign key constraint
        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*FOREIGN KEY.*"):
            session.execute(
                sqlalchemy.insert(models.UsedPhrases).values(
                    [
                        {"user_id": id, "phrase_id": id2},
                    ]
                )
            )
            session.commit()

        user = models.User(chat_id=1)
        phrase = models.Phrase(text="text")
        session.add(user)
        session.add(phrase)
        session.commit()

        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*NOT NULL.*"):
            session.execute(
                sqlalchemy.insert(models.UsedPhrases).values(
                    [
                        {"user_id": user.id, "phrase_id": None},
                    ]
                )
            )
            session.commit()

        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*NOT NULL.*"):
            session.execute(
                sqlalchemy.insert(models.UsedPhrases).values(
                    [
                        {"user_id": None, "phrase_id": phrase.id},
                    ]
                )
            )
            session.commit()

        with pytest.raises(sqlalchemy.exc.IntegrityError, match=".*UNIQUE.*"):
            session.execute(
                sqlalchemy.insert(models.UsedPhrases).values(
                    [
                        {"user_id": user.id, "phrase_id": phrase.id},
                    ]
                )
            )
            session.commit()
            session.execute(
                sqlalchemy.insert(models.UsedPhrases).values(
                    [
                        {"user_id": user.id, "phrase_id": phrase.id},
                    ]
                )
            )
            session.commit()
