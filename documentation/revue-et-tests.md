# Revue et bilan de migration

État au 11 octobre 2026. **Le bot habituel Asia fonctionne maintenant dans OpenClaw, en phase pilote.** L'ancien consommateur Windows est arrêté. Les validations utilisateur Telegram et de reprise Windows restent nécessaires avant de déclarer la migration entièrement terminée.

Asia conserve le bot actuel ; Développement et Recherche utilisent chacun un bot distinct. Les trois comptes OpenClaw sont connectés. Après la pause administrateur exécutée par le propriétaire, la transaction a contrôlé l'arrêt de l'ancien consommateur, transféré le budget et activé Asia sans conflit de polling observé. Recherche a ensuite été ajouté par une fusion validée, sans modifier les comptes Asia/Développement ni les limites budgétaires.

## Changements réalisés

- Installation des images officielles OpenClaw 2026.10.1, LiteLLM 1.104.1, PostgreSQL 17.11, Speaches CPU et Playwright MCP 0.0.83, figées par empreinte ; aucune image de l'ancienne application construite.
- Copie logique de PostgreSQL vers un volume distinct ; 91 tables restaurées. Conservation du sel LiteLLM et de la comptabilité historique.
- Création des agents Asia, Développement et Recherche, avec espaces, sessions et clés propres ; refus des droits administrateur.
- Quarantaine initiale des huit clés héritées ; après transfert, seule la clé OpenCode importée a été activée dans l'équipe commune Docker et bloquée côté Windows. Plafond partagé de 19,92877484 USD après déduction des dépenses Windows, sans effacer les dépenses Docker.
- Configuration de la transcription locale pour les trois agents et de la synthèse vocale Microsoft en français.
- Création des scripts de migration, de tests, de sauvegarde Docker, de préparation des bots et d'un client WebSocket de référence pour la future application.
- Documentation de l'ensemble du projet dans ce dossier et contrôles CI enrichis.
- Reprise pour Asia de Tavily, Playwright et mémoire MCP ; Google exclu à la demande du propriétaire. Passerelle de tâches Windows vers OpenCode avec validations humaines natives.
- Tâches Windows de démarrage et sauvegarde Docker installées ; bascule contrôlée réalisée, retour arrière préparé, journal de reprise inclus dans la sauvegarde chiffrée.
- Délégation native d'Asia vers les deux spécialistes, avec missions isolées, retour au parent, refus des échanges directs et de la récursion ; budget commun conservé.

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
| Cache npm initialement détenu par root et refus d'écriture du serveur mémoire | Initialisation ponctuelle du propriétaire Linux, démarrage hors ligne et persistance vérifiés |
| Filtrage Playwright par hôte sans numéro de port donnant un HTTP 403 | Autorités exactes avec port dans la liste ; navigation et capture réelles réussies |
| Modèle devinant des paramètres MCP au lieu de lire le schéma | Instructions explicites recherche → description → appel ; vérification des vrais résultats imbriqués et des marqueurs sur disque |
| Sortie normale Docker sur stderr traitée comme erreur par Windows PowerShell 5 | Lancement masqué avec capture séparée et contrôle du code de sortie ; deux tâches du Planificateur testées |
| Hooks d'approbation et outils du plugin chargés dans des instances séparées | Reçus privés à usage unique et verrou entre instances ; test de régression, refus réel et accord réel réussis |
| Client de test connecté sans annoncer la capacité d'approbation | Capacité `plugin-approvals` explicite ; absence de route refusée, puis accord/refus via appareil appairé |
| Liste explicite des plugins retirant l'adaptateur de transcription auparavant auto-activé | Conservation explicite du plugin `openai` utilisé contre Speaches local, test de régression et revalidation audio des trois agents |
| Sauvegarde Docker initiale n'incluant pas le nouveau journal de transfert | Inclusion explicite du journal privé dans l'archive chiffrée ; vérification refusant un point pilote sans ce journal |
| Premier essai de délégation appelant un outil différé non chargé puis un paramètre d'attente incorrect | Consignes imposant découverte/lecture du schéma et `waitFor: "message"` ; nouveau parcours complet réussi |

Le premier essai audio pendant un redémarrage a échoué : le stockage OpenClaw était en maintenance. L'essai a été relancé séquentiellement après l'état `healthy` et a réussi pour les trois agents. Ce résultat motive la règle d'exploitation : attendre la disponibilité, puis effectuer les changements de configuration un par un.

## Tests exécutés

