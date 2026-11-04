# trail-mania

La connexion Google Drive est proposée au démarrage tant qu'aucune autorisation n'a été enregistrée. Après connexion, l'application ouvre directement le calendrier. « Continuer sans connexion » permet d'utiliser les séances locales ; l'écran sera proposé au lancement suivant.

L'intégration Google est native Android et nécessite un APK reconstruit : le client standard de `flet run` ne contient pas l'extension locale `trail-mania-drive`. Sur ordinateur, on peut continuer sans connexion.

Configuration Google Drive pour Android :

1. Dans le même projet Google Cloud, activer Google Drive API, configurer l'audience OAuth et ajouter son compte comme utilisateur de test. Déclarer l'autorisation `https://www.googleapis.com/auth/drive.appdata`.
2. Créer un client OAuth **Android**, avec le package de l'APK (actuellement `com.flet.trail_mania`) et l'empreinte SHA-1 du certificat qui signe cet APK. Une autre clé de signature nécessite une configuration correspondante.
3. Créer aussi un client OAuth **Application Web**, utilisé comme `serverClientId` par le SDK Android. Aucun serveur, URI de redirection Web ni secret client n'est utilisé par cette intégration native.
4. Copier `src/assets/google_drive.example.json` vers `src/assets/google_drive.json`, puis remplacer `web_client_id` par l'identifiant du client **Web**. Ce fichier local est ignoré par Git et embarqué lors du build. Il contient uniquement un identifiant public, jamais de secret client, mot de passe ou jeton. La variable `TRAIL_MANIA_GOOGLE_WEB_CLIENT_ID` permet aussi de fournir cet identifiant pendant l'exécution Python ; les variables du PC ne sont pas automatiquement transmises au téléphone.
5. Lancer `uv sync`, puis `uv run flet build apk`. Installer et tester l'APK sur un téléphone Android avec les services Google Play.

Sur Windows, Flutter peut demander d'activer le mode développeur de Windows pour créer les liens symboliques nécessaires aux extensions.

Le SDK Google conserve la session native et gère l'obtention des jetons d'accès. L'application conserve le compte autorisé et son autorisation dans le stockage sécurisé Android, après le consentement Drive et une écriture réussie uniquement. Aucun jeton n'est écrit dans SQLite, les assets ou un fichier JSON. Le démarrage lit cet état local et reste utilisable hors ligne ; la révocation distante sera détectée lors d'une prochaine demande de jeton. `GoogleDriveAuth.access_token()` permet de demander un jeton au SDK et signale si une nouvelle autorisation est nécessaire. Une désinstallation, une suppression des données ou une révocation peut nécessiter de reconnecter le compte.

