# Accord Gmail — D-010

Page dédiée au propriétaire, bibliothèque standard Python 3.11+ sous Linux avec
la base de fuseaux système (`America/Toronto`). Écoute exclusivement sur
127.0.0.1:3111. Le service hôte demeure seul responsable de Gmail, de la politique,
de l'expiration et des transitions durables. Lire `.draft-protocol.md` en entier
avant installation. Aucune installation n'est effectuée par ce changement.

## Installation par Claude

Installer le code dans `/opt/platforme-agentique` (ou adapter les deux chemins
de l'unité), propriétaire root, non modifiable par Hermes ou drafts-approver.
Provisionner le groupe `dorasso-approvals` s'il n'existe pas, puis :

```sh
useradd --system --user-group --no-create-home --shell /usr/sbin/nologin drafts-approver
usermod -aG dorasso-approvals drafts-approver
id drafts-approver
install -d -o root -g root -m 0700 /etc/gmail-approvals
install -o root -g root -m 0600 /dev/null /etc/gmail-approvals/page.env
```

Créer `page.env` seulement à la première installation (ne pas écraser une
configuration existante). Y définir la connexion Tailscale exacte du propriétaire :

```ini
ALLOWED_LOGIN=proprietaire@example.org
```

Le fichier est lu par systemd, pas directement par l'utilisateur de la page.
Configurer **APPROVAL_UID avec l'UID numérique de drafts-approver** dans
`/etc/dorasso-gmail/drafts.env` du service hôte ; `APPROVAL_GID` est le GID du
groupe dorasso-approvals. L'UID doit être non root, distinct de celui d'Hermes.
L'appartenance au groupe seule ne suffit pas : l'hôte vérifie SO_PEERCRED.
La page ne doit appartenir ni à dorasso-drafts, ni aux groupes Docker/sudo.
Vérifier `/run/dorasso-approvals` (0750, gmail-connector:dorasso-approvals),
son socket `api.sock` (0660), et l'absence de montage de cette porte dans Hermes.
Ne pas donner à la page l'accès au stockage Gmail, aux secrets ou aux pièces source.

```sh
install -o root -g root -m 0644 ops/systemd/gmail-approvals.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gmail-approvals.service
tailscale serve --https=8443 --set-path /gmail http://127.0.0.1:3111
tailscale serve status
```

Conserver les autres routes du port 8443 : ne pas exécuter `tailscale serve reset`.
Vérifier après publication que `/gmail/<id>` atteint cette page et que la page
actuelle reste accessible sur les autres chemins. L'origine des formulaires est
fixée à `https://rass-server.taild656dc.ts.net:8443` ; le préfixe `/gmail` doit être
conservé par le proxy. Ne pas activer Funnel. L'identité provient exclusivement
des en-têtes injectés par Tailscale Serve ; les processus locaux capables de se
connecter au loopback font partie de la frontière de confiance. Ne jamais exposer
ce serveur directement ou via un proxy laissant passer une identité client forgée.

L'unité n'a aucun ReadWritePaths : elle n'écrit aucun fichier et peut se connecter
au socket Unix avec ProtectSystem=strict. Les jetons sont en mémoire, consommés
sous verrou, liés à la demande, à l'empreinte et à l'action, valides 5 minutes ;
un redémarrage les invalide. La durée du brouillon reste celle imposée par l'hôte.

## Notification du service hôte

Rendre ce dossier disponible dans le PYTHONPATH **du service de brouillons**
(code de confiance non modifiable par Hermes). Ajouter à son fichier
`/etc/dorasso-gmail/drafts.env`, root:root 0600 :

```ini
NOTIFY_CALLBACK=notify:notify
TELEGRAM_BOT_TOKEN=VALEUR_DU_BOT_ASIA
TELEGRAM_OWNER_ID=IDENTIFIANT_NUMERIQUE_DU_PROPRIETAIRE
```

Ne pas mettre ces secrets dans page.env, le dépôt ou `item`. Le callback envoie
du texte brut sans parse_mode ni bouton Telegram ; les aperçus de liens sont
désactivés. Destinataires, objet et résumé sont bornés pour Telegram, uniquement
dans la notification. Le lien vient de `item['url']`. Timeout réseau 5 secondes,
réponse bornée à 64 Kio, aucune relance ; l'erreur remontée est fixe, sans exception
source ni secret. Le timeout urllib est un timeout d'opération réseau, pas une
garantie de durée totale face à un DNS lent ou un serveur envoyant au compte-gouttes.

## Fonctionnement et limites

GET ne demande que `read`, sans effet Gmail. L'affichage conserve tout le corps,
tous les To/Cc et toutes les pièces, échappe le texte et vérifie le SHA-256 du MIME
décodé. Un script local à nonce ne fait qu'afficher le compte à rebours ; aucun
contenu du courriel ne devient du code. Les pièces sont téléchargées comme octets,
avec contrôle de taille et d'empreinte, jamais affichées comme HTML actif.
Les POST imposent identité et jeton à usage unique ; une origine présente doit
correspondre exactement à l'origine publique (comme la page existante, l'absence
d'Origin est tolérée avec jeton valide). Les réponses ne sont pas mises en cache.
Les journaux HTTP sont désactivés pour ne divulguer ni courriel ni jeton.

La page n'édite rien, ne crée aucun brouillon, ne reconstruit pas de MIME, ne fait
aucun appel Gmail direct et ne permet aucun accord Telegram. Elle ne change pas
phase5. `approved_dry_run` apparaît comme « approuvé, non envoyé (examen à blanc) ».
Les boutons indisponibles sont désactivés ; l'hôte tranche toujours. Après un
résultat inconnu, consulter l'état, sans réessai automatique. Après `draft_changed`,
créer un nouveau brouillon et une nouvelle demande. Une connexion Unix a une
échéance absolue de 5 secondes et une réponse limitée à 64 Mio, LF compris.

## Tests locaux sans services externes

```sh
python3 -B -m unittest discover -s infra/gmail-approvals -p 'test_*.py' -v
```

Les tests utilisent seulement un socket Unix temporaire, HTTP loopback et un
transport Telegram simulé. Sous Python Windows sans AF_UNIX, la même porte simulée
utilise TCP loopback pour vérifier HTTP et le protocole ; cela ne valide pas le
transport Unix, et les tests doivent être rejoués sous Linux.
Ils ne prouvent ni SO_PEERCRED côté service hôte ni
l'injection d'identité par Tailscale : contrôler ces deux points sur Linux au
déploiement, ainsi que le maintien des routes existantes et l'examen à blanc.
