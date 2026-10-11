# Retour arrière

## État actuel : Asia dans OpenClaw

L'ancien bot est arrêté mais ses fichiers sont conservés. OpenCode utilise maintenant LiteLLM Docker ; arrêter Docker seul interromprait donc aussi ses appels de modèles. **Utiliser la transaction de retour arrière**, qui restaure également le fournisseur, la clé, les dépenses et le consommateur Telegram Windows :

```powershell
python infra/activate-asia.py --rollback
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

La procédure exécutable, ses préconditions et ses limites de validation sont dans [bascule-asia.md](bascule-asia.md). Le journal de transfert existe et indique `active`. Avec `--rollback`, l'arrêt d'OpenClaw précède la reprise Windows, les dépenses Docker sont reportées, la clé et l'URL OpenCode sont restaurées. Développement est également suspendu. La tâche de démarrage Docker refuse ensuite un état de rollback ou un journal incomplet. L'activation réelle a réussi ; le rollback de cette transaction n'a pas été déclenché en production. Les restaurations isolées et les gardes ont été testés.

Asia réutilise le token du bot habituel ; seul OpenClaw reçoit actuellement ses messages. Garder le fichier de credentials Windows et le journal privé pour pouvoir revenir à cet ancien service avec la même identité Telegram. La sauvegarde chiffrée Docker inclut désormais ce journal de retour arrière.

L'ordre est impératif :

1. Désactiver/arrêter le consommateur OpenClaw du bot concerné et vérifier son arrêt.
2. Conserver une sauvegarde de l'état OpenClaw et la date de fin de traitement des messages.
3. Réactiver l'ancien superviseur Telegram, avec le token et les paramètres d'origine conservés hors Git.
4. Vérifier qu'un seul consommateur tourne, puis envoyer un nouveau message de contrôle depuis le compte propriétaire.
5. Contrôler les éventuels messages en attente avant toute répétition d'une action. Une absence de réponse ne prouve pas qu'une action n'a pas été exécutée.

La tâche `OpenCode Web` peut invoquer le superviseur Telegram comme compagnon. Le garde installé dans son lanceur vérifie `migration-paused` et empêche de recréer le bot. Le rollback retire ce marqueur seulement après l'arrêt du consommateur Docker. Arrêter uniquement le processus Node du bot ne suffirait pas : son superviseur pourrait le relancer.

Les conversations créées dans OpenClaw restent dans ses sauvegardes ; elles ne réapparaissent pas automatiquement dans OpenCode. Les réponses et dépenses produites pendant la fenêtre Docker doivent être conservées. Ne pas restaurer un ancien dump par-dessus les nouvelles données pour revenir à un ancien logiciel.

## Données perdues ou volume endommagé

Arrêter les consommateurs avant la restauration. Garder une copie du volume endommagé. Restaurer d'abord dans un nouvel environnement isolé, sans réseau Telegram sortant. Vérifier les agents, l'intégrité des bases et les droits d'accès avant de réutiliser un token.

La procédure de sauvegarde effectue déjà une restauration de contrôle vers un répertoire OpenClaw distinct et une base PostgreSQL temporaire. Elle ne remplace jamais les bases actives. Pour une reprise complète, il faut également la même version des images, les fichiers d'environnement, les tokens, le sel LiteLLM et la clé de déchiffrement de l'archive.

**Ne pas utiliser `docker compose down -v`, `docker volume prune` ou une suppression du dossier de données comme procédure de rollback.**
