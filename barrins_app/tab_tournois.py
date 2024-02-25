"""Onglet pour l'extraction et l'affichage des tournois depuis MTGTOPO8."""

import time
from tkinter import ttk

from cls_thread import DaemonThread as Thread
from mtgdc_carddata import DBCards, init_cards, init_sets
from mtgdc_database import Decks, Tournois, init_database
from mtgdc_scrapper import last_tournament_scrapped, scrap_mtgtop8

CARDS = DBCards()


class TournoisTab(ttk.Frame):
    """Onglet tournois."""

    def __init__(self, parent):
        super().__init__(parent)

        # Grid 6x6
        for i in range(6):
            self.grid_rowconfigure(i, weight=1)
            self.grid_columnconfigure(i, weight=1)

        # Ajouter des widgets à la grille
        self.f_extract = ExtractMtgTop8(self)
        self.f_display = DisplayMtgTop8(self)

        # Threads de l'onglet
        self.thread_load_data = Thread(target=self.f_display.load_data)

        # Exécution du chargement des decks lors de l'accès à l'onglet
        parent.bind("<<NotebookTabChanged>>", self.on_tab_change)

    def on_tab_change(self, event):
        """Chargement des tournois et decks en base uniqment à l'accès à l'onglet."""

        selected_tab = event.widget.select()
        tab_name = event.widget.tab(selected_tab, "text")
        if tab_name == "Tournois":
            self.unbind("<<NotebookTabChanged>>")
            self.thread_load_data.start()

    def on_closing(self):
        """Méthode appelée lors de la fermeture de l'application."""

        print("tournois tab closing")
        pass

    def mtgtop8_extraction(self):
        """Boucle de scrapping."""

        last_id = last_tournament_scrapped()

        scrap_mtgtop8(
            2000,
            label=self.f_extract.update_label,
            display=self.f_display.insert_last_tournament,
        )

        if last_id < last_tournament_scrapped():
            self.mtgtop8_extraction()


class ExtractMtgTop8(ttk.Labelframe):
    """Scrapping de MTGTOP8."""

    def __init__(self, parent):
        super().__init__(parent, text="Données MTGTOP8")
        self.parent = parent

        # Configuration de la grille
        self.grid(row=0, column=0, columnspan=6, sticky="nsew", padx=5, pady=5)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=5)
        self.rowconfigure(0, weight=5)
        self.rowconfigure(1, weight=1)

        # Ajout apparence
        self.extract_button = ttk.Button(
            self, text="Extraction", command=self.start_extraction
        )
        self.extract_button.grid(row=0, column=0, sticky="ew", padx=20)

        # Dernier tournoi
        self.last_tournament_label = ttk.Label(self, text="")
        self.last_tournament_label.grid(row=0, column=1, sticky="ew", padx=20)
        self.update_label()

        # Message sur freeze pendant DB update
        self.warning_message = ttk.Label(
            self,
            text=(
                "This software updates its MTG database once every week. "
                + "During this update, it may freeze due to heavy payload."
            ),
            font=("Arial", 10, "italic"),
            anchor="center",
        )
        self.warning_message.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20)

        # Threads de la zone
        self.extract_mtgtop8_thread = Thread(target=self.parent.mtgtop8_extraction)
        self.init_sets_thread = Thread(target=init_sets)
        self.init_cards_thread = Thread(target=init_cards)

    def start_extraction(self):
        """Action du bouton."""

        self.extract_button.configure(state="disabled")

        # Contrôle que les data sont à jour
        self.extract_button.configure(text="Updating MTG Data")
        self.init_sets_thread.start()
        self.init_cards_thread.start()
        self.extract_button.configure(text="MTG Data Updated")

        CARDS.helpers()

        # Extraction MtgTop8
        self.extract_button.configure(text="Scrapping...")
        self.extract_mtgtop8_thread.start()

    def update_label(self):
        """Mise à jour du label de résumé d'extraction."""

        session = init_database()
        last = session.query(Tournois).order_by(Tournois.id.desc()).first()

        if last:
            name = last.name if len(last.name) < 25 else last.name[:22] + "..."
            label_text = f'Last added: "{name}", {last.players} players, on {last.date}'
        else:
            label_text = "No tournament in database."

        self.last_tournament_label.config(text=label_text)
        session.close()


class DisplayMtgTop8(ttk.Labelframe):
    """Affichage des tournois et decks en base de données."""

    def __init__(self, parent) -> None:
        super().__init__(parent, text="Decks en base de données")

        # Configuration de la grille
        self.grid(
            row=1, column=0, rowspan=5, columnspan=6, sticky="nsew", padx=5, pady=5
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Ajout du tableau
        self.tableau = ttk.Treeview(self, columns=["col1", "col2", "col3"])
        self.tableau.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Mise en page des colonnes
        base_width = 700
        self.tableau.column("#0", width=int(base_width * 1 / 27))
        self.tableau.column("col1", width=int(base_width * 13 / 27))
        self.tableau.column("col2", width=int(base_width * 9 / 27))
        self.tableau.column("col3", width=int(base_width * 3 / 27))

        # Nom des colonnes
        self.sorting_states = {col: True for col in ["col1", "col2", "col3"]}
        self.tableau.heading("col1", text="Name", command=lambda: self.sort_c("col1"))
        self.tableau.heading("col2", text="Date", command=lambda: self.sort_c("col2"))
        self.tableau.heading("col3", text="Size", command=lambda: self.sort_c("col3"))

    def sort_c(self, col):
        """Fonction pour tri des colonnes."""

        items = [(self.tableau.set(k, col), k) for k in self.tableau.get_children("")]
        reverse = self.sorting_states[col]

        if col == "col3":
            items.sort(key=lambda x: int(x[0]), reverse=reverse)
        else:
            items.sort(reverse=reverse)

        for index, (val, k) in enumerate(items):
            self.tableau.move(k, "", index)

        self.sorting_states[col] = not reverse
        self.tableau.heading(col, command=lambda: self.sort_column(col))

    def load_data(self):
        """Récupération des tournois et affichage dans le tableau."""

        session = init_database()
        tournois = session.query(Tournois).order_by(Tournois.id.desc()).all()
        for tournoi in tournois:
            self.display_tournament(tournoi)
            time.sleep(0.2)

    def insert_last_tournament(self):
        """Insertion du dernier tournoi scrappé."""

        session = init_database()
        tournoi = session.query(Tournois).order_by(Tournois.date.desc()).first()
        self.display_tournament(tournoi)

    def display_tournament(self, tournoi: Tournois):
        """Affichage du tournoi et des decks liés."""

        self.tableau.insert(
            "",
            "end",
            values=(tournoi.name, tournoi.date, tournoi.players),
            iid=tournoi.id,
            tags=(tournoi.id,),
        )

        [
            Thread(target=self.insert_deck, args=(deck,)).start()
            for deck in tournoi.decks
        ]

    def insert_deck(self, deck: Decks):
        """Insertion d'un deck d'après ses données."""

        self.tableau.insert(
            deck.tournoi_id,
            "end",
            values=(deck.player, CARDS.command_zone_to_str(deck.commanders), ""),
            tags=(deck.tournoi_id,),
        )