Documentation : [configuration Android Google Sign-In](https://pub.dev/packages/google_sign_in_android), [dossier privé Drive](https://developers.google.com/workspace/drive/api/guides/appdata).

`trail_mania.drive_backup.backup_database_to_drive(auth)` crée une copie cohérente de SQLite, l'envoie dans le dossier privé de l'application sur Google Drive, puis conserve les 20 sauvegardes les plus récentes selon leur date de création Drive. Le fichier porte le nom `trail_mania_YYYY_MM_DD_HH_MM_SS_mmm.db`, en heure locale avec trois chiffres pour les millisecondes. La base locale n'est ni renommée ni déplacée, et la copie temporaire est supprimée après l'opération. Les autres fichiers Drive ne sont pas comptés : seules les sauvegardes marquées par cette fonction sont concernées.

Depuis un gestionnaire asynchrone Flet :

```python
from trail_mania.drive_backup import backup_database_to_drive

result = await backup_database_to_drive(page.session.store.get("drive_auth"))
```

Le résultat contient `file_id`, `filename` et `deleted_file_ids`. Les appels simultanés dans le même processus sont exécutés successivement sans bloquer l'interface. Aucune ancienne sauvegarde n'est supprimée si l'envoi échoue ou si la liste complète ne peut pas être obtenue. Si l'envoi réussit mais que le nettoyage échoue, `DriveBackupRetentionError.result` contient la sauvegarde envoyée et les suppressions déjà effectuées.

`AutomaticDriveBackup` déclenche un envoi après une nouvelle connexion Google Drive et après chaque ajout, modification ou suppression de séance validé dans `session_repository`. Les notifications partent après commit et fermeture de la connexion SQLite ; les lectures, les transactions échouées et la suppression d'une séance déjà absente ne déclenchent pas d'envoi. Sans connexion Google, les séances restent utilisables localement et les demandes sont conservées. Les envois s'exécutent en arrière-plan, un par un.

Les demandes inachevées sont enregistrées atomiquement dans `drive_backup_state.json`, à côté de la base, sans identifiants ni jetons Google. Une connexion restaurée au démarrage reprend les demandes en attente. Après un échec temporaire, la même tâche retente automatiquement après 15, 30, 60, 120, 240 puis 300 secondes au maximum, même sans nouvelle modification. Le retour d'une connexion réseau et le retour de l'application au premier plan réveillent l'attente pour réessayer plus tôt. Une interface Wi-Fi disponible ne garantit pas l'accès à Internet : les erreurs Drive continuent donc d'être prises en charge. Un seul message est affiché par série d'échecs. Si le consentement Google doit être renouvelé, les demandes restent conservées et un message demande de reconnecter le compte.

`prune_drive_backups(auth)` relance uniquement le nettoyage des anciennes copies. Si l'envoi a réussi mais que ce nettoyage échoue, l'application mémorise cette étape et la retente sans renvoyer la base. Les demandes de sauvegarde conservent leur nombre, mais les copies sont créées lors des tentatives : elles contiennent la base courante, pas un historique local de chaque modification hors ligne. Lorsque l'application est arrêtée par Android, les tentatives reprendront au prochain lancement ; aucun service de sauvegarde ne tourne avec l'application complètement fermée.

La base SQLite `trail_mania.db` est initialisée avec SQLAlchemy au démarrage. Elle est conservée dans `FLET_APP_STORAGE_DATA` (stockage persistant de Flet). En exécution Python directe, le dossier utilisé est `.flet/storage/data/` à la racine du projet.

Les modèles sont définis dans `src/trail_mania/models.py` : `Session`, `SessionSortieLongue`, `SessionEnduranceFondamentale`, `SessionEnduranceActive`, `SessionSeuil` et `SessionVO2max`. Les tables manquantes sont créées au démarrage, sans ajout de données. Les anciennes colonnes `inclination` entières sont automatiquement converties en nombres à une décimale et les colonnes `weather` deviennent nullables, en conservant les données.

Chaque détail possède un `session_id` obligatoire et unique dans sa table, lié à `sessions.id`. La suppression de la session supprime ses détails. Les choix autorisés et les champs obligatoires sont contrôlés par la base. `dynamic_type`, `elevation_gain`, `inclination`, `temperature` et `weather` sont facultatifs dans toutes les tables de détails ; `comment` peut contenir une chaîne vide.

Les tables `sessions_seuil` et `sessions_vo2max` contiennent respectivement jusqu'à trois et six répétitions. Pour le seuil, seule la première vitesse ON et les premières fréquences cardiaques sont obligatoires. Pour VO2max, les quatre premières vitesses ON, les trois premières vitesses OFF et les fréquences cardiaques des quatre premières répétitions sont obligatoires. Les autres vitesses et fréquences cardiaques sont facultatives. Les vitesses `velocity_ON_*` et `velocity_OFF_*` sont des `float` sans limite à une décimale. `duration_ON` est obligatoire et `duration_OFF` est facultatif ; tous deux sont des nombres à une décimale, lus comme `Decimal`, distincts des durées de zones en `timedelta`.

`distance`, `velocity`, `inclination` et `RPE` sont des nombres `NUMERIC` à une décimale, lus comme `Decimal` en Python. Les valeurs avec plus d'une décimale sont refusées. `date` utilise `datetime.date`. Les durées `Z1` à `Z5` utilisent `datetime.timedelta`, avec une précision à la seconde et un stockage en secondes entières, permettant un affichage `HH:MM:SS`, y compris au-delà de 24 heures. Pour convertir la valeur d'un `ZoneDurationInput`, utiliser `timedelta(seconds=champ.value)` après validation du champ.

Pour accéder aux données, utiliser `sqlalchemy.orm.Session` avec le moteur retourné par `create_database_engine()` dans `trail_mania.database`, puis fermer la session et libérer le moteur avec `engine.dispose()` lorsque son utilisation est terminée. Le modèle métier `trail_mania.models.Session` est distinct de la session de connexion SQLAlchemy.

Le bouton « Ajouter » valide les champs puis enregistre la session et ses détails dans une seule transaction via `trail_mania.session_repository.create_session`. « Muscu jambes » crée uniquement une entrée dans `sessions`. Les champs masqués et les répétitions inutilisées sont enregistrés à `NULL` : pour le seuil continu, seule la première vitesse ON et les premières fréquences cardiaques sont renseignées ; pour VO2max, seules les répétitions choisies et les récupérations intermédiaires sont renseignées. Les durées ON/OFF sont enregistrées en minutes, les vitesses en km/h et les zones en secondes.

Les champs non nullables sont obligatoires. Un champ numérique facultatif peut être vide, mais une saisie invalide bloque l'enregistrement. Si une écriture échoue, aucune entrée partielle n'est conservée et le formulaire reste disponible pour réessayer. Après succès, un message confirme l'enregistrement et l'application revient aux choix de sessions.

Le parcours d'ajout est réparti entre `AddSessionView` (navigation et enregistrement) et les contrôles de `src/trail_mania/views/add_session/` : `SessionForm` gère les choix progressifs et `SessionDetailsForm` construit et valide les champs de mesure. `SessionConfiguration` décrit une combinaison valide de terrain, pente, mouvement et format. Les contrôles restent en mémoire lors d'un changement d'onglet ; un retour aux choix de sessions abandonne le formulaire courant. Les événements provenant d'un ancien formulaire ne peuvent pas enregistrer de session.

Les choix métier et leurs libellés sont centralisés dans `session_types.py`, partagé avec les modèles SQLAlchemy. Les sélecteurs héritent de `ChoiceSelector`, qui gère la sélection unique, la remise à zéro et la synchronisation avec Flet. La validation et la conversion des mesures utilisent les exigences exposées par `session_repository.get_detail_fields`, sans introspection SQLAlchemy dans les vues.

La consultation des sessions est répartie entre `SessionsView` (navigation) et les contrôles de `views/sessions/` : `SessionList` coordonne le chargement et le filtrage en mémoire, `SessionFilters` conserve les choix et `SessionTable` gère le rendu, les largeurs mesurées et le défilement avec en-tête fixe. Les définitions de colonnes dans `_columns.py` regroupent leur ordre, leur formatage, leurs unités et leur alignement. Le sélecteur de types `components/session_type_picker.py` est partagé avec l'ajout de session.

`session_repository.get_sessions` charge une famille de course en une seule requête, par date puis identifiant décroissants. Les mesures sont retournées sous forme de `EnduranceSession` ou `IntervalSession` immuables définis dans `session_records.py`, sans objets ORM. Un changement de filtre ne relit pas la base ; un retour sur l'onglet actualise les données en conservant les choix. Le retour au sélecteur abandonne ces choix. Le calendrier et les tableaux utilisent la même déduction du format des répétitions, qui distingue une vitesse nulle d'une mesure absente.

La liste et le calendrier partagent le parcours de consultation via `views/sessions/_session_navigation.py` : détail, modification, puis retour à la vue d'origine. `SessionDetailView` compose les sections de `_detail_sections.py` et le graphique de `_zone_chart.py`. Le formatage des mesures est partagé avec les tableaux et les statistiques dans `views/_formatting.py`, sans dépendance à l'ordre des colonnes. Les types `RunningSession` et `SessionRecord` décrivent les familles de mesures acceptées.

La modification réutilise `SessionForm` et `SessionDetailsForm` avec `initial_session`. Le formulaire conserve les valeurs masquées et verrouille le terrain, la pente, le mouvement et le format. `session_repository.update_session` contrôle également ces invariants et modifie la date et les mesures dans une seule transaction. La suppression utilise l'identifiant persistant et supprime les détails en cascade. Les confirmations et les écrans quittés ignorent leurs anciens événements. Les changements non enregistrés nécessitent un choix avant de quitter l'éditeur.

Après une modification ou une suppression, la liste est reconstruite en conservant les filtres ; le calendrier retrouve son mode et sa période. Un changement d'onglet pendant la consultation ou l'édition diffère cette actualisation jusqu'au retour à la vue d'origine, sans modifier les contrôles détachés ni perdre la saisie en cours.

Les statistiques sont réparties entre `views/statistics/statistics_view.py` (période et actualisation), `_table.py` (colonnes et rendu) et `session_statistics.py` (calculs indépendants de Flet et de la base). `session_repository.get_running_sessions_between` charge toutes les familles de course d'une période inclusive en une requête, sans préparer les descriptions du calendrier. Les sélections du mois et de la semaine ISO restent indépendantes ; le retour sur l'onglet recharge les données en conservant la période et le tableau.

Les cumuls conservent leur précision jusqu'à l'affichage. La durée d'endurance est déduite de la distance et de la vitesse moyenne ; pour les intervalles, la distance utilise les vitesses ON renseignées et la durée utilise le nombre de répétitions du format. Les récupérations sont exclues de ces deux mesures. Le dénivelé enregistré, y compris zéro, est prioritaire sur l'estimation par distance et inclinaison. Les pourcentages de zones utilisent les durées cumulées de Z1 à Z5, partagées avec les vues de sessions. Le total général additionne les cumuls par famille sans recalculer les séances ni moyenner les pourcentages.

Pour lancer les tests depuis la racine du projet avec PowerShell :

```powershell
$env:PYTHONPATH = "src"
uv run python -m unittest discover -s tests -v
```
