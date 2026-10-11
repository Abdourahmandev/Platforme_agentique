# Installation et migration

Ces commandes s'exécutent dans PowerShell, depuis la racine du dépôt. Elles supposent l'installation Windows de référence décrite dans [l'exploitation historique](../docs/operations.md), Docker Desktop en mode Linux et Python 3.13. Le clonage seul ne restaure pas les secrets. Pour une nouvelle installation, préparer un environnement Python dédié :

```powershell
python -m venv "$env:LOCALAPPDATA\AsiaDockerOps\venv"
$python = "$env:LOCALAPPDATA\AsiaDockerOps\venv\Scripts\python.exe"
& $python -m pip install -r ops/requirements.txt
```

## 1. Sauvegarder et prouver la reprise

```powershell
& $python ops/backup.py --restore-check
npm.cmd test
npm.cmd run build
```

La sauvegarde contrôle les empreintes, l'intégrité SQLite et restaure PostgreSQL dans une base temporaire. Ne pas commencer une bascule si cette commande échoue. Conserver le chemin de l'archive et sa clé de récupération dans des emplacements protégés distincts.

## 2. Préparer le candidat

```powershell
& $python infra/prepare-runtime.py
& ./infra/compose.ps1 config --quiet
& ./infra/compose.ps1 pull postgres litellm openclaw
& ./infra/compose.ps1 up -d postgres
& $python infra/migrate-database.py
& ./infra/compose.ps1 up -d --wait --wait-timeout 240 litellm
```

`prepare-runtime.py` crée `%LOCALAPPDATA%\AsiaDocker` avec une ACL limitée au propriétaire et à SYSTEM. Les clés fournisseurs et le sel de chiffrement sont copiés depuis l'installation existante ; le secret administrateur du candidat est distinct. Le script refuse d'écraser un runtime déjà initialisé.

La migration refuse d'écraser une base cible existante. Après un échec partiel, inspecter le candidat et garder les preuves avant de décider de recréer un volume. Ne jamais supprimer un volume pour « réparer » automatiquement une installation contenant des données utiles.

## 3. Créer les agents

```powershell
& $python infra/provision-agents.py
& $python infra/quarantine-imported-keys.py
& ./infra/compose.ps1 --profile bootstrap run --rm --no-deps openclaw-init
& ./infra/compose.ps1 up -d --wait --wait-timeout 240 openclaw
& ./infra/compose.ps1 exec -T openclaw node dist/index.js config validate
```

L'initialiseur copie uniquement les fichiers préparés vers un volume Linux vide, puis applique les permissions du compte de service. Il refuse un volume non vide. Après initialisation, le dossier Windows `AsiaDocker\openclaw` n'est qu'une source d'installation : **la configuration active est dans le volume**, et doit être modifiée avec les commandes/API OpenClaw.

Les trois identités et leurs instructions sont dans [infra/agents](../infra/agents). Aucun bot Telegram n'est activé par ces commandes.

## 4. Tester les fonctions

```powershell
& $python infra/test-platform.py --inference
node infra/test-gateway.mjs
node infra/test-gateway.mjs --inference
& $python infra/test-isolation.py --vision
& $python infra/test-team-budget.py
& $python ops/backup-docker.py --restore-check
```

Les tests `--inference` et d'isolation font de petits appels payants avec des données artificielles. Ils n'envoient pas de message Telegram. Les résultats sont conservés dans le runtime privé.

Installer l'audio et exécuter ses tests selon [le guide d'exploitation](exploitation.md#audio). Ensuite, **sans autre test ou modification en parallèle**, lancer `python infra/test-lifecycle.py` : il redémarre PostgreSQL, arrête le candidat, vérifie la disponibilité Windows, recrée les conteneurs sans supprimer les volumes, puis contrôle la persistance. Il refuse de fonctionner si un consommateur Telegram est activé. Les scripts lancés l'un après l'autre doivent tous retourner un code zéro ; ne pas poursuivre après un échec.

Le premier client WebSocket doit être appairé. Il affiche un identifiant de demande, jamais son secret. Vérifier qu'il s'agit de la demande que l'on vient de lancer, puis utiliser `openclaw devices approve IDENTIFIANT` dans le conteneur et relancer le test. Ne jamais désactiver l'authentification des appareils pour contourner ce contrôle.

## 5. Préparer les bots

**Choix retenu : Asia conserve le bot Telegram actuel et son token.** Aucun nouveau bot Asia n'est nécessaire. Préparer sa reprise sans changer le service en production :

```powershell
& ./infra/prepare-existing-asia.ps1
```

Cette commande valide le bot avec `getMe` et copie son token dans `AsiaDocker/secrets/asia.token`, sous ACL privée. Elle ne lit pas les mises à jour Telegram, ne change pas le webhook et ne démarre aucun consommateur. Le nom, le lien et la conversation Telegram restent ceux du bot existant. L'historique OpenCode n'est pas pour autant converti en mémoire OpenClaw.

Créer seulement les bots **Développement et Recherche** dans BotFather et stocker leurs tokens avec :

```powershell
'developpement','recherche' | ForEach-Object {
    & ./infra/set-telegram-token.ps1 -Agent $_
}
```

La commande valide chaque token auprès de Telegram et l'enregistre dans le dossier privé. Un token reste un secret même si le dépôt est privé. Il ne doit pas être collé dans une issue, une conversation ou un fichier suivi par Git.

Une fois le candidat démarré, `python infra/configure-telegram.py --reuse-existing-asia` prépare et valide les associations sans les activer. **L'initialiseur de staging refuse toujours l'activation du token de production** : la bascule du bot Asia doit inclure l'arrêt de l'ancien consommateur et de son superviseur, la neutralisation de sa relance automatique, puis le démarrage du nouveau consommateur. Une simple copie de token ou l'arrêt d'un processus enfant ne constitue pas ce transfert.

Le mode historique sans `--reuse-existing-asia` conserve la possibilité d'un bot temporaire `asia-test`, facultatif. Son activation avec `--activate` reste réservée aux bots distincts du bot de production. Les messages directs sont réservés au propriétaire actuel et les groupes désactivés. Les parcours utilisateur Telegram sont validés séparément après la connexion du canal.

### Démarrer un seul agent

Les bots n'ont pas besoin de démarrer ensemble. Pour la première activation de Développement seul, après démarrage du candidat et attente de son état sain :

```powershell
python infra/configure-telegram.py --agent developpement
python infra/configure-telegram.py --agent developpement --activate
& ./infra/compose.ps1 exec -T openclaw node dist/index.js channels status --probe --channel telegram --json
```

L'option `--agent` peut être répétée. Seuls les tokens sélectionnés sont requis ; aucun compte Asia ou Recherche n'est activé implicitement. L'initialiseur refuse d'écraser un canal déjà actif ou des associations existantes. Pour ajouter un agent après cette première activation, fusionner explicitement sa configuration avec les comptes en place et la valider ; ne pas effacer les associations existantes pour relancer l'initialiseur.

### Ajouter un spécialiste sur une Gateway active

Recherche a été ajouté au pilote existant le 11 octobre 2026 avec cette procédure, après stockage privé et validation de son token :

```powershell
python infra/add-telegram-account.py --agent recherche
python infra/add-telegram-account.py --agent recherche --activate
```

Le premier appel vérifie l'identité, l'absence de webhook, la distinction des bots et le schéma, sans démarrer le consommateur. L'activation exige un agent déjà configuré, refuse tout compte ou association existant et fusionne le nouveau compte en préservant les précédents. Le script compare les configurations avant/après et contrôle la connexion de tous les comptes actifs. Les messages directs sont limités au propriétaire et les groupes désactivés. Aucune limite LiteLLM n'est modifiée.

Un journal privé conserve l'état antérieur. En cas d'échec, le script désactive seulement le compte ajouté et retire sa route Telegram ; les autres bots restent configurés. Ne pas rejouer aveuglément une activation interrompue : examiner le journal et l'état du compte. Une nouvelle activation de compte déjà présent est volontairement refusée. Le bot Recherche actuel est [Rassresearchbot](https://t.me/Rassresearchbot) ; le propriétaire doit ouvrir la conversation et appuyer sur **Démarrer**, puis tester texte, photo et vocal.

Avant la bascule : configurer les associations exactes compte–agent, les messages directs autorisés et le refus des groupes ; démarrer une conversation avec chacun des bots ; vérifier texte, photo, note vocale, réponse au bon bot, isolation et reconnexion. Ne jamais lancer deux consommateurs avec le même token.

## Critères de bascule

- Sauvegarde et restauration vérifiées, ancien service récupérable.
- Chaque bot transféré validé séparément et propriétaire explicitement autorisé ; les bots non encore créés ne bloquent pas les autres.
- Fonctions nécessaires reconnectées, écarts acceptés et documentés.
- Budget de production partagé configuré sans double enveloppe.
- Redémarrage des conteneurs, persistance et retour arrière testés.
- Démarrage Docker après ouverture de session Windows et comportement après veille contrôlés.

La bascule n'est pas automatique à la fin des scripts d'installation. Se référer au [retour arrière](rollback.md) et au [bilan courant](revue-et-tests.md).

La procédure du bot existant est décrite dans [Bascule Asia](bascule-asia.md). Elle ajoute les connecteurs hors Google, un contrôle d'arrêt du superviseur Windows et une transaction de transfert budgétaire. La pause administrateur et la bascule ont été réalisées le 11 octobre 2026. Le runtime courant est `asia-pilot` ; ne pas rejouer les initialiseurs sur cette installation. Les contrôles techniques après transfert sont passés ; les essais utilisateur Telegram et de reprise Windows restent à réaliser.
