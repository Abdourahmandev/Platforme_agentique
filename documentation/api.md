# Contrat de la future application

Le client technique [gateway-client.mjs](../infra/gateway-client.mjs) et ses [tests](../infra/test-gateway.mjs) valident le protocole WebSocket de la version OpenClaw installée. Ce client est une preuve d'intégration ; il ne constitue pas encore une application mobile complète.

## Identifiants

| Identifiant | Usage |
| --- | --- |
| `agentId` | Identité stable : `asia`, `developpement`, `recherche` |
| `accountId` | Compte du canal, par exemple le bot Telegram associé |
| `sessionKey` | Conversation appartenant à un agent ; à conserver telle que renvoyée par OpenClaw |
| `idempotencyKey` | Identité d'un envoi utilisateur, conservée jusqu'à confirmation |
| `runId` | Exécution à suivre ou annuler |
| `deviceId` | Client appairé, avec sa propre paire de clés et ses portées |

Ne pas utiliser le nom d'affichage d'un agent comme clé de données. Ne pas créer une nouvelle session en supposant qu'elle reprendra automatiquement celle de Telegram : retrouver et sélectionner la session côté serveur.

## Flux testé

1. Connexion WebSocket sur la même origine que la Gateway.
2. Lecture de `connect.challenge`, signature Ed25519 avec l'horodatage et le nonce reçus.
3. `connect` au protocole 4, puis appairage explicite du nouvel appareil.
4. `agents.list` et `sessions.list` pour construire la navigation.
5. `chat.send` avec une clé d'idempotence stable.
6. Événements `chat` : fragments `delta`, fin `final`, interruption `aborted` ou erreur.
7. `chat.abort` pour demander l'arrêt d'une exécution précise.
8. `chat.history` après reconnexion pour retrouver l'état confirmé.

Le test soumet deux fois le même identifiant et vérifie un seul message utilisateur. Après une coupure, le client ne renvoie jamais automatiquement une mutation avec un nouvel identifiant. La durée de déduplication et les cas de crash du serveur doivent être testés avant de promettre une livraison « exactement une fois ».

## Authentification et limites

Le client de test reçoit `operator.read`, `operator.write`, `operator.approvals` et `operator.questions`, sans `operator.admin`. La lecture de configuration peut être permise sans droit de modification ; le test de refus utilise une opération administrative, pas une simple lecture.

Le client technique utilise la clé Gateway pour son premier appairage. Une application distribuée devra conserver un token d'appareil dans le stockage sécurisé de la plateforme et gérer révocation, expiration, déconnexion et changement de portées. Elle ne doit pas embarquer de secret maître dans son code source ou ses bundles.

Les points HTTP compatibles OpenAI ont servi aux tests texte/image et aux identités. Leur token donne des droits de propriétaire sur la Gateway entière ; ils ne constituent pas une API publique multi-utilisateur. Voir [la frontière d'accès de l'API outils](https://docs.openclaw.ai/gateway/tools-invoke-http-api).

Les approbations, les pièces jointes Telegram et la reprise d'une exécution après panne doivent être validées séparément. Une réponse HTTP réussie ne prouve pas à elle seule que ces parcours fonctionnent.
