"""Module de gestion de base de données."""
from pathlib import Path

import sqlalchemy
from sqlalchemy import (
    JSON,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Table,
    create_engine,
    insert,
    select,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

IntegrityError = sqlalchemy.exc.IntegrityError

Base = declarative_base()

decks_cartes = Table(
    "decks_cartes",
    Base.metadata,
    Column("deck_id", ForeignKey("decks.id"), primary_key=True),
    Column("carte_id", ForeignKey("cartes.id"), primary_key=True),
    Column("quantite", Integer, nullable=False, default=1),
)

decks_commanders = Table(
    "decks_commanders",
    Base.metadata,
    Column("deck_id", ForeignKey("decks.id"), primary_key=True),
    Column("carte_id", ForeignKey("cartes.id"), primary_key=True),
)


class Cartes(Base):
    """Tables cartes."""
    __tablename__ = "cartes"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    mana_value = Column(Integer, nullable=False)
    color_identity = Column(String, nullable=False)
    text = Column(String, nullable=False)
    first_print = Column(String, ForeignKey("sets.code"), nullable=False)
    legalities = Column(JSON, nullable=False)

    decks = relationship("Decks", secondary=decks_cartes, back_populates="cartes")
    as_commander = relationship(
        "Decks", secondary=decks_commanders, back_populates="commanders"
    )

    def __repr__(self):
        return f"<Carte `{self.name}`>"


class Decks(Base):
    """Tables decks."""
    __tablename__ = "decks"

    id = Column(Integer, primary_key=True)
    tournoi_id = Column(Integer, ForeignKey("tournois.id"), nullable=False)
    rank = Column(String, nullable=False)
    player = Column(String, nullable=False)

    tournoi = relationship("Tournois", back_populates="decks")
    cartes = relationship("Cartes", secondary=decks_cartes, back_populates="decks")
    commanders = relationship(
        "Cartes", secondary=decks_commanders, back_populates="as_commander"
    )


class Sets(Base):
    """Tables sets."""
    __tablename__ = "sets"

    code = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    release_date = Column(Date, nullable=False)


class Tournois(Base):
    """Tables tournois."""
    __tablename__ = "tournois"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    place = Column(String, nullable=False)
    players = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)

    decks = relationship("Decks", back_populates="tournoi")


def init_database():
    """Initialisation de la base de données."""
    db_path = Path(__file__).parent / "barrins-data.sqlite"
    engine = create_engine("sqlite:///" + str(db_path))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def stmt_set_deck_carte(deck: Decks, carte: Cartes, quantite: int):
    """Insertion de la quantité des cartes."""
    return insert(decks_cartes).values(
        deck_id=deck.id, carte_id=carte.id, quantite=int(quantite)
    )


def stmt_get_deck_carte(deck: Decks, carte: Cartes):
    """Récupération de la quantité des cartes."""
    return (
        select(decks_cartes)
        .where(decks_cartes.c.deck_id == deck.id)
        .where(decks_cartes.c.carte_id == carte.id)
    )
