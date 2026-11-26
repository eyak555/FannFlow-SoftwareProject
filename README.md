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

- La création d’une inscription émet automatiquement un billet associé. Les catégories sont Standard et VIP, et chacune utilise le tarif configuré sur l’événement ; pour un ancien identifiant sans événement associé, le tarif provisoire est de `10,00`.
- Le billet reste « En attente » tant que l’inscription n’est pas confirmée. Un billet payant reste aussi en attente jusqu’au paiement.
- Le type de billet de l’inscription propose uniquement Standard et VIP. Le code lisible du billet (`FF-000001`) est généré à partir de son identifiant auto-incrémenté ; le QR SVG est généré à partir de ce code et s’affiche sur la fiche uniquement si le billet est disponible.
- Le statut de paiement est encore géré manuellement : aucun paiement en ligne ni remboursement bancaire n’est intégré.
- Une entrée est enregistrée avec le code QR et un point d’accès du même événement. Le billet devient alors « Utilisé » et ne peut pas servir à une seconde entrée ; la sortie est enregistrée sur cette présence et libère une place à la capacité du point.
- La capacité d’un point d’accès est le nombre maximal de personnes présentes simultanément. Une sortie déjà enregistrée, une entrée effectuée, un billet consommé ou un point d’accès avec des présences liées ne peuvent pas être supprimés ou déplacés au moyen du CRUD.
- Les présences existantes sont conservées lors de la migration : chaque ancien nom de porte devient un point d’accès pour l’événement concerné. Son lieu est « À préciser » et sa capacité est initialisée au nombre de personnes encore présentes (au minimum 1) ; vérifiez et ajustez ces points après migration.
- Le module Événements fournit les événements, leurs activités et intervenants. Le responsable est un compte actif de directeur, organisateur ou administrateur du module `users_teams`. Les inscriptions et points d’accès historiques conservent leur identifiant numérique `event_id` pour compatibilité ; les nouveaux événements réutilisent leur clé primaire comme identifiant d’événement.
- La fiche publique d’un événement publié permet de demander une inscription. Les prix Standard et VIP sont exprimés en dinars tunisiens (DT) ; le billet reprend le prix correspondant configuré sur l’événement. Les anciens identifiants sans événement correspondant conservent le tarif provisoire de 10,00 DT.
- L’écran de contrôle permet de saisir le code billet lu par un scanner externe ; l’accès caméra et la lecture automatique ne sont pas inclus.

## Événements et programme

- Le tableau de bord Événements est filtrable par catégorie, statut, ville/lieu et dates. Il présente des graphiques calculés à partir des événements et inscriptions confirmées, les entrées réellement enregistrées, le taux de remplissage, une carte des événements publiés à venir et un calendrier interactif par jour, semaine ou mois avec horaires et lieux. Les organisateurs/directeurs voient leurs événements affectés ; les administrateurs voient l’ensemble.
- Les événements ont un statut de publication (brouillon, publié ou annulé) et un état de cycle de vie calculé à partir de leurs dates. Seuls les événements publiés sont visibles dans le catalogue public.
- Les événements ne peuvent pas être supprimés tant que des inscriptions ou points d’accès les référencent ; ils peuvent être annulés ou dépubliés à la place.
- Les activités sont datées à l’intérieur de leur événement et peuvent être liées à plusieurs intervenants.
- Les événements utilisent des illustrations SVG locales par catégorie et peuvent recevoir une image JPG, PNG ou WEBP (5 Mo maximum). Les images importées sont stockées sous `MEDIA_ROOT/events/<categorie>/` et supprimées avec l’événement ou après leur remplacement.
- Le formulaire d’événement permet de choisir un lieu enregistré ou de rechercher/sélectionner un emplacement tunisien sur une carte OpenStreetMap. Les coordonnées vérifiées créent un lieu associé à l’événement ; si Leaflet ou le géocodage est indisponible, la saisie textuelle reste possible. L’attribution OpenStreetMap reste visible.
- La recherche de lieux passe par le proxy Django, sans autocomplétion, avec cache et limitation des requêtes. En production, configurez `FANNFLOW_NOMINATIM_USER_AGENT` avec un identifiant et un contact de l’application, ainsi qu’un cache partagé pour appliquer la limite de requêtes entre plusieurs workers. Les URL peuvent être configurées avec `FANNFLOW_NOMINATIM_API_URL` et `FANNFLOW_OSM_TILE_URL`.
- Le catalogue public utilise une pagination Django de neuf événements par page. Recherche, catégorie, lieu, période, état et tri sont appliqués en base et conservés lors de la navigation.
- L’organisateur peut définir l’âge minimum et/ou maximum accepté. La condition est affichée sur la fiche publique et contrôlée à l’inscription d’après la date de naissance du profil ; pour vérifier une restriction d’âge, la date de naissance est obligatoire. Le billet VIP a son propre prix.

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
