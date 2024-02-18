"""Module de scrap de MTGTOP8 et de mise en base des tournois."""

import math
import re
from datetime import datetime
from threading import Lock, Thread

import requests
from bs4 import BeautifulSoup
from mtgdc_carddata import DBCards
from mtgdc_database import Cartes, Decks, Tournois, init_database, stmt_set_deck_carte

CARDS = DBCards()

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "3600",
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0)"
        + "Gecko/20100101 Firefox/52.0"
    ),
}


class Soupe:
    """Classe qui contient les informations pour le scrapping."""

    def __init__(self, link: str) -> None:
        self.link = link
        self.soup = self.get_soup()

    @property
    def encoding(self) -> str:
        """Propriété contenant l'encoding de mtgtop8."""
        return "iso-8859-1"

    def get_soup(self) -> BeautifulSoup:
        """Fonction qui récupère la page demandée."""
        req = requests.get(self.link, HEADERS, stream=True, timeout=5000)
        req.encoding = self.encoding
        return BeautifulSoup(req.content, "html.parser", from_encoding=self.encoding)


class MTGDeck(Soupe):
    """Classe pour représenter l'objet Deck."""

    def __init__(self, deck_id: str) -> None:
        # C'est un appel "à blanc" du deck car j'ai observé que
        # si la page de deck n'était pas visitée au préalable,
        # l'exportation de la decklist ne fonctionnait pas correctement
        tmp = Soupe(f"https://mtgtop8.com/event?e=1&d={deck_id}").soup

        super().__init__(f"https://mtgtop8.com/mtgo?d={deck_id}")
        self.id = deck_id

        self.data = {
            "mainboard": [],
            "sideboard": [],
            "player": "",
            "rank": 0,
        }

    @property
    def to_dict(self) -> dict:
        """Propriété pour gérer la représentation en dict de l'objet."""
        return {
            "id": self.id,
            "rank": self.rank,
            "player": self.player,
            "commander": self.commander,
            "decklist": self.mainboard,
        }

    @property
    def decklist(self) -> str:
        """Propriété retournant la decklist."""
        return self.soup.prettify()

    @property
    def commander(self) -> list:
        """Propriété qui retourne le sideboard."""
        if len(self.data["sideboard"]) == 0:
            if "Sideboard" not in self.decklist:
                self.data["sideboard"] = ["Unknown Card"]
            else:
                self.data["sideboard"] = [
                    line[2:].strip()
                    for line in re.split("Sideboard", self.decklist)[1].split("\n")
                    if len(line[2:].strip()) > 0
                ]

            # Make sure every card is properly typed
            for idx, carte in enumerate(self.data["sideboard"]):
                self.data["sideboard"][idx] = CARDS.get(carte)["name"]

        return self.data["sideboard"]

    @property
    def mainboard(self) -> list:
        """Propriété qui retourne le mainboard."""
        if len(self.data["mainboard"]) == 0:
            if "Sideboard" not in self.decklist:
                self.data["mainboard"] = [
                    line.strip() for line in self.decklist.split("\n") if line.strip()
                ]
            else:
                self.data["mainboard"] = [
                    line.strip()
                    for line in re.split("Sideboard", self.decklist)[0].split("\n")
                    if line.strip()
                ]

            # Clean card names in case of encoding errors
            lines = []
            for line in self.data["mainboard"]:
                tmp = line.split(" ", maxsplit=1)
                tmp[1] = CARDS.get(tmp[1])["name"]
                lines.append(" ".join(tmp))

            self.data["mainboard"] = lines

        return self.data["mainboard"]

    @property
    def rank(self) -> str:
        """Propriété pour gérer le rang du deck dans le tournoi."""
        return self.data["rank"]

    @rank.setter
    def rank(self, value: str) -> None:
        """Setter pour le rang du deck."""
        self.data["rank"] = value  # int impossible car rang "5-8" par exemple

    @property
    def player(self) -> str:
        """Propriété pour gérer le joueur du deck."""
        return self.data["player"]

    @player.setter
    def player(self, value: str) -> None:
        """Setter pour le joueur du deck."""
        self.data["player"] = value


