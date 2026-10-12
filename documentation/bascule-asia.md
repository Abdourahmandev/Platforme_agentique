# Bascule contrôlée d'Asia

## État de cette étape

**Bascule réalisée le 11 octobre 2026.** Asia Telegram est désormais servi par OpenClaw avec le même token et le même bot. Développement reste actif. Le superviseur et l'ancien bot Windows sont arrêtés ; le marqueur persistant empêche leur relance. Google Workspace est exclu à la demande du propriétaire : il n'était pas connecté.

Dans le candidat, les appels réels ont validé Tavily (recherche et extraction), Playwright (navigation et capture de structure) et la mémoire MCP (écriture, lecture et persistance après redémarrage du serveur). Un tour réel d'Asia a utilisé les trois connecteurs ; ses appels et leurs résultats ont été contrôlés dans son historique de test. La transcription, les images et l'isolation des espaces/sessions ont également été revérifiées. Les essais n'ont envoyé aucun message Telegram.

L'utilisateur a exécuté la pause administrateur Windows. Le contrôle d'absence des processus et du verrou a ensuite permis l'activation. Les deux comptes Telegram sont connectés, sans conflit de polling observé ; une inférence réelle d'Asia a réussi. Le runtime est `asia-pilot` et le journal `active`. Le test complet de passerelle Windows a été rejoué avec le nouveau LiteLLM : déduplication, attente, refus sans exécution et accord unique réussis. **Le propriétaire confirme maintenant les réponses des trois bots, ainsi que photo et vocal pour Asia. Les boutons d'approbation privés sont reçus ; accord unique et refus ont été vérifiés.** Voir les [preuves et limites](tests-robustesse.md) et le [test des approbations Telegram](approbations-telegram.md).

## Connecteurs et périmètre

| Fonction | Mise en œuvre | Limite vérifiée ou restante |
| --- | --- | --- |
| Recherche web | MCP distant officiel Tavily, authentification par en-tête issu de l'environnement privé | Coûts Tavily distincts du budget LLM ; recherche/extraction testées, crawl/map exposés mais pas exercés en réel |
| Navigateur | Image officielle Microsoft Playwright MCP 0.0.83, figée par digest, conteneur non privilégié et sans port hôte | Nouveau contexte isolé ; les connexions du navigateur Windows ne sont pas importées ni conservées après fermeture du contexte |
| Fichiers du navigateur | Seul le sous-répertoire `workspaces/asia` est monté | Aucun montage des clés OpenClaw ni des espaces Développement/Recherche ; les fichiers téléchargés restent à vérifier avant utilisation |
| Mémoire | `@modelcontextprotocol/server-memory@1.0.0`, cache npm persistant, démarrage hors ligne | Fichier JSONL propre à Asia ; le chemin de mémoire Windows était absent. Les tours d'agents sont sérialisés pour éviter des écritures concurrentes |
| Droits des autres agents | Refus explicite des trois serveurs MCP pour Développement et Recherche | Politiques locales à une Gateway de confiance ; pas une isolation hostile entre utilisateurs |
| Texte, images, audio | Routage LiteLLM, transcription Speaches et synthèse Microsoft déjà configurée ; texte/photo/vocal Asia confirmés par le propriétaire sur Telegram | Cette confirmation ne valide pas la livraison d'une réponse vocale de synthèse ni les médias des deux spécialistes |
| Tâches Windows | Plugin natif `asia-opencode`, sessions propres à la passerelle, permissions OpenCode conservées | Commande synthétique testée avec refus puis accord unique natif ; suivi explicite des tâches longues, pas de notification autonome de fin |
| Historique Windows | OpenCode reste installé et son historique est sauvegardé | Les anciennes conversations ne deviennent pas automatiquement des conversations OpenClaw |

