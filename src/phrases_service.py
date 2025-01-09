import functools
import sqlalchemy
from sqlalchemy.orm import Session
from db import models
from sqlalchemy.orm import aliased

class PhrasesService:
    def add_phrases(self, session: Session, new_phrases: list[str]):
        old_phrases = set(phrase.text for phrase in self.get_phrases(session))
        phrases_to_insert = set()
        for phrase in new_phrases:
            if phrase not in old_phrases:
                phrases_to_insert.add(phrase)
        if phrases_to_insert:
            session.execute(
                sqlalchemy.insert(models.Phrase),
                [ { "text": text } for text in phrases_to_insert ]
            )
            session.commit()

    def get_phrases(self, session):
        return session.query(models.Phrase).all()

    def get_random_phrases(self, session):
        return session.execute(PhrasesService._get_random_phrases_request()).all()

    @functools.cache
    @staticmethod
    def _get_random_phrases_request():
        # somethind like
        # SELECT R.id as user_id, Result.phrase_id as phrase_id
        # FROM ((
        #   SELECT name, id 
        #   FROM EMPLOYEE 
        #   WHERE dept = 1
        # ) AS R
        # LEFT JOIN (
        #   SELECT U.id AS user_id, PHRASE.id AS phrase_id
        #   FROM (
        #     SELECT name, id 
        #     FROM EMPLOYEE 
        #     WHERE dept = 1
        #   ) U
        #   CROSS JOIN PHRASE
        #   EXCEPT 
        #   SELECT user_id, phrase_id 
        #   FROM USED_PHRASE
        # ) AS L
        # ON L.user_id = R.id
        # ) AS Result
        # order by random()
        # ) group by user_id;
        users_to_send_phrases = (sqlalchemy
            .select(models.User.id, models.User.chat_id)
            .where(models.User._send_phrases)).subquery()
        not_yet_sent_phrases = (sqlalchemy
            .select(models.User.id, models.Phrase.id)
            .join(models.Phrase, sqlalchemy.literal(True))
            .except_(sqlalchemy.select(models.UsedPhrases))).subquery()
        not_yet_sent_phrases_for_each_user = (sqlalchemy
            .select(users_to_send_phrases, aliased(models.Phrase, not_yet_sent_phrases).id)
            .join(
                not_yet_sent_phrases, 
                aliased(models.User, users_to_send_phrases).id == 
                aliased(models.User, not_yet_sent_phrases).id, 
                isouter=True)
            .order_by(sqlalchemy.func.random())).subquery()
        random_phrase_ids = (sqlalchemy
            .select(not_yet_sent_phrases_for_each_user)
            .group_by(aliased(models.User, not_yet_sent_phrases_for_each_user).id)).subquery()
        phrases = sqlalchemy.select(models.Phrase).subquery()
        random_phrases = (sqlalchemy
            .select(random_phrase_ids, aliased(models.Phrase, phrases).text)
            .join(
                phrases,
                aliased(models.Phrase, random_phrase_ids).id ==
                aliased(models.Phrase, phrases).id,
                isouter=True
            ))
        return random_phrases