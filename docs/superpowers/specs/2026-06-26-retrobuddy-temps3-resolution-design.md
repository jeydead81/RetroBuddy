# RetroBuddy — Temps 3 : Résolution des écarts + matching désignation + ingestion en tâche de fond — Design

> Troisième sous-projet de RetroBuddy. Construit sur les Temps 1-2. Cadrage global :
> `CADRAGE_RETROCESSION.md`.

- **Date** : 2026-06-26
- **Périmètre** : §11 étapes 8-9 du cadrage, + une amélioration UX transverse (ingestion
  en tâche de fond qui survit à la navigation).
- **Livrable** : l'étape humaine de résolution. L'outil présente **uniquement** ce qui n'est
  pas résolu automatiquement, dans un **tableau type Excel** (édition inline, compteurs,
  couleurs rouge/orange), alimenté par un **matching par désignation** (passes 3-4) ;
  l'ingestion tourne **côté serveur** et survit au changement d'onglet.

---

## 1. Objectif et périmètre

Trois composants, indépendamment testables :

- **A — Matching par désignation (passes 3-4)** : produit les candidats 🟠 orange quand le
  code n'a pas résolu (passes 1-2).
- **B — Tableau de résolution** (`/resolution`) : l'écran humain (rouge/orange uniquement,
  compteurs, couleurs, édition inline, validation).
- **C — Ingestion en tâche de fond** : refonte des deux flux d'import (labo `/ingest`,
  LGO `/retro`) pour que l'ingestion tourne côté serveur et **ne s'annule pas** si on
  navigue ailleurs.

Principe directeur inchangé : **aucune erreur permise sur le montant.** Un prix n'est jamais
inventé ; tout candidat orange est confirmable/refusable ; tout rouge est saisi à la main.

**Hors périmètre (plus tard) :**
- **Passe 5** (relecture IA des PDF labo pour rapprocher) — étape 9 restante.
- Édition de la facture de rétrocession PDF/Excel (Temps 4).

---

## 2. Composant A — Matching par désignation (passes 3-4)

### 2.1 Normalisation (`app/temps2/normalisation_designation.py`)
- `normaliser_designation(s, abreviations=None) -> str` : MAJUSCULES, suppression des
  accents (`unicodedata`), suppression ponctuation, espaces normalisés ; expansion des
  **abréviations** depuis la table `abreviations_labo` (ex. `LRP` → `LA ROCHE POSAY`).
- `extraire_dosage(s) -> set[str]` : isole les tokens dosage/contenance (`50ML`, `100MG`,
  `350G`, `B24`…) pour le contrôle de concordance.

### 2.2 Score déterministe (sans API)
- `score_designation(a_norm, b_norm) -> float` dans [0,1] : similarité sur les désignations
  normalisées (tokens triés + `difflib.SequenceMatcher`). Choix **déterministe** : rapide,
  testable, gratuit. L'IA (passe 5) viendra en renfort plus tard.

### 2.3 Rapprochement (`matching.py`, étendu)
- `resoudre_par_designation(conn, designation, seuil_bas) -> (code, score) | (None, 0)` :
  compare la désignation normalisée de la ligne à celles du **référentiel** (distinct
  `code, designation`), renvoie le meilleur si `score ≥ seuil_bas`.
- **Passe 3** = désignation normalisée identique (score = 1,0). **Passe 4** = meilleur score
  ≥ `seuil_bas` (défaut **0,80**, configurable).

### 2.4 Intégration au traitement (`traitement_retro.py`, étendu)
Pour chaque ligne, ordre de résolution :
1. Passes 1-2 (code) — inchangé.
2. Si échec → passe 3-4 (désignation) → `code` candidat → `prix_a_date(code, bl_date)`.
   - Prix trouvé → **🟠 orange** : stocke `code_resolu`, prix, `score_match`,
     `passe_match` (3 ou 4).
     - **Auto-validation** si `score ≥ seuil_auto` (défaut **0,95**) **et** dosage/contenance
       concordants → `valide_utilisateur=1` (orange pré-validé).
     - Sinon → orange « à confirmer » (`valide_utilisateur=0`).
   - Pas de candidat, ou pas de prix ≤ date BL → **🔴 rouge**.

