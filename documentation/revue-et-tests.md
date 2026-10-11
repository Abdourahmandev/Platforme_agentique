# Revue et bilan de migration

État au 11 octobre 2026. Le candidat Docker est installé et testé sur le PC de référence. **Le bot habituel fonctionne encore avec l'installation Windows. La migration de production n'est pas déclarée terminée.**

Décision complémentaire : Asia conserve le bot actuel. Son token a été validé auprès de Telegram et copié dans le runtime privé sans activer OpenClaw. Seuls les tokens Développement et Recherche restent à fournir. Les tests de garde vérifient que ce choix ne permet pas à l'initialiseur de démarrer un second consommateur du bot actuel ; les résultats Telegram historiques ci-dessous précèdent cette préparation.

## Changements réalisés

- Installation des images officielles OpenClaw 2026.10.1, LiteLLM 1.104.1, PostgreSQL 17.11 et Speaches CPU, figées par empreinte ; aucune image de l'ancienne application construite.
- Copie logique de PostgreSQL vers un volume distinct ; 91 tables restaurées. Conservation du sel LiteLLM et de la comptabilité historique.
- Création des agents Asia, Développement et Recherche, avec espaces, sessions et clés propres ; enveloppe de test réduite et refus des droits administrateur.
- Blocage des huit clés héritées dans le candidat ; clé Windows toujours valide en production et refusée dans le candidat.
- Configuration de la transcription locale pour les trois agents et de la synthèse vocale Microsoft en français.
- Création des scripts de migration, de tests, de sauvegarde Docker, de préparation des bots et d'un client WebSocket de référence pour la future application.
- Documentation de l'ensemble du projet dans ce dossier et contrôles CI enrichis.

## Défauts trouvés et corrigés

| Défaut observé | Correction et preuve |
| --- | --- |
| Copie de `.git` dans l'ancienne sauvegarde, avec fichiers en lecture seule empêchant le nettoyage | Exclusion de `.git`, nettoyage borné au dossier temporaire et test avec fichier en lecture seule |
| Déchiffrement d'une archive tronquée pouvant conserver du contenu non authentifié | Contrôle de longueur/fin de fichier, suppression du résultat non authentifié, refus d'écrasement ; tests corruption et troncature |
| Permissions POSIX OpenClaw incompatibles avec un montage de l'état sur Windows | Volume Linux, initialisation par copie explicite, permissions 700/600 et propriétaire du service |
| PowerShell pouvait absorber l'option Docker `-d` comme paramètre `Debug` | Wrapper simple transmettant les arguments Docker ; démarrage détaché vérifié |
| Dérive entre exemples documentaires et schéma OpenClaw installé | Validation contre le schéma de l'image : agents, audio, TTS et protocole WebSocket 4 |
| Absence de limitation des tentatives d'authentification Gateway | Limitation configurée ; audit intégré ensuite sans alerte critique ni avertissement |
| Fichiers temporaires d'une restauration appartenant à root | Lecture/écriture par le compte du service, permissions privées et nettoyage après restauration |
| Risque de second budget porté par les clés copiées depuis Windows | Quarantaine des clés héritées dans le candidat, test de refus et contrôle de la clé originale sur Windows |
| Course possible lors de la reconnexion du client WebSocket de test | Requêtes en attente liées à chaque connexion ; reconnexion et historique testés |
| Arrêt Docker plus court que le drainage maximal de la Gateway | Délai d'arrêt de six minutes et test d'arrêt/recréation avec volumes conservés |

Le premier essai audio pendant un redémarrage a échoué : le stockage OpenClaw était en maintenance. L'essai a été relancé séquentiellement après l'état `healthy` et a réussi pour les trois agents. Ce résultat motive la règle d'exploitation : attendre la disponibilité, puis effectuer les changements de configuration un par un.

## Tests exécutés