class MTGTournoi(Soupe):
    """Classe pour représenter l'objet Tournoi."""

    def __init__(self, link: str) -> None:
        super().__init__(link)
        self.soup = self.get_soup()
        self.tournoi_id = link.split("=")[1]
        self._is_commander = None
        self.data = {
            "name": "",
            "place": "",
            "players": 0,
            "date": datetime(1993, 8, 5),
        }

    @property
    def to_dict(self) -> dict:
        """Fonction qui permet d'exporter l'objet Tournoi en dictionnaire."""
        return {
            "format": "Duel Commander",
            "id": self.tournoi_id,
            "name": self.name,
            "place": self.place,
            "players": self.players,
            # "date": self.date,
            "date": str(self.date),
            "decks": self.decks,
        }

    @property
    def is_commander(self) -> bool:
        """Propriété qui vérifie que la soupe contient un tournoi en Duel Commander."""
        if self._is_commander is None:
            tag = self.soup.find("div", class_="meta_arch")
            self._is_commander = tag is not None and "Duel Commander" in tag.text
        return self._is_commander

    @property
    def name(self) -> str:
        """Propriété qui retourne le nom de l'événement."""
        if self.data["name"] == "":
            self._set_name_place()
        return self.data["name"]

    @property
    def place(self) -> str:
        """Propriété qui retour le lieu de l'événement."""
        # Le lieu n'est pas toujours indiqué mais le nom l'est toujours
        if self.data["place"] == "" and self.data["players"] == 0:
            self._set_name_place()
        return self.data["place"]

    @property
    def players(self) -> str:
        """Propriété qui retourne le nombre de joueurs."""
        if self.data["players"] == 0:
            self._set_players_date()
        return self.data["players"]

    @property
    def date(self) -> str:
        """Propriété qui retourne la date de l'événement."""
        if self.data["date"] == datetime(1993, 8, 5):
            self._set_players_date()
        return self.data["date"]

    @property
    def decks(self) -> list[MTGDeck]:
        """Propriété qui retourne la liste des decks de la page."""
        top8_decks = [
            (tag, "top8") for tag in self.soup.select("div.S14 a[href^='?e=']")
        ]
        out_decks = [(tag, "out") for tag in self.soup.select("optgroup option")]
        decks_to_crawl = top8_decks + out_decks

        # Stockage des decks
        response = []
        deck_ids = []  # Cas de nesting de balise dans certains tournois

        def get_deck_info(deck, option, lock):
            """Procédure appelée lors du threading."""
            if option == "top8":
                rdeck = MTGDeck(re.split("=", deck["href"])[2][:-2])
                block = deck.parent.parent.parent
                try:
                    rdeck.player = block.find(
                        "a", attrs={"class": "player"}
                    ).string.strip()
                except AttributeError:
                    return
                for div in block.find_all("div"):
                    if div.string is not None:
                        if re.match(r"\d(?:-\d)?", div.string):
                            rdeck.rank = div.string

            if option == "out" and deck["value"] not in deck_ids:
                rdeck = MTGDeck(deck["value"])
                rdeck.player = re.split(" - ", deck.contents[0], maxsplit=1)[1].strip()
                rdeck.rank = re.split("#", deck.parent["label"], maxsplit=1)[1]

            with lock:
                deck_ids.append(rdeck.id)
                response.append(rdeck.to_dict)

        threads = [
            Thread(
                target=get_deck_info,
                args=(item[0], item[1], Lock()),
            )
            for item in decks_to_crawl
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        response = [item for item in response if item is not None]
        response = sorted(response, key=lambda i: int(i["id"]))

        return response

    def _set_name_place(self) -> None:
        """Fonction qui récupère le nom et le lieu depuis la soupe."""
        tag = self.soup.find("div", class_="event_title")
        if tag is not None:
            if "@" not in tag.text:
                self.data["name"] = tag.text
            else:
                (name, place) = re.split("@", tag.text, maxsplit=1)
                self.data["name"] = name.strip()
                self.data["place"] = place.strip()

    def _set_players_date(self) -> None:
        """fonction qui récupère le nombre de joueurs et la date depuis la soupe."""
        div_meta_arch = self.soup.find("div", class_="meta_arch")
        if div_meta_arch:
            tags = div_meta_arch.parent.find_all("div")
            for tag in tags:
                line = "".join(tag.text)
                if re.match(r"[0-9][0-9]/[0-9][0-9]", line) and "-" not in line:
                    self.data["date"] = datetime.strptime(line, "%d/%m/%y")
                elif "players" in line and "-" not in line:
                    self.data["players"] = int(
                        line.strip().split(" ", maxsplit=1)[0].strip()
                    )
                elif "players" in line and "-" in line:
                    (players, date) = re.split("-", line)
                    self.data["players"] = int(
                        players.strip().split(" ", maxsplit=1)[0].strip()
                    )
                    self.data["date"] = datetime.strptime(
                        date.strip(), "%d/%m/%y"
                    ).date()


def last_tournament_scrapped():
    """Retourne le dernier id de tournoi scrappé."""
    session = init_database()

    tournaments = session.query(Tournois).all()
    if len(tournaments) == 0:
        return 2695 - 1  # Premier tournoi DC sur mtgtop8 : 2695

    return max([tournament.id for tournament in tournaments])


def scrap_mtgtop8(span: int = 100, **kw):
    """Fonction asynchrone pour le scrapping de MTGTOP8."""

    def execute_scrap(tournament_id: int, label):
        tournament = MTGTournoi(f"https://mtgtop8.com/event?e={tournament_id}")

        if tournament.is_commander and tournament.date > datetime(1993, 8, 5).date():
            session = init_database()

            tournament_data = {
                "id": tournament.tournoi_id,
                "name": tournament.name,
                "place": tournament.place,
                "players": tournament.players,
                "date": tournament.date,
            }
            new_tournament = Tournois(**tournament_data)
            session.add(new_tournament)

            for deck in tournament.decks:
                deck_data = {
                    "id": deck["id"],
                    "tournoi_id": tournament.tournoi_id,
                    "rank": deck["rank"],
                    "player": deck["player"],
                }
                new_deck = Decks(**deck_data)
                session.add(new_deck)

                card_names = [
                    line.split(" ", maxsplit=1)[1] for line in deck["decklist"]
                ]
                if "Unknown Card" in (card_names + deck["commander"]):
                    session.rollback()
                    session.close()
                    return False

                for card_name in deck["commander"]:
                    card = session.query(Cartes).filter_by(name=card_name).first()
                    new_deck.commanders.append(card)

                cards = session.query(Cartes).filter(Cartes.name.in_(card_names)).all()
                card_dict = {card.name: card for card in cards}
                for line in deck["decklist"]:
                    qty, card_name = line.split(" ", maxsplit=1)
                    card = card_dict.get(card_name)

                    if card:
                        session.execute(stmt_set_deck_carte(new_deck, card, int(qty)))

            session.commit()
            session.close()

            if label:
                #update_label(label)
                label.master.update_label()
                label.master.parent.f_display.insert_tournament()

    tournament_id = last_tournament_scrapped()
    label = kw.get("label", None)

    for loop in range(math.ceil(span // 10)):
        threads = [
            Thread(
                target=execute_scrap, args=((tournament_id + 1 + i + loop * 10), label)
            )
            for i in range(10)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
