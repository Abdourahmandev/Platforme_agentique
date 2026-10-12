# Validation du redémarrage Windows

Le propriétaire a effectué un redémarrage complet le 12 octobre 2026 après validation des boutons Telegram. **Les 13 contrôles techniques après reprise sont réussis.** Les services ont démarré par leurs mécanismes automatiques ; une intervention a arrêté Ollama pour libérer de la mémoire pendant le contrôle. Le délai d'un prochain démarrage sans cette intervention reste donc à mesurer.

## Résultat du 12 octobre 2026

La première commande de redémarrage avait échoué avec le code Windows 1271 : machine verrouillée, arrêt sans forçage refusé. Elle n'a pas été relancée automatiquement. Le propriétaire a ensuite redémarré Windows lui-même.

| Contrôle | Résultat observé |
| --- | --- |
| Nouveau démarrage Windows | 12 octobre à 00 h 09 min 26 s, heure de New York ; précédent démarrage le 6 octobre |
| Démarrage automatique | `Asia Docker Startup` lancée à 00 h 10 min 10 s, terminée avec le code 0 à 00 h 17 min 21 s |
| Services | Les cinq conteneurs sains, mêmes images ; aucune relance manuelle de Docker ou de Compose |
| Comptes Telegram | Asia, Développement et Recherche en fonctionnement, sondes natives réussies, aucune dernière erreur |
| Sessions et appareil | Les 53 identifiants de sessions sont conservés ; l'appareil de test déjà appairé se reconnecte, sans nouvelle association |
| Configuration et fichiers | Empreinte de configuration identique hors métadonnées ; les 34 fichiers des espaces des agents sont identiques |
| Comptabilité | Mêmes équipes, plafonds et dates de budget ; dépenses enregistrées conservées |
| Exécuteur Windows | OpenCode accessible, sans tâche, permission ou question en attente ; fournisseur toujours sur LiteLLM Docker |
| Ancien bot | Marqueur de migration et garde présents, consommateur historique resté arrêté |

Le journal `%LOCALAPPDATA%/AsiaDocker/training/windows-restart-result.json` conserve ces contrôles. `windows-restart-gateway-result.json` conserve la comparaison des sessions. Le propriétaire a ensuite envoyé un court message aux trois bots et confirmé : « Oui, les trois répondent ». Cette confirmation du parcours Telegram après redémarrage est enregistrée séparément des sondes techniques.

Le démarrage a été lent : presque huit minutes entre le démarrage Windows et le succès de la tâche. Pendant cette attente, l'application Ollama inutilisée s'était relancée avec environ 2,5 Gio de mémoire résidente, sans modèle chargé. La mémoire libre observée est descendue à 398 Mio. Les services et la passerelle avaient commencé à répondre avant son arrêt ; la tâche a terminé quatre secondes après. Cela ne prouve pas qu'Ollama soit l'unique cause du délai.

Ollama a été arrêté, puis son seul raccourci `Ollama.lnk` retiré du dossier de démarrage automatique. Il est conservé sous `%LOCALAPPDATA%/AsiaDocker/training/disabled-startup`. Le journal `ollama-startup-disabled.json` contient le chemin d'origine, l'empreinte SHA-256 et les octets du raccourci pour la sauvegarde chiffrée. Aucun modèle ni programme n'a été désinstallé. Pour annuler cette modification, restaurer le raccourci à son chemin d'origine après vérification de l'empreinte et de l'absence d'un nouveau raccourci à cet endroit.

La sauvegarde finale `D:\AsiaBackups\docker-20261012T042220-7dc044d5.aes` inclut les preuves privées du redémarrage et du retrait du raccourci. Sa restauration de contrôle réussit : 259 fichiers vérifiés, archive native OpenClaw restaurée dans un répertoire distinct et 91 tables PostgreSQL restaurées dans une base temporaire. Les données actives ne sont pas remplacées.

Limite relevée : les appels Docker de `ops/start-docker.ps1` utilisent encore une attente de processus non bornée ; la boucle de quatre minutes ne garantit donc pas une échéance si un appel reste bloqué. Le Planificateur impose une limite globale de 25 minutes. Un délai par commande et un état explicite « démarrage en cours » constituent les prochains durcissements ; le rapport de succès doit toujours être daté après le démarrage Windows pour être valable. La veille/réveil reste distincte de ce test.

## État conservé avant le test

Le journal privé `%LOCALAPPDATA%/AsiaDocker/training/windows-restart-private.json` conserve l'heure de démarrage Windows, les identifiants de 53 sessions, les empreintes de 34 fichiers des espaces des agents, celle de la configuration hors métadonnées, les images et états des cinq conteneurs et la comptabilité des trois clés. Aucun contenu de conversation ni secret n'est publié dans ce document.

Les vérifications avant interruption confirment : aucune exécution d'agent ou tâche OpenCode active, aucune permission ou question OpenCode en attente, aucun verrou de mutation de la passerelle, cinq conteneurs sains et aucune dégradation de plugin. La sauvegarde Docker récente possède une restauration de contrôle réussie. Son chemin est conservé dans le journal.

`Asia Docker Startup` est activée à l'ouverture de session du propriétaire. Elle lance Docker Desktop si nécessaire, attend le moteur, puis démarre PostgreSQL, LiteLLM, OpenClaw, Speaches et Playwright. La tâche `OpenCode Web` est également activée. Le garde de migration doit continuer d'empêcher la relance de l'ancien consommateur Telegram. L'application utilisée pour cette conversation doit être rouverte pour poursuivre les vérifications avec l'assistant.

Le redémarrage demandé n'utilise pas de fermeture forcée. Windows peut demander de fermer une application qui le bloque. Un délai positif de `shutdown /t` implique `/f` sous Windows : le délai de préparation est donc réalisé par un petit processus séparé avant l'appel `shutdown /r /t 0`.

## Contrôles après connexion

1. Comparer `LastBootUpTime` à `boot_before` du journal : elle doit être plus récente.
2. Attendre la fin de `Asia Docker Startup`. Vérifier son résultat et `%LOCALAPPDATA%/AsiaDocker/startup-result.json` : succès daté après le nouveau démarrage.
3. Vérifier les cinq services sains, puis sonder les trois comptes Telegram. Vérifier également l'accès à OpenCode et l'absence de reprise de l'ancien bot.
4. Comparer les empreintes de configuration et documents, la présence des sessions enregistrées, les budgets et les dépenses. Une nouvelle session ou une dépense supplémentaire légitime n'est pas une perte ; toute baisse inexpliquée de comptabilité demande une inspection.
5. Exécuter `node infra/test-gateway.mjs` pour contrôler la connexion de l'appareil déjà appairé et les sessions. Compléter par un court échange Telegram si nécessaire. Conserver le bilan daté dans le dossier privé `training` avant de déclarer le test réussi.

Ne pas lancer `infra/test-lifecycle.py` pour cela : il est réservé au staging sans bots actifs.

## En cas d'échec

Consulter `startup-result.json` et les logs privés `startup*.log`. Après inspection, `./ops/start-docker.ps1` permet de reprendre le démarrage sans recréer les données. Distinguer une reprise automatique réussie d'une récupération manuelle. Ne supprimer aucun volume, ne réactiver aucun ancien bot et ne restaurer aucune ancienne base par-dessus la production pour faire passer le test. Le [retour arrière de migration](rollback.md) est une opération distincte qui conserve la comptabilité et évite deux consommateurs Telegram.