Chromium s'exécute avec `--no-sandbox` **dans son conteneur dédié**, sans clés de modèles et avec une racine en lecture seule. Ce choix ne doit pas être confondu avec une sandbox de navigation complète : Playwright documente que ses contrôles d'origines ne sont pas une frontière de sécurité. Les URL `file://` sont refusées lors du test ; aucune garantie générale de blocage de tout le réseau local n'est annoncée. `browser_run_code` et `browser_install` sont retirés du catalogue de l'agent. Le navigateur natif d'OpenClaw reste désactivé.

## Préparation reproductible

Depuis la racine du dépôt, après les sauvegardes décrites dans le guide d'exploitation :

```powershell
python infra/configure-asia-tools.py --prepare-env
./infra/compose.ps1 up -d --no-deps --wait --wait-timeout 360 openclaw playwright
python infra/configure-asia-tools.py --apply
python infra/test-asia-tools.py
node infra/test-opencode-bridge.mjs
./infra/install-docker-operations.ps1
python infra/activate-asia.py
```

Le script résout la référence d'environnement Tavily existante et copie cette clé dans le runtime privé. Il installe aussi le plugin depuis les sources du dépôt et copie les identifiants OpenCode dans le répertoire privé de credentials du volume, hors des workspaces. Il conserve un état antérieur de configuration, fusionne les nouvelles permissions et ne modifie pas Telegram. Le cache npm est initialisé avec son propriétaire Linux par un conteneur ponctuel sans réseau. Aucune image applicative n'est construite. Après une modification du code d'un plugin déjà chargé, exécuter `./infra/compose.ps1 exec -T openclaw node dist/index.js plugins reload asia-opencode` avant son test.

La passerelle conserve un journal privé `asia-opencode/tasks.json`. Une soumission incertaine ne se rejoue pas automatiquement. Le verrou de mutation protège aussi les différentes instances du plugin ; un verrou restant après incident exige une inspection opérateur, pas une suppression automatique. Les autorisations natives passent par un reçu privé lié à l'appel, aux paramètres et à la demande OpenCode complète. Ce reçu expire après 30 secondes et est consommé atomiquement avant la réponse `once`. Un refus, une absence de surface d'approbation ou une demande modifiée n'autorise rien. Les permissions trop longues pour être affichées intégralement exigent une vérification dans l'interface OpenCode. Les refus et accords ont d'abord été testés avec le client Gateway appairé, sur la commande artificielle `echo ASIA_BRIDGE_TEST`, puis [dans Telegram avec le propriétaire](approbations-telegram.md), sur deux nouvelles commandes distinctes. Les boutons ciblent son échange privé avec Asia (`target=dm`).

`infra/test-mcp-transports.mjs` s'exécute par entrée standard avec `docker exec -i ... node --input-type=module`. Il utilise le SDK MCP présent dans l'image pour valider les transports sans modèle, puis supprime ses seules données artificielles. Les diagnostics restent privés. L'API HTTP `/tools/invoke` n'est pas une preuve positive des outils MCP différés : le test d'agent contrôle leurs véritables appels via `tool_call` et leurs résultats.

Le plan privé `AsiaDocker/asia-handoff-plan.json` est un instantané avant mutation : il confirme `legacy_stopped: true` et conserve `new_consumer_started: false` par définition. L'état final est dans `asia-handoff-private.json` (`active`) et `asia-post-handoff-result.json` (dix contrôles réussis). Le plan seul ne décrit pas l'état courant du bot.

## Transfert du consommateur

Les commandes suivantes documentent le transfert déjà réalisé ; ne pas les rejouer sur le pilote actif. Pour reproduire cette étape depuis un état de préparation validé et une archive récente, ouvrir **PowerShell en administrateur avec le même compte Windows** et exécuter depuis le dépôt :

```powershell
./infra/control-legacy-telegram.ps1 -Mode Pause
```

