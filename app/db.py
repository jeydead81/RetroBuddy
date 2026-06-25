import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS factures (
  id INTEGER PRIMARY KEY,
  fichier TEXT,
  labo TEXT,
  numero_facture TEXT,
  date_facture TEXT,
  type_document TEXT,
  total_affiche REAL,
  total_calcule REAL,
  statut TEXT,
  motif TEXT,
  modele_extraction TEXT,
  ingere_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lignes_facture (
  id INTEGER PRIMARY KEY,
  facture_id INTEGER REFERENCES factures(id),
  code TEXT, type_code TEXT, code_interne TEXT,
  designation TEXT,
  qte REAL, qte_gratuite REAL,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  montant_ht REAL, tva REAL,
  checksum_ok INTEGER,
  valide INTEGER
);

CREATE TABLE IF NOT EXISTS referentiel_prix (
  code TEXT, date_facture TEXT,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  designation TEXT, facture_id INTEGER,
  PRIMARY KEY (code, date_facture)
);

CREATE TABLE IF NOT EXISTS abreviations_labo (
  abrev TEXT PRIMARY KEY, complet TEXT
);
"""


def get_connection(chemin="data/retrocession.db"):
    chemin = str(chemin)
    if chemin != ":memory:":
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
