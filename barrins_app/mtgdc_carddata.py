"""Module de gestion des données de cartes et sets."""

import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
import sqlalchemy
from mtgdc_database import Cartes, IntegrityError, Sets, init_database
from unidecode import unidecode


class MTGJSON:
    """Gestion de base de la récupération des fichiers de MTGJSON."""

    target = ""
    path = Path()
    data = {}

    @property
    def is_up_to_date(self):
        if not self.path.is_file():
            return False
        return not self._file_older_than(7)

    def _file_older_than(self, age: int):
        file_timestamp = self.path.stat().st_mtime
        file_timestamp = datetime.fromtimestamp(file_timestamp)
        current_time = datetime.now()
        return (current_time - file_timestamp) > timedelta(days=age)

    def _download(self):
        response = requests.get(self.target, stream=True)
        with open(self.path, "wb") as file:
            file.write(response.content)


class AllSets(MTGJSON):
    """Récupération et initialisation des données MTGJSON."""

    def __init__(self) -> None:
        self.target = "https://mtgjson.com/api/v5/SetList.json.gz"
        self.path = Path(__file__).parent / "AllSets.json.gz"

        if not self.is_up_to_date:
            self._download()
            self.data = json.load(gzip.open(self.path))["data"]
            self._upgrade()

    def _upgrade(self):
        """Mise à jour de la base."""
        session = init_database()

        for set_data in self.data:
            # Vérifier si le set existe déjà dans la base de données
            existing_set = session.query(Sets).filter_by(code=set_data["code"]).first()
            if existing_set:
                continue

            # Ajouter le nouveau set à la base de données
            new_set = Sets(
                code=set_data["code"],
                name=set_data["name"],
                release_date=datetime.strptime(set_data["releaseDate"], "%Y-%m-%d"),
            )
            session.add(new_set)
            try:
                session.commit()
            except sqlalchemy.exc.IntegrityError:
                session.rollback()
                print(
                    f"Erreur : Impossible d'ajouter {set_data['code']} à la base de données."
                )


class AllCards(MTGJSON):
    """Récupération et initialisation des données MTGJSON."""

    def __init__(self) -> None:
        self.target = "https://mtgjson.com/api/v5/AtomicCards.json.gz"
        self.path = Path(__file__).parent / "AtomicCards.json.gz"

        if not self.is_up_to_date:
            self._download()
            self.data = json.load(gzip.open(self.path))["data"]
            self._upgrade()

    def _upgrade(self):
        """Mise à jour de la base."""
        session = init_database()

        for card_name in self.data.keys():
            card_data = self.data[card_name][0]

            # Vérifier si ce n'est pas une carte Archenemy
            if card_data["name"].startswith("A-"):
                continue

            # Vérifier si la carte n'est ni un plan ni une manigance
            if "Scheme" in card_data["type"] or "Plane —" in card_data["type"]:
                continue

            # Si la carte n'a pas de légalité
            if len(card_data["legalities"].keys()) == 0:
                continue

            # Vérifier si la carte existe déjà dans la base de données
            existing_card = (
                session.query(Cartes)
                .filter_by(id=card_data["identifiers"]["scryfallOracleId"])
                .first()
            )
            if existing_card:
                continue

            # Ajouter la nouvelle carte à la base de données
            try:
                card_text = card_data["text"] if "text" in card_data.keys() else ""
                first_print = (
                    card_data["firstPrinting"]
                    if "firstPrinting" in card_data.keys()
                    else oldest_set(card_data["printings"])
                )

                new_card = Cartes(
                    id=card_data["identifiers"]["scryfallOracleId"],
                    name=card_data["name"],
                    type=card_data["type"],
                    mana_value=int(card_data["manaValue"]),
                    color_identity="".join(card_data["colorIdentity"]),
                    text=card_text,
                    first_print=first_print,
                    legalities=card_data["legalities"],
                )
                session.add(new_card)
            except KeyError:
                print(card_data)
                break

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                print(
                    f"Erreur : Impossible d'ajouter {card_data['name']} à la base de données."
                )


class DBCards:
    """Classe qui gère les requêtes à la base concernant les cartes."""

    def __init__(self) -> None:
        self.helper = {}
        self.clean_keys = {}
        self.helpers()

    def helpers(self) -> None:
        """Procédure qui permet de recréer les helpers après un update de la base de données."""
        session = init_database()
        cards = session.query(Cartes).all()

        self.helper = {
            card.name: {
                "id": card.id,
                "name": card.name,
                "type": card.type,
                "mana_value": card.mana_value,
                "color_identity": card.color_identity,
                "text": card.text,
                "first_print": card.first_print,
                "legalities": card.legalities,
            }
            for card in cards
        }

        self.clean_keys = {
            self._remove_accents(card_name): card_data
            for card_name, card_data in self.helper.items()
        }

    def _remove_accents(self, string: str) -> str:
        """Méthode statique qui retourne une chaine contenant uniquement des lettres."""
        string = string.replace("&amp;", "")
        return "".join(char for char in unidecode(string) if char.isalpha()).lower()

    def get(self, card_name: str) -> dict:
        """Récupération et contrôle des clés utilisées."""
        if card_name == "Unknown Card":
            return {"name": "Unknown Card"}

        if card_name in self.helper.keys():
            return self.helper.get(card_name)

        card_name = self._remove_accents(card_name)
        if card_name in self.clean_keys.keys():
            return self.clean_keys.get(card_name)

        possible_keys = [
            value
            for key, value in self.clean_keys.items()
            if key.startswith(card_name) and " // " in value["name"]
        ]
        if len(possible_keys) == 1:
            return possible_keys[0]

        return {}

    def has_leadership(self, card) -> bool:
        """Méthode pour savoir si la carte aurait pu être commander."""
        if type(card) == str:
            card = self.get(card)

        if card["name"].startswith("A-"):
            return False

        if "legendary" not in card["type"].lower():
            return False

        if (
            "creature" not in card["type"].lower()
            and "can be your commander" not in card["text"].lower()
        ):
            return False

        return True

    def is_commander(self, card) -> bool:
        """Méthode pour savoir si la carte est actuellement commander."""
        if type(card) == str:
            card = self.get(card)

        if not self.has_leadership(card):
            return False

        legalities = card["legalities"]
        if "duel" in legalities.keys() and legalities["duel"] == "Restricted":
            return False

        return True


def oldest_set(set_codes):
    """Fonction pour vérifier quel est le premier set d'impression d'une carte."""
    session = init_database()
    sets = session.query(Sets).filter(Sets.code.in_(set_codes)).all()

    oldest_release_date = datetime.now().date()
    oldest_set = None

    for set in sets:
        if set.release_date and set.release_date < oldest_release_date:
            oldest_release_date = set.release_date
            oldest_set = set

    if oldest_set:
        return oldest_set.code
    else:
        set_codes[-1]


def init_sets():
    """Initialisation de la table de sets."""
    sets = AllSets()
    return sets


def init_cards():
    """Initialisation de la table de cartes."""
    cards = AllCards()
    return cards
