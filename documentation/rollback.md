# Retour arrière

## État actuel : candidat distinct

L'ancien bot, OpenCode, LiteLLM Windows et PostgreSQL Windows restent en place. Les ports, secrets administrateur et volumes du candidat sont distincts. Le rollback immédiat consiste à arrêter le candidat, sans supprimer ses données :

```powershell
& ./infra/compose.ps1 --profile audio stop
Invoke-RestMethod 'http://127.0.0.1:3210/api/bootstrap' | Select-Object healthy,version
```

Le dernier appel passe par l'interface Asia locale pour contrôler la santé d'OpenCode. Ne jamais saisir un mot de passe dans la ligne de commande ou publier les logs de configuration.

Les ports Windows de référence restent : Asia 3210, OpenCode 4096, LiteLLM 4000, PostgreSQL 55432. Les anciennes associations Tailscale sont conservées.

## Après un transfert de token Telegram

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
