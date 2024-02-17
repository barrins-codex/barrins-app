"""Onglet pour l'extraction et l'affichage des tournois depuis MTGTOPO8."""

import threading
from tkinter import ttk

from mtgdc_carddata import AllCards, AllSets
from mtgdc_database import Decks, Tournois, init_database
from mtgdc_scrapper import last_tournament_scrapped, scrap_mtgtop8, update_label


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


class ExtractMtgTop8(ttk.Labelframe):
    """Scrapping de MTGTOP8."""

    def __init__(self, parent):
        super().__init__(parent, text="Données MTGTOP8")

        # Configuration de la grille
        self.grid(row=0, column=0, columnspan=6, sticky="nsew", padx=5, pady=5)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=5)
        self.rowconfigure(0, weight=1)

        # Ajout apparence
        self.extract_button = ttk.Button(
            self, text="Extraction", command=self.start_extraction
        )
        self.extract_button.grid(row=0, column=0, sticky="ew", padx=20)

        # Dernier tournoi
        self.last_tournament_label = ttk.Label(self, text="")
        self.last_tournament_label.grid(row=0, column=1, sticky="ew", padx=20)
        update_label(self.last_tournament_label)

    def start_extraction(self):
        """Action du bouton."""
        self.extract_button.configure(state="disabled")

        # Contrôle que les data sont à jour
        AllSets()
        AllCards()

        # Extraction MtgTop8
        thread = threading.Thread(target=self.mtgtop8_extraction)
        thread.start()

    def mtgtop8_extraction(self):
        """Boucle de scrapping."""
        last_id = 0
        loops = 0

        while last_id < last_tournament_scrapped():
            last_id = last_tournament_scrapped()
            loops += 1

            scrap_mtgtop8(2000, label=self.last_tournament_label)

        return


class DisplayMtgTop8(ttk.Labelframe):
    """Affichage des tournois et decks en base de données."""

    def __init__(self, parent) -> None:
        super().__init__(parent, text="Decks en base de données")

        # Configuration de la grille
        self.grid(
            row=1, column=0, rowspan=5, columnspan=6, sticky="nsew", padx=5, pady=5
        )

        # Ajout du tableau
        self.tableau = ttk.Treeview(
            self, columns=["col0", "col1", "col2", "col3"], show="headings"
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.tableau.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.tableau.bind("<Double-1>", self.on_double_click)

        # Mise en page des colonnes
        base_width = 700
        self.tableau.column("col0", width=int(base_width * 1 / 27))
        self.tableau.column("col1", width=int(base_width * 15 / 27))
        self.tableau.column("col2", width=int(base_width * 8 / 27))
        self.tableau.column("col3", width=int(base_width * 3 / 27))

        # Nom des colonnes
        self.sorting_states = {col: True for col in ["col0", "col1", "col2", "col3"]}
        self.tableau.heading("col0", text="", command=lambda: self.sort_column("col0"))
        self.tableau.heading(
            "col1", text="Date", command=lambda: self.sort_column("col1")
        )
        self.tableau.heading(
            "col2", text="Name", command=lambda: self.sort_column("col2")
        )
        self.tableau.heading(
            "col3", text="Size", command=lambda: self.sort_column("col3")
        )

        self.load_data()

    def sort_column(self, col):
        """Fonciton pour tri des colonnes."""
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
        for row in self.tableau.get_children():
            self.tableau.delete(row)

        session = init_database()
        tournois = session.query(Tournois).order_by(Tournois.date.desc()).all()
        for tournoi in tournois:
            self.tableau.insert(
                "",
                "end",
                values=("➕", tournoi.name, tournoi.date, tournoi.players),
                iid=tournoi.id,
                tags=(tournoi.id,),
            )

    def load_decks(self, id_tournoi):
        """Récupération et affichage des decks."""
        session = init_database()
        decks = (
            session.query(Decks)
            .filter_by(tournoi_id=id_tournoi)
            .order_by(Decks.rank.asc())
            .all()
        )
        for deck in decks:
            commanders = " + ".join([carte.name for carte in deck.commanders])
            self.tableau.insert(
                id_tournoi,
                "end",
                values=("↳", deck.player, commanders, ""),
                tags=(id_tournoi,),
            )

    def on_double_click(self, event):
        """Drill up et down tournois/decks."""
        item = self.tableau.selection()[0]
        parent = self.tableau.parent(item)

        if parent == "":
            tournoi_id = self.tableau.item(item, "tags")[0]
            self.remove_children(item)
            self.load_decks(tournoi_id)

            values = list(self.tableau.item(item, "values"))
            values[0] = "➖" if values[0] == "➕" else "➕"
            self.tableau.item(item, values=values)

        else:
            self.remove_children(parent)

            values = list(self.tableau.item(parent, "values"))
            values[0] = "➕" if values[0] == "➖" else "➖"
            self.tableau.item(parent, values=values)

    def remove_children(self, parent):
        """Retrait des enfants du tableau."""
        children = self.tableau.get_children(item=parent)
        for child in children:
            self.tableau.delete(child)