| Étape | Résultat observé | Limite de la preuve |
| --- | --- | --- |
| Application et passerelle | 16 tests Node réussis ; compilation réussie | Inclut idempotence, refus d'auto-approbation, requête modifiée/expirée et concurrence entre instances ; aucun audit exhaustif des images |
| Sauvegarde, routage, infrastructure et reprise Telegram | 29 tests Python réussis | Fixtures déterministes, refus d'une archive pilote sans journal, reprise budgétaire, ajout de bot, frontières de délégation et restauration exacte des politiques sans modifier Telegram/audio |
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
| Telegram Asia et Développement | Deux comptes actifs, bonnes associations, probes API réussis, aucun dernier échec ni conflit de polling observé ; réponse réelle d'Asia vérifiée après transfert par la Gateway | Échange depuis le compte utilisateur, photo, vocal et approbations à essayer ; aucun message de test envoyé à l'utilisateur |
| Ajout Telegram Recherche | Token distinct et sans webhook, configuration validée avant écriture, comptes Asia/Développement identiques après fusion, trois probes réussis ; inférence Recherche réelle réussie et clé dans l'équipe budgétaire commune | Premier échange depuis le compte propriétaire à effectuer ; les outils de recherche web propres au spécialiste restent à configurer/valider |
| Délégation Asia → spécialistes → Asia | Deux parcours réels réussis ; 20 contrôles sur le dernier : deux missions, réponses réelles, attente et synthèse du parent, contexte privé non copié, lecture des enfants par Asia, refus de lectures croisées, refus HTTP d'envoi/création chez les spécialistes, facturation propre aux trois clés | Sessions WebChat artificielles ; restitution Telegram, timeout, panne en mission et reprise après crash à éprouver. Les limites de quantité par demande et de durée sont détaillées dans [le guide](delegation.md) |
| Connecteurs Asia | Tavily recherche/extraction, Playwright navigation/capture/refus `file://`, mémoire création/lecture/persistance ; appels d'un vrai tour Asia vérifiés | Crawl/map non exercés ; pas de reprise des connexions du navigateur Windows ; mémoire historique absente |
| Tâches Windows d'Asia | Soumission et déduplication, commande en attente, refus natif sans exécution puis accord unique et sortie vérifiée ; accès 404 pour les autres agents. Test rejoué après transfert vers LiteLLM Docker | Commande artificielle `echo` ; boutons Telegram et questions OpenCode interactives à tester sur le canal final |
| Planificateur Windows | Démarrage et sauvegarde testés, résultat 0 ; démarrage refusé sur un runtime artificiel en rollback | Ouverture de session après redémarrage et veille/réveil non exécutées ; pas d'alerte externe d'échec |
| Garde et transaction de bascule | Refus préalable tant que l'ancien superviseur était présent ; après pause administrateur, activation réelle réussie et dix contrôles d'état positifs (ancien consommateur, clés, budget, fournisseur OpenCode, Gateway et comptes Telegram) | Rollback de cette transaction non déclenché en production ; reprise complète Windows non testée |

Les rapports détaillés restent dans `%LOCALAPPDATA%\AsiaDocker` : tests de plateforme, Gateway, isolation, budget, audio, TTS, cycle de vie, sauvegarde et activation Développement ; ainsi que `asia-tools-test-result.json`, `mcp-transports-result.json`, `opencode-bridge-result.json`, `asia-post-handoff-result.json`, `telegram-recherche-result.json`, `delegation-test-result.json`, `startup-result.json` et `scheduled-backup-result.json`. Les journaux de bascule, d'ajout de compte et de délégation restent privés et sont sauvegardés chiffrés. Ces fichiers ne sont pas copiés aveuglément dans Git. Les messages utilisés pour les essais sont artificiels.

Restaurations de contrôle réussies sur les points Docker `docker-20261011T210319-0b250d43.aes` et Windows `asia-20261011T210504-e5c708.aes`, dans `D:\AsiaBackups` : état OpenClaw restauré séparément, SQLite Windows intègre et bases temporaires de 91 tables. Ces archives sont locales et chiffrées, pas déposées sur GitHub. Le rapport privé indique le point le plus récent ; des sauvegardes supplémentaires incluent la préparation de la passerelle et ses données artificielles.

## Revue de robustesse : priorités restantes

