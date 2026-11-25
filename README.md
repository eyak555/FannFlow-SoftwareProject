# FannFlow

Socle Django commun de la plateforme de gestion des événements culturels.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Structure

- `fannflow/` : configuration globale du projet.
- `core/` : gabarit, charte graphique, navigation, composants réutilisables et routes CRUD génériques.
- `users_teams/` : Module 1 — utilisateurs et équipes.
- `events_program/` : Module 2 — événements, activités et intervenants.
- `registration_access/` : Module 3 — inscriptions, billets, présences et points d’accès.
- `resources_operations/` : Module 4 — lieux, ressources et allocations.
- `sponsors_finance/` : Module 5 — sponsors, financements et budgets.
- `communication_media/` : Module 6 — communication, médias, dossiers de presse et publications.

## Inscriptions, billets et QR

- La création d’une inscription émet automatiquement un billet associé. Jusqu’à l’intégration des tarifs des événements, son prix est fixé à `0,00` et sa catégorie reprend le type de billet reconnu (`Standard`, `VIP` ou `Groupe` ; sinon `Standard`).
- Le billet reste « En attente » tant que l’inscription n’est pas confirmée. Un billet payant reste aussi en attente jusqu’au paiement.
- Le type de billet de l’inscription propose les choix Standard, VIP et Groupe. Le code lisible du billet (`FF-000001`) est généré à partir de son identifiant auto-incrémenté ; le QR SVG est généré à partir de ce code et s’affiche sur la fiche uniquement si le billet est disponible.
- Quand le module Événements fournira les tarifs, remplacer le prix provisoire dans `registration_access/services.py`.
- Le statut de paiement est encore géré manuellement : aucun paiement en ligne ni remboursement bancaire n’est intégré.
- Une entrée est enregistrée avec le code QR et un point d’accès du même événement. Le billet devient alors « Utilisé » et ne peut pas servir à une seconde entrée ; la sortie est enregistrée sur cette présence et libère une place à la capacité du point.
- La capacité d’un point d’accès est le nombre maximal de personnes présentes simultanément. Une sortie déjà enregistrée, une entrée effectuée, un billet consommé ou un point d’accès avec des présences liées ne peuvent pas être supprimés ou déplacés au moyen du CRUD.
- Les présences existantes sont conservées lors de la migration : chaque ancien nom de porte devient un point d’accès pour l’événement concerné. Son lieu est « À préciser » et sa capacité est initialisée au nombre de personnes encore présentes (au minimum 1) ; vérifiez et ajustez ces points après migration.
- Le module Événements ne contient pas encore de modèle `Event`. Les deux champs `event_id` restent donc des identifiants numériques temporaires ; une vraie clé étrangère sera à ajouter lors de l’intégration des modules.
- L’écran de contrôle permet de saisir le code billet lu par un scanner externe ; l’accès caméra et la lecture automatique ne sont pas inclus.

## Ajouter un CRUD dans une branche

1. Depuis `main`, exécutez `git pull origin main`, puis créez `git checkout -b module-NOM-MODULE`.
2. Ajoutez les modèles Django dans `<application>/models.py` et créez les migrations.
3. Ajoutez les formulaires du module en héritant de `core.forms.FannFlowModelForm`.
4. Remplacez les fonctions placeholder de `<application>/views.py` par les vues réelles.
5. Déclarez les nouvelles routes avant `crud_patterns` dans `<application>/urls.py`.
6. Étendez les gabarits `core/layouts/list.html`, `form.html`, `detail.html` et `confirm_delete.html`.
7. Testez avec `python manage.py makemigrations`, `python manage.py migrate` et `python manage.py test`.
8. Ouvrez une Pull Request vers `main` sans modifier les fichiers du socle sans accord de l’équipe.

## Choix simples d’ambiguïté

- Le cahier indique « 24 tables » puis une répartition de 26 tables : les 26 entités nominatives détaillées sont retenues.
- Les modules sont implémentés progressivement dans leurs branches ; le CRUD Inscriptions et Accès comprend les inscriptions, billets, présences et points d’accès.
- Les polices Roboto, Inter et JetBrains Mono sont chargées depuis Google Fonts avec un repli sans-serif du navigateur.
- L’écran de connexion présente les options prévues, mais aucune authentification réelle n’est activée dans le socle.
