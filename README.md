# trail-mania

La base SQLite `trail_mania.db` est initialisée avec SQLAlchemy au démarrage. Elle est conservée dans `FLET_APP_STORAGE_DATA` (stockage persistant de Flet). En exécution Python directe, le dossier utilisé est `.flet/storage/data/` à la racine du projet.

Les modèles sont définis dans `src/trail_mania/models.py` : `Session`, `SessionSortieLongue`, `SessionEnduranceFondamentale`, `SessionEnduranceActive`, `SessionSeuil` et `SessionVO2max`. Les tables manquantes sont créées au démarrage, sans ajout de données. Les anciennes colonnes `inclination` entières sont automatiquement converties en nombres à une décimale et les colonnes `weather` deviennent nullables, en conservant les données.

Chaque détail possède un `session_id` obligatoire et unique dans sa table, lié à `sessions.id`. La suppression de la session supprime ses détails. Les choix autorisés et les champs obligatoires sont contrôlés par la base. `dynamic_type`, `elevation_gain`, `inclination`, `temperature` et `weather` sont facultatifs dans toutes les tables de détails ; `comment` peut contenir une chaîne vide.

Les tables `sessions_seuil` et `sessions_vo2max` contiennent respectivement jusqu'à trois et six répétitions. Pour le seuil, seule la première vitesse ON et les premières fréquences cardiaques sont obligatoires. Pour VO2max, les quatre premières vitesses ON, les trois premières vitesses OFF et les fréquences cardiaques des quatre premières répétitions sont obligatoires. Les autres vitesses et fréquences cardiaques sont facultatives. Les vitesses `velocity_ON_*` et `velocity_OFF_*` sont des `float` sans limite à une décimale. `duration_ON` est obligatoire et `duration_OFF` est facultatif ; tous deux sont des nombres à une décimale, lus comme `Decimal`, distincts des durées de zones en `timedelta`.

`distance`, `velocity`, `inclination` et `RPE` sont des nombres `NUMERIC` à une décimale, lus comme `Decimal` en Python. Les valeurs avec plus d'une décimale sont refusées. `date` utilise `datetime.date`. Les durées `Z1` à `Z5` utilisent `datetime.timedelta`, avec une précision à la seconde et un stockage en secondes entières, permettant un affichage `HH:MM:SS`, y compris au-delà de 24 heures. Pour convertir la valeur d'un `ZoneDurationInput`, utiliser `timedelta(seconds=champ.value)` après validation du champ.

Pour accéder aux données, utiliser `sqlalchemy.orm.Session` avec le moteur retourné par `create_database_engine()` dans `trail_mania.database`, puis fermer la session et libérer le moteur avec `engine.dispose()` lorsque son utilisation est terminée. Le modèle métier `trail_mania.models.Session` est distinct de la session de connexion SQLAlchemy.

Le bouton « Ajouter » valide les champs puis enregistre la session et ses détails dans une seule transaction via `trail_mania.session_repository.create_session`. « Muscu jambes » crée uniquement une entrée dans `sessions`. Les champs masqués et les répétitions inutilisées sont enregistrés à `NULL` : pour le seuil continu, seule la première vitesse ON et les premières fréquences cardiaques sont renseignées ; pour VO2max, seules les répétitions choisies et les récupérations intermédiaires sont renseignées. Les durées ON/OFF sont enregistrées en minutes, les vitesses en km/h et les zones en secondes.

Les champs non nullables sont obligatoires. Un champ numérique facultatif peut être vide, mais une saisie invalide bloque l'enregistrement. Si une écriture échoue, aucune entrée partielle n'est conservée et le formulaire reste disponible pour réessayer. Après succès, un message confirme l'enregistrement et l'application revient aux choix de sessions.

Le parcours d'ajout est réparti entre `AddSessionView` (navigation et enregistrement) et les contrôles de `src/trail_mania/views/add_session/` : `SessionTypePicker` affiche les types de sessions, `SessionForm` gère les choix progressifs et `SessionDetailsForm` construit et valide les champs de mesure. `SessionConfiguration` décrit une combinaison valide de terrain, pente, mouvement et format. Les contrôles restent en mémoire lors d'un changement d'onglet ; un retour aux choix de sessions abandonne le formulaire courant. Les événements provenant d'un ancien formulaire ne peuvent pas enregistrer de session.

Les choix métier et leurs libellés sont centralisés dans `session_types.py`, partagé avec les modèles SQLAlchemy. Les sélecteurs héritent de `ChoiceSelector`, qui gère la sélection unique, la remise à zéro et la synchronisation avec Flet. La validation et la conversion des mesures utilisent les exigences exposées par `session_repository.get_detail_fields`, sans introspection SQLAlchemy dans les vues.

Pour lancer les tests depuis la racine du projet avec PowerShell :

```powershell
$env:PYTHONPATH = "src"
uv run python -m unittest discover -s tests -v
```