### 2.5 Re-rapprochement à la demande
- `app/temps3/rematch.py` : `rematcher(conn, config)` rejoue passes 1-4 + calcul prix sur les
  lignes **ni validées ni saisies manuellement** (`valide_utilisateur=0` ET
  `saisie_manuelle=0`) de `retro_lignes`, contre le référentiel **actuel** — pour ne jamais
  écraser le travail humain en cours. Utile après avoir ingéré de nouvelles factures labo.
  Déterministe, sans API. Exposé par un bouton « Re-rapprocher » (§3).

---

## 3. Composant B — Tableau de résolution (`/resolution`)

- N'affiche **QUE** les lignes `rouge` et `orange` (les `resolu` vertes sont masquées).
- **Compteur en haut** : `à compléter` (rouge) / `à confirmer` (orange non validé) /
  `auto-validées` + **barre de progression** (validées / total à traiter).
- **Colonnes lecture seule** : désignation LGO, code, qté, BL n°/date, (candidat + score pour
  les oranges). **Éditables** : `PA brut`, `remise %`, `PA net`, `UG`.
- **Recalcul PA net** (cadrage §3.3, `app/temps3/resolution.py`) :
  `calcul_net(qte, prix_brut, remise_pct, ug) = qte*prix_brut*(1-remise/100)/(qte+ug)`
  (UG défaut 0 → `prix_brut*(1-remise/100)`). Recalculé à chaque édition de brut/remise/UG ;
  `PA net` reste sur-saisissable manuellement.
- **Orange** : candidat affiché (« réf. <designation>, score 0,94 ») + **Accepter** /
  **Refuser**. Accepter → `valide_utilisateur=1`. Refuser → repasse `rouge` (saisie manuelle).
- **Rouge** : saisie manuelle PA brut/remise/net → `saisie_manuelle=1`, `valide_utilisateur=1`
  quand un PA net > 0 est renseigné.
- Édition **inline** (vanilla JS), **sauvegarde par ligne**, filtrable/triable (filtre
  rouge/orange/validées).
- Bouton **« Re-rapprocher »** → `POST /resolution/rematch` (composant A §2.5).

### 3.1 Endpoints
- `GET /resolution` : page (lignes rouge+orange, compteurs).
- `POST /resolution/ligne/{id}` : enregistre `{prix_brut, remise_pct, prix_net, ug}` (recalcul
  serveur), met à jour `statut_ecart`/`valide_utilisateur`/`saisie_manuelle`. Renvoie la ligne
  recalculée (JSON).
- `POST /resolution/ligne/{id}/accepter` : valide le candidat orange.
- `POST /resolution/ligne/{id}/refuser` : repasse la ligne en rouge.
- `POST /resolution/rematch` : rejoue le matching (§2.5), renvoie les compteurs.

---

## 4. Composant C — Ingestion en tâche de fond (survit à la navigation)

### 4.1 Problème
Aujourd'hui l'ingestion est pilotée par le JS de la page (boucle `fetch` par fichier). Quitter
la page **annule** l'ingestion.

### 4.2 Solution : job serveur + polling
- **Registre de jobs en mémoire** (`app/jobs.py`) : `app.state.jobs[job_id]` →
  `{type, total, fait, recap, cout, details[], termine}`. L'app est **mono-processus local**
  (un worker uvicorn) → un dict en mémoire suffit. Accès protégé par un `threading.Lock`.
- `lancer_job(...)` démarre un `threading.Thread` qui traite les fichiers un par un (via
  `traiter_facture` / `traiter_retro`) en **ouvrant sa propre connexion SQLite** (les
  connexions ne se partagent pas entre threads), et met à jour l'état du job.
- **Endpoints** (pour chaque flux) :
  - `POST /ingest/start` (et `/retro/ingest/start`) : enregistre les fichiers (temp), crée un
    job, lance le thread, renvoie `{job_id, total}` immédiatement.
  - `GET /ingest/progress/{job_id}` (et `/retro/progress/{job_id}`) : renvoie l'état du job.
