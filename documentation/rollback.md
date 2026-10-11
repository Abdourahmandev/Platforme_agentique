# Retour arrière

## État actuel : candidat distinct

L'ancien bot, OpenCode, LiteLLM Windows et PostgreSQL Windows restent en place. Les ports, secrets administrateur et volumes du candidat sont distincts. Le rollback immédiat consiste à arrêter le candidat, sans supprimer ses données :

```powershell
& ./infra/compose.ps1 --profile audio stop
Invoke-RestMethod 'http://127.0.0.1:3210/api/bootstrap' | Select-Object healthy,version
```

Le dernier appel passe par l'interface Asia locale pour contrôler la santé d'OpenCode. Ne jamais saisir un mot de passe dans la ligne de commande ou publier les logs de configuration.

Les ports Windows de référence restent : Asia 3210, OpenCode 4096, LiteLLM 4000, PostgreSQL 55432. Les anciennes associations Tailscale sont conservées.

## Suspendre seulement le bot Développement

Le compte `developpement` est le premier bot activé dans OpenClaw. Pour le suspendre sans arrêter Asia ni effacer son historique :

```powershell
& ./infra/compose.ps1 exec -T openclaw node dist/index.js config set channels.telegram.accounts.developpement.enabled false --strict-json
& ./infra/compose.ps1 exec -T openclaw node dist/index.js channels status --probe --channel telegram --json
```

Contrôler que ce compte est arrêté. En cas de doute ou d'absence de réponse de la Gateway, `./infra/compose.ps1 stop openclaw` arrête le processus Docker qui le reçoit. Les tokens et volumes sont conservés. Pour une reprise, réactiver ce compte et vérifier son état ; ne pas relancer l'initialiseur qui refuse d'écraser les associations actives.

## Après un transfert de token Telegram

La procédure exécutable, ses préconditions et ses limites de validation sont dans [bascule-asia.md](bascule-asia.md). Après création du journal de transfert, utiliser `python infra/activate-asia.py --rollback` : l'arrêt d'OpenClaw précède la reprise Windows, les dépenses Docker sont reportées, la clé et l'URL OpenCode sont restaurées. La tâche de démarrage Docker refuse ensuite un état de rollback ou un journal incomplet. Cette transaction n'a pas encore été exécutée en production ; les restaurations isolées et les gardes ont été testés.

Asia réutilisera le token du bot actuel. La copie préparée sous `AsiaDocker/secrets/asia.token` ne change pas son propriétaire d'exécution : jusqu'à la bascule, seul le service Windows reçoit les messages. Garder le fichier de credentials Windows pour pouvoir revenir à ce service avec la même identité Telegram.

L'ordre est impératif :

1. Désactiver/arrêter le consommateur OpenClaw du bot concerné et vérifier son arrêt.
2. Conserver une sauvegarde de l'état OpenClaw et la date de fin de traitement des messages.
3. Réactiver l'ancien superviseur Telegram, avec le token et les paramètres d'origine conservés hors Git.
4. Vérifier qu'un seul consommateur tourne, puis envoyer un nouveau message de contrôle depuis le compte propriétaire.
5. Contrôler les éventuels messages en attente avant toute répétition d'une action. Une absence de réponse ne prouve pas qu'une action n'a pas été exécutée.

La tâche `OpenCode Web` peut démarrer le superviseur Telegram comme compagnon. La bascule doit donc neutraliser aussi son démarrage automatique du bot, et restaurer cette configuration lors du rollback. Arrêter uniquement le processus Node du bot ne suffit pas : son superviseur peut le relancer.

Les conversations créées dans OpenClaw restent dans ses sauvegardes ; elles ne réapparaissent pas automatiquement dans OpenCode. Les réponses et dépenses produites pendant la fenêtre Docker doivent être conservées. Ne pas restaurer un ancien dump par-dessus les nouvelles données pour revenir à un ancien logiciel.

## Données perdues ou volume endommagé

Arrêter les consommateurs avant la restauration. Garder une copie du volume endommagé. Restaurer d'abord dans un nouvel environnement isolé, sans réseau Telegram sortant. Vérifier les agents, l'intégrité des bases et les droits d'accès avant de réutiliser un token.

La procédure de sauvegarde effectue déjà une restauration de contrôle vers un répertoire OpenClaw distinct et une base PostgreSQL temporaire. Elle ne remplace jamais les bases actives. Pour une reprise complète, il faut également la même version des images, les fichiers d'environnement, les tokens, le sel LiteLLM et la clé de déchiffrement de l'archive.

**Ne pas utiliser `docker compose down -v`, `docker volume prune` ou une suppression du dossier de données comme procédure de rollback.**
