# Validation du redémarrage Windows

Le propriétaire a autorisé un redémarrage complet après validation des boutons Telegram. **Le contrôle avant redémarrage est réussi ; la reprise effective reste à vérifier après une nouvelle ouverture de session Windows.** Le lancement d'une commande de redémarrage ne suffit pas à déclarer ce test réussi.

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