| Étape | Résultat observé | Limite de la preuve |
| --- | --- | --- |
| Ancienne application | 10 tests Node réussis ; compilation réussie ; audit npm de production sans vulnérabilité signalée | Ne constitue pas un audit exhaustif des dépendances des images |
| Sauvegarde, routage, infrastructure et reprise Telegram | 13 tests Python réussis | Fixtures déterministes et contrôles de frontières de déploiement, sans fournisseur externe |
| Sauvegarde Windows | Archive chiffrée vérifiée, SQLite intègre, 38 sessions OpenCode, PostgreSQL restauré dans une base temporaire de 91 tables | La reprise sur un PC neuf n'a pas été simulée |
| Migration PostgreSQL | 91 tables dans la cible distincte ; rôle applicatif non superutilisateur | Aucun fichier de cluster Windows monté dans Linux |
| Accès LiteLLM/OpenClaw | Absence/mauvaise clé refusée ; droits administrateur refusés aux trois agents ; modèle inconnu refusé | Interfaces locales, pas d'essai depuis le téléphone |
| Catalogue | 34 routes visibles pour chaque clé d'agent | Les 34 endpoints n'ont pas tous été réévalués en réel pendant cette migration ; voir validations historiques |
| Budget individuel et partagé | Clé épuisée refusée ; deux clés encore disponibles refusées par le budget de leur équipe épuisée | Dépense de fixture ; plafonds non instantanés sous concurrence |
| Trois agents | Réponses avec la bonne identité ; dépenses attribuées à chaque clé | Requêtes artificielles courtes |
| Espaces et sessions | Chaque agent lit/écrit son marqueur ; listes limitées à son agent ; historique voisin interdit ; marqueur voisin non divulgué ; shell indisponible | Politique dans un processus partagé, pas une frontière multi-utilisateur hostile ; le test négatif de fichier inclut le comportement du modèle |
| Image | Carré rouge envoyé à OpenClaw, réponse correcte via LiteLLM | Ne valide pas encore la chaîne Telegram photo |
| Pannes fournisseurs | Routeur LiteLLM réel, fournisseurs simulés, six cas réussis : texte, images Auto/manuelles, PDF, JSON strict, panne totale bornée | Simulation isolée sans réseau ; pas de panne infligée aux comptes fournisseurs |
| API future application | Protocole 4, appairage, liste d'agents/sessions, streaming, idempotence, annulation, historique après reconnexion, refus d'écriture admin | Crash en plein appel d'outil et durée de déduplication non éprouvés |
| Transcription | Fixture vocale synthétique comprise par chacun des trois agents avec Speaches local | Réception effective d'un vocal Telegram à tester |
| Synthèse | MP3 français généré par Microsoft ; contenu vérifié par transcription locale | Service externe sans garantie de disponibilité ; livraison Telegram non testée |
| Redémarrage PostgreSQL | LiteLLM se reconnecte et conserve les comptes | Test de redémarrage propre, pas corruption du disque |
| Retour arrière / recréation | Candidat arrêté, Windows toujours sain, quatre conteneurs recréés ; espaces, comptes, dépenses, sessions et appareil conservés | Pas de redémarrage complet de Windows |
| Sauvegarde Docker | Sauvegarde native OpenClaw vérifiée et restaurée dans un emplacement distinct ; dump PostgreSQL restauré, 91 tables | Pas de restauration par-dessus un environnement actif |
| Sécurité OpenClaw | 0 critique, 0 avertissement dans l'audit intégré après correction | Deux informations sur les frontières de confiance ; ce n'est pas un test d'intrusion |
| Telegram | Schéma des trois comptes et associations validé sans activation | Tokens absents ; aucun nouveau bot testé ni message envoyé |

Les rapports détaillés avec chemins locaux restent dans `%LOCALAPPDATA%\AsiaDocker` : `platform-test-result.json`, `gateway-test-result.json`, `isolation-test-result.json`, `team-budget-test-result.json`, `audio-test-result.json`, `tts-test-result.json`, `lifecycle-test-result.json`, `docker-backup-result.json` et `key-quarantine-result.json`. Ils ne sont pas copiés aveuglément dans Git. Les messages utilisés pour les essais sont artificiels.

