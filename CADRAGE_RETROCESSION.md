# Projet : Automatisation des factures de rétrocession inter-pharmacies - RetroBuddy

## Document de cadrage — Version 3 (finale, 4 temps, éprouvée sur formats réels)

Document destiné à amorcer le développement dans Claude Code. Règles métier verrouillées
et validées sur de vrais échantillons.

---

## 1. Objectif

Automatiser la production des factures de rétrocession entre 4 pharmacies confrères
partageant le même LGO. Réduire ~6 semaines/an de travail manuel à quelques heures de
validation d'exceptions.

Principe directeur : **aucune erreur permise sur le montant facturé.** Viser le 100 %
correct, pas le 100 % automatique muet. Tout ce qui n'est pas certain est signalé pour
vérification, jamais masqué. Aucun export d'une facture incomplète.

**Architecture technique (actée) :**
- **Application web locale** : FastAPI sert une interface sur localhost, ouverte dans le
  navigateur. Pas de serveur distant, pas de comptes utilisateurs, pas de cloud (hors
  appels API d'extraction). Installable telle quelle chez chacun des 4 confrères.
- **Persistance SQLite** : un simple fichier `retrocession.db` dans le dossier de l'app,
  intégré nativement à Python, sans serveur ni installation séparée. Sert à stocker le
  référentiel prix une fois pour toutes (ingestion annuelle) et à le réinterroger à chaque
  rétrocession, ce qui évite de ré-ingérer (et re-payer) les factures labo. Le fichier se
  copie d'un poste à l'autre ; prévoir un bouton « exporter/importer la base » pour que les
  confrères partagent un référentiel commun.

---

## 2. Architecture en QUATRE temps

### TEMPS 1 — Référentiel prix (factures laboratoires)

- Entrée : factures labo en PDF, zone d'import « factures sources ».
- Classification du document (§4) -> extraction IA (prompt A, §8.1) -> filtrage lignes
  valides (§3.2) -> garde-fous (§5).
- Sortie : **référentiel prix historisé** (par code, tous les prix nets avec leur date).

### TEMPS 2 — Ingestion LGO + matching automatique

- Entrée : « facture de vente rétrocession » du LGO (ex. LGPI), zone d'import distincte.
- Colonnes prix/remise/montant du LGO = FAUSSES -> ignorées.
- Extraction (prompt B, §8.2) : désignation, code, qté, TVA, n°/date BL, pharmacie
  émettrice, destinataire.
- **Matching automatique** par code sur le référentiel (passes 1->6, §6).
- Calcul du prix : dernier prix net <= date du BL de la ligne (§3.1).

### TEMPS 3 — Résolution des écarts (étape humaine)

- L'outil présente UNIQUEMENT ce qui n'est pas résolu automatiquement.
- Interface : **vue tableau unique type Excel dans le navigateur** (pas de wizard, pas de
  textbox). Édition inline, filtrable/triable.
- **Compteur visible en haut** : nombre de lignes à vérifier / à compléter / auto-validées,
  + barre de progression. L'utilisateur sait combien il en a AVANT de commencer.
- Code couleur par type d'écart :
  - ROUGE = prix manquant (produit LGO introuvable dans les factures labo) -> saisie
    manuelle PA brut / remise / PA net. **Bloquant.**
  - ORANGE = résolu par désignation (passes 3-4-5) -> à confirmer. Non bloquant.
- Lignes ORANGE **validées par défaut** si score élevé (seuil configurable, ex. >=0,95 +
  contenance/dosage concordants) ; **à confirmer** en dessous du seuil. Candidat proposé
  affiché à côté (ex. « LGO X -> facture Y, score 0,94 ») avec accepter/refuser.
- Champs lecture seule : désignation LGO, code, qté, BL/date. Champs éditables : PA brut,
  remise %, PA net (recalcul auto).
- Option ouverte : export/import Excel pré-rempli pour ceux qui préfèrent travailler dans
  Excel (mais le tableau web reste recommandé car il peut bloquer l'export).

### TEMPS 4 — Édition de la facture de rétrocession

- Intègre le matching automatique (Temps 2) + les corrections (Temps 3).
- En-tête : pharmacie émettrice (vendeur) + destinataire (acheteur).
- Structure calquée sur le PDF LGO : regroupement **par BL** (avec sa date), puis lignes.
- Colonnes : Désignation | Code | Qté | PA brut | Remise % | PA net | TVA | Montant HT.
  - PA brut, Remise %, PA net du référentiel labo (vrai coût), affichés pour vérification.
  - Montant HT = Qté x PA net.
- Pied : ventilation TVA par taux (2,1 / 5,5 / 10 / 20) + Total HT, Total TVA, Total TTC.
- Bouton « Générer la facture » DÉSACTIVÉ tant qu'une ligne ROUGE subsiste. Les ORANGE ne
  bloquent pas.
- Sortie : PDF (calqué LGO) + export Excel/CSV.

---

## 3. Règles métier (verrouillées)

### 3.1 Calcul du prix de rétrocession

- Prix = dernier prix net unitaire connu, de la dernière facture labo valide dont la date
  <= date du BL de la ligne.
- La date est portée par CHAQUE BL : deux lignes du même produit sous deux BL de dates
  différentes peuvent recevoir deux prix différents. Ne jamais fusionner les occurrences.
- Prix coûtant strict : pas de marge, pas de décote.
- TVA = celle du document LGO (suit le produit), pas celle de la facture labo.

### 3.2 Sélection des lignes valides (Temps 1)

Retenir : prix brut > 0, remise < 100 %, prix net > 0, rattachée à un code. Ignorer : UG
(y compris ligne séparée « remise 100 % » / net = 0), RFA, remises globales/exceptionnelles
non rattachées à un produit.

### 3.3 Unités gratuites (UG) — Option B

- Extraction auto : UG ignorées.
- Temps 3/4 : champ UG éditable ; s'il est renseigné, net recalculé :
  PA net = (Qté x PA brut x (1 - remise%)) / (Qté + UG).
- Piège : « UG » dans une désignation (ex. FORCAPIL ANTI-CHUTE 2MOIS + 1UG) = nom
  commercial, PAS une unité gratuite.

### 3.4 Lignes sans facture source

Code LGO absent du référentiel -> ligne ROUGE « prix à compléter ». Saisie manuelle.
Export bloqué tant qu'une ROUGE n'est pas chiffrée.

---

## 4. Classification du document (Temps 1, avant extraction)

| Nature | Marqueurs | Action |
|--------|-----------|--------|
| facture_marchandise | lignes produit, total HT positif | Traiter |
| avoir | AVOIR, Avoir net de taxe, Avoir déduit, montants négatifs | Ignorer |
| abonnement_service | abonnement logiciel, prestation, autocollants, mobilier | Ignorer |
| releve | relevé d'échéances | Ignorer |
| autre / grossiste | — | Ignorer (V1) |

Validé sur le lot : URGO, PHOENIX, Cooper c600135086, Havea/IRB = avoirs ;
Pharmagest/Equasens = abonnement ; Sandoz = autofacturation prestation -> exclus.
Décision V1 : les avoirs n'impactent pas le référentiel.

---

## 5. Garde-fous automatiques (Temps 1)

1. Checksum codes : clé CIP13 (préfixe 34009) et EAN13. Invalide -> non rapproché, signalé.
2. Validation contre le PU net AFFICHÉ, PAS de reconstruction depuis une seule remise.
   Validé (multi-remises) : Pierre Fabre 2,10 x 0,90 = 1,89 != net 1,98 ; Perrigo R1 12,25 %
   + R2 27,75 % != net 5,98.
3. Cohérence totaux : somme lignes ~= total HT. Écart > seuil -> facture en revue.
4. Code interne != CIP/EAN : cibler le vrai code 13 chiffres (AbbVie 20007519, Fresenius
   107621 = codes internes, pas CIP).

---

## 6. Matching multi-passes (Temps 2)

| Passe | Méthode | Drapeau | Couleur Temps 3 |
|-------|---------|---------|-----------------|
| 1 | Code identique (CIP<->CIP, EAN<->EAN) | Non | (résolu, non affiché) |
| 2 | CIP<->EAN via clé / table | Non | (résolu, non affiché) |
| 3 | Désignation normalisée identique | Oui | Orange |
| 4 | Désignation proche (score IA) | Oui | Orange |
| 5 | Retour IA sur PDF factures | Oui | Orange |
| 6 | Introuvable -> saisie manuelle | Oui | Rouge |

Règle : passe >= 3 signalée au Temps 3. Passes 1-2 résolues silencieusement.
Terrain : codes propres et identiques entre LGO et factures labo -> passes 1-2 couvrent
l'écrasante majorité ; désignation = filet pour codes ayant changé.

### 6.1 Normalisation désignations (passes 3-4)

- Table abréviations labos maintenue à la main (ex. LRP -> LA ROCHE POSAY).
- Majuscules, suppression accents/ponctuation, normalisation dosages/contenances.
- Score explicite ; auto-validation si seuil haut + contenance concordante. Seuil
  configurable.

---

## 7. Pièges identifiés sur le lot réel

- Pages à l'envers (Perrigo p.2, 180°) : rotation auto à la conversion ; drapeau renforcé.
- Récapitulatifs tarifaires (Cooper p.2/3, texte libre sans codes ni qté livrées) : ne pas
  extraire ; drapeau structure inhabituelle.
- EAN sous intitulé « CIP/ACL » (Arkopharma) : se fier au contenu du code (clé), pas au nom.
- Multi-remises (Pierre Fabre, Perrigo, PiLeJe) : garde-fou §5.2.
- UG en lignes séparées (PiLeJe, Caudalie, Cooper colonne Qté Gratuite) : ignorées (§3.2).

---

## 8. Prompts d'extraction (éprouvés)

### 8.1 Prompt A — Factures labo (Temps 1)

JSON : type_document, entete{labo, numero_facture, date_facture, total_ht_affiche},
lignes[] : code (vrai CIP13/EAN13, jamais interne), type_code, code_interne, designation,
qte, qte_gratuite, prix_brut, remise_pct, remises_detail[], prix_net (AFFICHÉ, non
recalculé), montant_ht, tva. Règles : classifier d'abord ; privilégier net affiché ;
distinguer code interne et CIP/EAN.

### 8.2 Prompt B — Document LGO (Temps 2)

JSON : type_document = retro_lgo, entete{pharmacie_emettrice, pharmacie_destinataire,
date_vente, numero}, lignes[] : UNIQUEMENT designation, code, type_code, qte, tva,
bl_numero, bl_date. Règle impérative : ignorer entièrement PUHT, % Remise, Montant Remise,
Prix unitaire Net, Montant Total HT (valeurs fausses).

---

## 9. Schéma de données (SQLite)

CREATE TABLE factures (id INTEGER PRIMARY KEY, fichier TEXT, labo TEXT, date_facture DATE,
total_affiche REAL, total_calcule REAL, statut TEXT, ingere_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE lignes_facture (id INTEGER PRIMARY KEY, facture_id INTEGER REFERENCES factures(id),
code TEXT, type_code TEXT, code_interne TEXT, designation TEXT, qte REAL, prix_brut REAL,
remise_pct REAL, prix_net REAL, montant_ht REAL, tva REAL, checksum_ok BOOLEAN, valide BOOLEAN);

CREATE TABLE referentiel_prix (code TEXT, date_facture DATE, prix_brut REAL, remise_pct REAL,
prix_net REAL, designation TEXT, facture_id INTEGER, PRIMARY KEY (code, date_facture));

CREATE TABLE retro_documents (id INTEGER PRIMARY KEY, fichier TEXT, pharmacie_emettrice TEXT,
pharmacie_destinataire TEXT, date_vente DATE, numero TEXT);

CREATE TABLE retro_lignes (id INTEGER PRIMARY KEY, retro_id INTEGER REFERENCES retro_documents(id),
designation TEXT, code TEXT, type_code TEXT, qte REAL, tva REAL, bl_numero TEXT, bl_date DATE,
code_resolu TEXT, prix_brut REAL, remise_pct REAL, prix_net REAL, ug REAL DEFAULT 0,
passe_match INTEGER, score_match REAL, statut_ecart TEXT, -- 'resolu'|'orange'|'rouge'
valide_utilisateur BOOLEAN, saisie_manuelle BOOLEAN);

CREATE TABLE abreviations_labo (abrev TEXT PRIMARY KEY, complet TEXT);

Note : referentiel_prix garde l'historique complet (code+date), pas seulement le dernier
prix, pour résoudre « dernier prix <= date BL ».

---

## 10. Arborescence du projet

retrocession/
- README.md, requirements.txt, config.yaml (clé API, seuils)
- app/main.py (FastAPI : imports, UI, routes), app/db.py
- app/temps1/ : ingest_factures, extraction_ia (prompt A), pdf_reader (rotation auto),
  classifier (§4), filtres (§3.2), garde_fous, referentiel
- app/temps2/ : ingest_retro (prompt B), matching (passes 1->6), normalisation,
  retour_factures (passe 5), calcul_prix (<= date BL)
- app/temps3/ : ecarts.py (calcul des écarts + compteurs), api_resolution.py (endpoints
  édition inline / validation)
- app/temps4/ : facture_builder (regroupe par BL, ventile TVA), export_pdf (calqué LGO),
  export_xlsx
- app/codes/ : checksum, correspondance (CIP<->EAN)
- app/ui/ : resolution.html + resolution.js (tableau type Excel, compteur, couleurs,
  blocage export), facture_preview.html
- prompts/ : extraction_facture.txt (A), extraction_retro.txt (B)
- data/retrocession.db

---

## 11. Plan de développement par étapes

1. Socle : projet, SQLite, lecture PDF (pdftoppm/pdf2image + rotation).
2. Classification (§4) : trier factures / avoirs / abonnements.
3. Extraction labo (prompt A) + parsing JSON strict.
4. Garde-fous + filtres (§5, §3.2).
5. Référentiel prix historisé -> PREMIER LIVRABLE TESTABLE.
6. Extraction LGO (prompt B) : code+qté+TVA+BL+pharmacies.
7. Matching passes 1-2 + calcul prix <= date BL.
8. TEMPS 3 — interface résolution écarts : tableau type Excel, compteur, couleurs, édition
   inline, saisie manuelle, auto-validation orange. -> DEUXIÈME LIVRABLE TESTABLE.
9. Matching passes 3-5 : normalisation, score, retour factures (alimente les oranges).
10. TEMPS 4 — édition facture : PDF calqué LGO + Excel. Export bloqué si ligne rouge.

---

## 12. Coût API

Sonnet 4.6 ($3/$15 par M tokens). ~0,03 $/facture standard, ~0,015 $ en Batch.
4 pharmacies x 1 an : dizaines à quelques centaines de $/an. Précision ±50 % tant que le
volume réel n'est pas connu.

---

## 13. Points ouverts (non bloquants)

- Format graphique exact du PDF de sortie (logo, mentions légales émetteur).
- Référentiel CIP officiel (solidifie passes 1-2, table CIP<->EAN).
- Volume réel factures/an.
- Acter le point RGPD (factures fournisseurs via API).
- Mesurer le taux d'erreur réel de l'extraction vision à l'échelle (étapes 3-5, vraie clé API).