| Priorité | Observation | Action et critère de réussite |
| --- | --- | --- |
| Validation du pilote | Asia, Développement et Recherche actifs dans OpenClaw | Tester chaque conversation, texte, photo et vocal depuis le compte propriétaire Telegram ; valider les approbations d'Asia |
| Coordination | Asia délègue et reçoit les résultats dans des sessions séparées | Valider une synthèse sur Telegram, l'annulation et les scénarios de délai/panne ; garder les spécialistes sans échanges directs |
| Stabilisation | PC de 12 Go, moins de 1 Go libre observé avec Windows et Docker en parallèle | Mesurer au repos et pendant deux tâches avec audio ; arrêter les services remplacés seulement après validation ; garder une marge mémoire suffisante sans boucle de redémarrage |
| Validation après reprise | Démarrage Docker maintenant planifié et testé manuellement | Tester véritable ouverture de session, veille/réveil, réseau retardé et reprise des bots |
| Exploitation | Sauvegarde Docker planifiée et testée, sans notification externe | Ajouter une alerte d'échec et une copie chiffrée hors machine ; exercice de reprise sur nouveaux volumes |
| Portabilité | Connecteurs repris hors Google ; tâches Windows par passerelle OpenCode | Valider les parcours Telegram ; remplacer plus tard l'exécuteur Windows par un environnement isolé si une installation entièrement Linux est souhaitée |
| Comptabilité | Budget partagé transféré, plafond réduit tenant compte de Windows | Contrôler les dates de remise à zéro avant de ramener l'enveloppe à 20 USD ; conserver les dépenses en cas de retour arrière |
| Avant exécution autonome | Le spécialiste Développement n'a actuellement pas de shell | Introduire un environnement de travail isolé et des approbations testées ; pas d'accès global au disque hôte ni au socket Docker |
| Avant multi-utilisateur | Une Gateway possède tous les agents et leurs identifiants | Conserver le propriétaire unique ; séparer instances, volumes, comptes et connecteurs si la confiance change |
| Avant nouvelle application | Le client de démonstration n'est pas un SDK mobile complet | Stockage sécurisé du token d'appareil, révocation, reprise après crash, approbations et pièces jointes à tester |
| Maintenance | Catalogue, tarifs et alias fournisseurs évolutifs | Revalider régulièrement les modèles effectivement utilisés ; garder un scénario de repli compatible et des tests de coût |
| Maintenance | Frontend historique monolithique et chemins Windows figés | Découper la future application autour d'un contrat d'API ; paramétrer les chemins d'exploitation après stabilisation de la migration |
| Maintenance | Pas de rétention unifiée des sessions, médias et archives | Définir durée et quotas avant suppression ; sauvegarder et tester le nettoyage sans perdre les sessions actives |

## Décision actuelle

Le [premier cycle de formation supervisée](formation/bilan-cycle-1.md) ajoute un bac à sable temporaire, deux modules de diagnostic revus et des procédures par rôle. Recherche réussit les cas évalués après correction ; Asia reste supervisée pour la reprise après issue inconnue, et Développement pour le respect du périmètre. Les profils de formation et leurs droits temporaires ont été retirés. Le dépôt intégré passe 54 tests Node, 35 tests Python et la compilation ; la sauvegarde finale restaure OpenClaw et 91 tables PostgreSQL.

La [reprise ciblée suivante](formation/bilan-reprise.md) valide les nouveaux scénarios d'Asia et les actions de Développement, avec une correction de formulation sur la lecture seule. Elle utilise une Gateway distincte, sans redémarrer les trois bots. Le dépôt passe désormais 57 tests Node et 39 tests Python. Les procédures revues sont installées ; les permissions de production restent inchangées. Cette réussite limitée aux cas évalués ne constitue pas une qualification d'autonomie générale.

Le pilote utilise les bots Asia, Développement et Recherche dans OpenClaw. Les anciennes données et les archives sont conservées pour le retour arrière. L'activation réelle et les contrôles techniques sont passés ; ils ne prouvent pas encore tous les parcours utilisateur Telegram ni la disponibilité après redémarrage Windows.

Cinq conteneurs servent les trois agents avec un budget commun. Asia coordonne désormais leurs missions ; les conversations Telegram et les accès aux outils restent distincts. Le shell natif OpenClaw demeure désactivé ; seule Asia possède la passerelle de tâches Windows. OpenCode reste donc nécessaire comme exécuteur pendant cette phase hybride. Recherche dispose de la lecture d'URL mais pas encore des connecteurs MCP d'Asia. La procédure [bascule-asia.md](bascule-asia.md) décrit le transfert réalisé et les validations restantes.