Point de reprise Docker vérifié à 20:02 UTC : `D:\AsiaBackups\docker-20261011T200200-570803f5.aes`, 46 fichiers vérifiés, restauration OpenClaw réussie et 91 tables PostgreSQL restaurées. Point de reprise Windows : `D:\AsiaBackups\asia-20261011T190807-c0f5ef.aes`. Ces archives sont locales et chiffrées, pas déposées sur GitHub. Le rapport privé indique le point le plus récent si une sauvegarde supplémentaire a été faite.

## Revue de robustesse : priorités restantes

| Priorité | Observation | Action et critère de réussite |
| --- | --- | --- |
| Avant bascule | Asia réutilise le bot actuel ; deux bots restent à créer/configurer | Recevoir les tokens Développement/Recherche par saisie locale protégée ; transférer Asia avec un seul consommateur ; tester texte, photo, vocal, refus d'un correspondant non autorisé et absence de mélange des conversations |
| Avant bascule | PC de 12 Go, moins de 1 Go libre observé avec Windows et Docker en parallèle | Mesurer au repos et pendant deux tâches avec audio ; arrêter les services remplacés seulement après validation ; garder une marge mémoire suffisante sans boucle de redémarrage |
| Avant bascule | Docker Desktop ne démarrait pas automatiquement à l'ouverture de session | Configurer et tester ouverture de session, veille/réveil, réseau retardé et reprise des bots |
| Avant bascule | Sauvegarde Docker manuelle | Ajouter une exécution planifiée avec verrou, contrôle d'âge et alerte d'échec ; copie chiffrée hors machine et exercice de reprise sur nouveaux volumes |
| Avant bascule | Connecteurs Google, Tavily, navigateur et exécution de code non migrés | Choisir les fonctions réellement nécessaires ; raccorder et tester les droits par agent, avec lecture seule initiale pour Google |
| Avant bascule | Budgets Windows et candidat distincts | Transférer la seule enveloppe de production, garder les dépenses de la période et désactiver les anciennes clés utilisées par les consommateurs remplacés |
| Avant exécution autonome | Le spécialiste Développement n'a actuellement pas de shell | Introduire un environnement de travail isolé et des approbations testées ; pas d'accès global au disque hôte ni au socket Docker |
| Avant multi-utilisateur | Une Gateway possède tous les agents et leurs identifiants | Conserver le propriétaire unique ; séparer instances, volumes, comptes et connecteurs si la confiance change |
| Avant nouvelle application | Le client de démonstration n'est pas un SDK mobile complet | Stockage sécurisé du token d'appareil, révocation, reprise après crash, approbations et pièces jointes à tester |
| Maintenance | Catalogue, tarifs et alias fournisseurs évolutifs | Revalider régulièrement les modèles effectivement utilisés ; garder un scénario de repli compatible et des tests de coût |
| Maintenance | Frontend historique monolithique et chemins Windows figés | Découper la future application autour d'un contrat d'API ; paramétrer les chemins d'exploitation après stabilisation de la migration |
| Maintenance | Pas de rétention unifiée des sessions, médias et archives | Définir durée et quotas avant suppression ; sauvegarder et tester le nettoyage sans perdre les sessions actives |

## Décision actuelle

Le socle est suffisamment préparé pour les essais Telegram avec des bots distincts. Le bot existant reste disponible. Les anciennes données et les archives sont conservées pour le retour arrière. Aucun objectif de disponibilité continue, aucune parité complète des MCP et aucune bascule de production ne sont annoncés sans les validations correspondantes.

Les quatre conteneurs ont été arrêtés après validation pour rendre de la mémoire au PC pendant l'attente des nouveaux bots. Aucun volume n'a été supprimé. Le redémarrage explicite est documenté dans [l'exploitation](exploitation.md).
