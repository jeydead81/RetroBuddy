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
  cout_estime REAL,
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
  valide INTEGER,
  motif_ligne TEXT
);

CREATE TABLE IF NOT EXISTS referentiel_prix (
  code TEXT, date_facture TEXT,
  type_code TEXT, labo TEXT,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  designation TEXT, facture_id INTEGER,
  PRIMARY KEY (code, date_facture)
);

CREATE TABLE IF NOT EXISTS retro_documents (
  id INTEGER PRIMARY KEY,
  fichier TEXT,
  pharmacie_emettrice TEXT,
  pharmacie_destinataire TEXT,
  date_vente TEXT,
  numero TEXT,
  cout_estime REAL,
  ingere_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS retro_lignes (
  id INTEGER PRIMARY KEY,
  retro_id INTEGER REFERENCES retro_documents(id),
  designation TEXT, code TEXT, type_code TEXT,
  qte REAL, tva REAL,
  bl_numero TEXT, bl_date TEXT,
  code_resolu TEXT,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  ug REAL DEFAULT 0,
  passe_match INTEGER,
  score_match REAL,
  statut_ecart TEXT,
  valide_utilisateur INTEGER DEFAULT 0,
  saisie_manuelle INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS correspondance_codes (
  code_a TEXT, code_b TEXT,
  PRIMARY KEY (code_a, code_b)
);

CREATE TABLE IF NOT EXISTS abreviations_labo (
  abrev TEXT PRIMARY KEY, complet TEXT
);
"""

# Colonnes ajoutées après la V1 initiale. Migration idempotente : la base
# `retrocession.db` est copiée d'un poste à l'autre entre confrères, on doit
# pouvoir la mettre à niveau sans perdre les données existantes.
_COLONNES_AJOUTEES = [
    ("referentiel_prix", "type_code", "TEXT"),
    ("referentiel_prix", "labo", "TEXT"),
    ("referentiel_prix", "modifie_manuellement", "INTEGER DEFAULT 0"),
    ("lignes_facture", "motif_ligne", "TEXT"),
    ("factures", "cout_estime", "REAL"),
]


def get_connection(chemin="data/retrocession.db"):
    chemin = str(chemin)
    if chemin != ":memory:":
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _colonnes(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrer(conn):
    for table, col, typ in _COLONNES_AJOUTEES:
        if col not in _colonnes(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def init_db(conn):
    conn.executescript(SCHEMA)
    _migrer(conn)
    conn.commit()