- **Page (JS)** : à la soumission → `start` → mémorise `job_id` dans **`localStorage`** →
  **poll** `progress` (~1 s) et met à jour compteur/barre/coût/liste. Comme le travail tourne
  côté serveur, **naviguer n'annule rien**. Au **chargement** de la page d'import, si un
  `job_id` actif est en `localStorage`, elle **reprend le polling** et réaffiche la
  progression (le job a continué pendant l'absence).
- Le job nettoie ses fichiers temporaires en fin de traitement ; un job terminé est conservé
  en mémoire (consultable) jusqu'au prochain démarrage de l'app.

### 4.3 Compatibilité
Les anciens endpoints `/ingest-un` et `/retro/ingest-un` (un fichier → JSON) sont **conservés**
(utilisés par les tests et comme brique interne du job). La page bascule sur `start`+`progress`.

---

## 5. Modèle de données

Aucune nouvelle table. `retro_lignes` a déjà : `code_resolu, prix_brut, remise_pct, prix_net,
ug, score_match, passe_match, statut_ecart` (`rouge`|`orange`|`resolu`), `valide_utilisateur`,
`saisie_manuelle`. La table `abreviations_labo` (déjà créée au Temps 1) est désormais
**exploitée** par la normalisation ; un petit jeu d'abréviations courantes peut être semé.

Config (nouveaux défauts) : `seuil_match_bas: 0.80`, `seuil_match_auto: 0.95`.

---

## 6. Stratégie de test

- **Normalisation** : accents, ponctuation, abréviations (LRP→LA ROCHE POSAY), extraction
  dosage/contenance.
- **Score** : identique→1,0 ; proche≥seuil ; éloigné<seuil.
- **Matching désignation** : candidat trouvé / non ; respect du seuil.
- **Auto-validation** : score≥0,95 + dosage concordant → validé ; dosage discordant → à
  confirmer.
- **Recalcul net** : avec/sans UG (formule §3.3).
- **Orchestration étendue** (`traiter_retro`) avec MockExtractor + référentiel synthétique :
  ligne orange (désignation), orange auto-validée, rouge (rien), priorité passes 1-2 > 3-4.
- **Rematch** : une ligne rouge devient orange après ajout d'une entrée au référentiel.
- **Résolution endpoints** : save (recalcul + statut), accepter, refuser, rematch.
- **Jobs** : `lancer_job` traite N fichiers (avec MockExtractor), `progress` reflète
  l'avancement et l'état final ; un job continue indépendamment du « client ».
- **Web** : `/resolution` 200 ; `/ingest/start` renvoie `job_id` ; `/ingest/progress/{id}`
  renvoie l'avancement.
- Tout testable **sans appel API** (MockExtractor + matching déterministe).

---

## 7. Gestion d'erreurs

- Un fichier en erreur dans un job → compté en `erreur`, le job **continue** sur les suivants.
- Candidat orange sans prix ≤ date BL → reste `rouge`.
- `job_id` inconnu (ex. app redémarrée) → `progress` renvoie « job introuvable » ; la page
  nettoie son `localStorage`.
- Refuser un orange ne supprime jamais la ligne : elle repasse `rouge` (à compléter).

---

## 8. Critères d'acceptation Temps 3

1. Le tableau `/resolution` n'affiche que les lignes rouge/orange, avec compteurs (à compléter
   / à confirmer / auto-validées) et barre de progression.
2. Une ligne non résolue par code mais dont la désignation correspond à une entrée du
   référentiel ressort en **orange** avec candidat + score ; auto-validée si score ≥ 0,95 et
   dosage concordant.
3. La normalisation gère accents, ponctuation, abréviations et dosage/contenance.
4. L'édition inline recalcule le PA net (formule UG §3.3) et la sauvegarde persiste dans
   `retro_lignes` ; accepter/refuser un orange marche.
5. « Re-rapprocher » fait passer en orange/résolu des lignes rouges après ajout des factures
   labo correspondantes, sans appel API.
6. Une ingestion (labo ou LGO) **continue côté serveur** si on change d'onglet ; en revenant
   sur la page d'import, la progression est **toujours là** et se met à jour jusqu'à la fin.
7. Le cœur (normalisation, score, matching, recalcul, rematch, jobs) est couvert par des tests
   unitaires verts, sans appel API.