Cette commande valide les chemins des processus avant de les arrêter. Elle sauvegarde le lanceur, ajoute un garde de pause persistant, arrête d'abord le superviseur puis le bot, et contrôle l'absence de processus et la libération du verrou. OpenCode et son serveur restent en place. Un PID réutilisé ou une identité inaccessible provoque un refus avant toute modification. Le lanceur compagnon peut toujours être invoqué au démarrage, mais le garde l'empêche de recréer le consommateur pendant la migration.

Puis, depuis une session normale :

```powershell
python infra/activate-asia.py --activate
```

L'activation est volontairement séparée de l'initialiseur de staging. Elle exige le marqueur de pause, l'absence des anciens PID, le verrou disponible, des tests de connecteurs et de passerelle réussis depuis moins de 24 heures, une archive vérifiée de moins de 24 heures et aucune tâche OpenCode active. La configuration est fusionnée en une écriture validée. L'identité Telegram reste la même, les groupes restent désactivés et les messages comme les approbations sont limités au propriétaire.

La transaction bloque d'abord l'ancienne clé dans LiteLLM Windows, rattache sa copie importée à l'équipe Docker et change l'URL du fournisseur OpenCode vers `127.0.0.1:14000`. Ainsi l'ancienne interface peut continuer à utiliser OpenCode et le catalogue existant tout en partageant le budget des nouveaux agents. Les 34 routes doivent être accessibles avec la clé transférée avant l'activation du bot. Les dépenses enregistrées ne sont pas effacées.

Le plafond Docker est calculé comme **plafond Windows moins dépenses Windows déjà enregistrées**. Les dépenses déjà faites dans Docker restent comptées dans cette enveloppe ; chaque clé est aussi limitée. Le script recalcule le montant au moment du transfert. Ce plafond réduit reste conservé aux périodes suivantes tant qu'un opérateur ne le ramène pas explicitement à 20 USD après le changement de période. Les requêtes en vol peuvent dépasser un plafond comptable.

Le script vérifie ensuite les deux connexions Telegram et une réponse réelle d'Asia. Il marque le runtime `asia-pilot`, pas « migration entière terminée ». Le journal privé empêche de rejouer automatiquement une bascule interrompue : inspecter l'état puis reprendre ou annuler explicitement.

## Retour arrière

Après une tentative de transfert ayant créé le journal :

```powershell
python infra/activate-asia.py --rollback
```

Le retour arrière arrête OpenClaw, fige l'enveloppe Docker, conserve ses nouvelles dépenses dans le compteur Windows, restaure l'URL OpenCode et réactive sa clé. Il désactive le compte Asia dans le volume arrêté, retire sa route, puis relance le consommateur Windows. Développement et Recherche sont suspendus avec OpenClaw pendant ce rollback complet. Les volumes, les historiques et les archives sont conservés. Ne pas relancer aveuglément Docker avant de vérifier les budgets et le compte Asia désactivé.

Un échec pendant l'activation déclenche cette procédure. Une impossibilité de retour arrière laisse le nouveau consommateur arrêté et exige une inspection du journal privé ; elle ne justifie jamais deux consommateurs du même token.

**Validation réalisée :** préparation, refus du double consommateur, tests unitaires de fusion et de budget, restaurations isolées Windows/Docker, bascule effective, contrôle des comptes et de la réponse Asia, passerelle Windows via le nouveau budget ; confirmation du propriétaire pour les conversations des trois bots et les médias entrants d'Asia ; accord unique et refus avec les boutons Telegram ; [redémarrage Windows réel](redemarrage-windows.md), données conservées et trois réponses Telegram confirmées. **Non réalisée à ce stade :** scénario d'échec réel de cette transaction et veille/réveil. La lenteur du démarrage et l'intervention sur Ollama sont détaillées dans le bilan de reprise.

Références : [MCP OpenClaw](https://docs.openclaw.ai/cli/mcp/registry), [Tavily](https://docs.tavily.com/documentation/mcp), [Playwright MCP](https://github.com/microsoft/playwright-mcp), [mémoire MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/memory).
