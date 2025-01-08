import sqlalchemy
from sqlalchemy.orm import Session
from db import models

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