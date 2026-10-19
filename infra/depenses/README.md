# Dépenses — D-012

Page propriétaire sans framework, servie sur `127.0.0.1:3112`, uniquement en GET.
Python 3.10+ et psycopg 3 doivent déjà être disponibles pour `/usr/bin/python3`.
Le fichier `page.html` accompagne `server.py` ; CSS et JS sont servis inline avec
un nonce aléatoire par réponse. Polices système, aucune ressource externe.

## Installation sur le serveur Ubuntu

Commandes à exécuter par l'administrateur, non exécutées lors de cette livraison.
Déployer les fichiers dans `/opt/platforme-agentique/infra/depenses`, appartenant
à root et non modifiables par le compte de service (répertoire 0755, fichiers 0644).

```sh
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin depenses-viewer
sudo install -d -o root -g root -m 0700 /etc/depenses
sudo install -o root -g root -m 0600 /dev/null /etc/depenses/page.env
sudoedit /etc/depenses/page.env
```

Contenu du fichier (remplacer les valeurs dans l'éditeur, jamais dans une ligne
de commande, un argument de processus ou Git) :

```ini
ALLOWED_LOGIN=identite-tailscale-du-proprietaire
LEDGER_DSN="host=127.0.0.1 port=5432 dbname=comptabilite user=ledger_dorasso password=SECRET"
```

Utiliser la syntaxe conninfo de libpq et échapper les caractères spéciaux selon
libpq puis EnvironmentFile. systemd lit le fichier root 0600 avant de démarrer
le processus dédié. Ne jamais afficher l'environnement dans les diagnostics.
La connexion PostgreSQL doit être locale (TCP loopback ou socket Unix).
Le rôle `ledger_dorasso` doit avoir uniquement les droits de lecture prévus par
le moteur, sans privilège d'écriture ni appartenance à un rôle d'écriture.
La page vérifie `current_user` et `current_database()` et impose une transaction
`REPEATABLE READ READ ONLY`, en plus du défaut lecture seule de connexion.

```sh
sudo install -o root -g root -m 0644 ops/systemd/depenses.service /etc/systemd/system/depenses.service
sudo systemctl daemon-reload
sudo systemctl enable --now depenses.service
sudo tailscale serve --bg --https=8443 --set-path /depenses http://127.0.0.1:3112/depenses
```

URL : https://rass-server.taild656dc.ts.net:8443/depenses

Le préfixe est conservé. Ne pas exposer le port 3112, ni activer Funnel.
L'identité repose sur l'en-tête injecté par Tailscale Serve : le serveur refuse
les identités absentes, différentes ou répétées. Les processus locaux font
partie de cette frontière de confiance puisqu'ils peuvent joindre le loopback.

## Lecture et incertitudes

API : `/depenses/api?periode=mois&debut=2026-10-01&variables=0`.
Les trois paramètres sont obligatoires et uniques. `debut` doit être le début
calendaire de la période (lundi, premier du mois/trimestre/an).
`variables=1` conserve les sous-catégories déclarées variables dans le détail ;
les groupes hors total, flux non attestés, doublons et dates inconnues restent visibles.
Les agrégats sont calculés par PostgreSQL à partir du seul niveau sous-catégorie
des vues du moteur ; jamais de somme des deux niveaux ni de net entre entrées
et sorties. Un montant inconnu contamine le total, une période absente reste n.d.
Les détails suivent l'ordre SQL décroissant ; le navigateur filtre la sélection
sans recalculer les montants ou compteurs. Les conversions Number servent seulement
aux proportions du dessin et de sa légende. Les textes sont insérés par textContent.

Le contrat livré n'expose **ni horodatage de collecte ni confirmation bancaire ni
fin de revue**. Ces informations restent explicitement n.d./non attestées ;
`calcule_le` n'est pas présenté comme une collecte. Le total complet reste n.d.
Pour afficher une véritable dernière collecte, le moteur devra exposer son
horodatage dans le contrat de lecture. La couverture et la date du calcul sont
affichées ; l'obsolescence est évaluée au jour de Toronto.

## Tests hors réseau

```sh
python -B -m unittest discover -s infra/depenses -p 'test_*.py' -v
```

Base et transport HTTP simulés : aucun socket ni DSN réel nécessaire, aucune
installation. Les tests ne remplacent pas une validation d'intégration contre
les vues déployées ni une vérification visuelle dans un navigateur.

## Accès réseau à la base (constaté à l'installation)

L'unité limite le réseau à `localhost` (`IPAddressAllow=localhost`). La base comptable est sur le réseau
interne Docker (`dorasso-ledger-1`, adresse lue par `docker inspect`) : ajouter **seulement** cette adresse
par un fichier complémentaire, sans élargir le reste :

```sh
IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' dorasso-ledger-1)
sudo install -d -m 0755 /etc/systemd/system/depenses.service.d
printf '[Service]
IPAddressAllow=%s/32
' "$IP" | sudo tee /etc/systemd/system/depenses.service.d/ledger.conf
sudo systemctl daemon-reload && sudo systemctl restart depenses
```

`LEDGER_DSN` s'écrit sous forme d'URI sans espace (`postgresql://ledger_dorasso:MOT_DE_PASSE@IP:5432/comptabilite`) :
une forme `cle=valeur` avec espaces est mal lue. Le service tourne avec son propre environnement Python
(`/opt/depenses/venv`, `psycopg[binary]==3.2.10`), le Python système n'ayant pas le pilote.
