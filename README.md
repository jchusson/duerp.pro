# DUERP.pro — Logiciel de gestion du Document Unique

Application web multi-clients de gestion du **Document Unique d'Évaluation des Risques Professionnels** (DUERP), conforme au format JHC Consulting.

## Fonctionnalités

- **Multi-clients** : chaque client (entreprise) a ses propres unités de travail, risques et plan d'action.
- **Multi-utilisateurs** : plusieurs personnes par client, rôles `admin` (gestion des utilisateurs) et `user`.
- **Cotation simple** : Fréquence (1-4) × Gravité (1, 2, 4, 8) × Maîtrise (0,5 / 1 / 2) = criticité F×G×M colorée (vert ≤ 3, orange 4-15, rouge ≥ 16).
- **Format du document** repris du modèle JHC : page de garde, cadre légal, méthodologie, grille de cotation, tableaux par unité de travail, plan d'action.
- **Exports** :
  - PDF du Document Unique complet (avec plan d'action)
  - Excel du Document Unique complet (avec plan d'action)
  - PDF du plan d'action seul
  - Excel du plan d'action seul
- **Charte graphique** duerp.pro (rouge `#8B1D1D`, bleu `#1B2F5E`, crème `#F5F0E8`) + logo JHC.

## Installation

```bash
pip install -r requirements.txt
python app.py
```

L'application démarre sur `http://localhost:5000`.

## Compte de démarrage

À la première initialisation de la base (`python init_db.py`), un compte super-administrateur est créé :

- email : `admin@duerp.pro`
- mot de passe : `changeme` (à changer immédiatement)

Les mots de passe sont stockés hachés (PBKDF2-SHA256, salt aléatoire).

## Structure

- `app.py` — serveur Flask (routes, API, exports)
- `database.py` — schéma et accès SQLite (`duerp.db`)
- `init_db.py` — initialisation et compte admin
- `exports.py` — génération PDF (ReportLab) et Excel (openpyxl)
- `templates/`, `static/` — interface
- `assets/logo-jhc.png` — logo JHC

## Modèle de cotation

| Fréquence | Gravité | Maîtrise |
|---|---|---|
| 1 Faible | 1 Mineure | 0,5 Bonne |
| 2 Ponctuelle | 2 Significative | 1 Moyenne |
| 3 Moyenne | 4 Critique | 2 Aucune |
| 4 Élevée | 8 Vitale | |

**Criticité = F × G × M** — vert ≤ 3 : aucune action complémentaire ; orange 4 à 15 : action de communication / consigne ; rouge ≥ 16 : action palliative rapide + solution durable.
