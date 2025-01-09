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

    @staticmethod
    def get_random_phrases(session):
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
            .except_(session.query(models.UsedPhrases))).subquery()
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
        
        return session.execute(random_phrases).all()
        active_users = sqlalchemy.select(models.User.id, models.User.chat_id).where(models.User._send_phrases)
        all_phrases = (
            sqlalchemy.select(models.User.id, models.Phrase.id)
            .join(models.Phrase, sqlalchemy.literal(True))
            .except_(session.query(models.UsedPhrases)))
        active_users_subq = active_users.subquery()
        all_phrases_subq = all_phrases.subquery()
        user_alias = aliased(models.User, all_phrases_subq, name="user")
        phrase_alias = aliased(models.Phrase, all_phrases_subq, name="phrase")
        user_alias2 = aliased(models.User, active_users_subq, name="user2")
        not_yet_sent_phrases_for_each_user = (sqlalchemy
            .select(active_users_subq, phrase_alias.id)
            .join(
                all_phrases_subq, 
                user_alias2.id == user_alias.id, isouter=True)
            .order_by(sqlalchemy.func.random()))
        get_phrases_subq = not_yet_sent_phrases_for_each_user.subquery()
        user_alias3 = aliased(models.User, get_phrases_subq)

        random_phrase_ids = sqlalchemy.select(get_phrases_subq).group_by(user_alias3.id)
        grouped_phrases_subq = random_phrase_ids.subquery()
        phrases_alias2 = aliased(models.Phrase, grouped_phrases_subq, name="phrase2")
        texts = sqlalchemy.select(grouped_phrases_subq, models.Phrase).join(
            models.Phrase,
            phrases_alias2.id == models.Phrase.id)

        #return grouped_phrases

        return session.execute(texts).all()
            # for user_id, chat_id, phrase_id in session.execute(self._get_random_phrases(session)).all():
            #     # TODO: Move it to a join in _get_random_phrases
            #     message = 'We do not have phrases for you :('
            #     if phrase_id is not None:
            #         phrase = session.query(models.Phrase).where(models.Phrase.id == phrase_id).one()
            #         message = phrase.text
