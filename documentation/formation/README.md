# Formation supervisee des agents

La formation porte sur les instructions, les methodes de travail et les outils. Aucun poids de DeepSeek/Gemini n'est reentraine. Le superviseur observe les vrais appels et recus, corrige les ecarts et ne retient que les procedures verifiees.

La [reprise ciblee](bilan-reprise.md) utilise desormais une Gateway de formation distincte : volume, appareil operateur, cles et journaux propres, sans Telegram. Ce mode evite de redemarrer les bots. Le fonctionnement historique du premier cycle reste documente plus bas pour comprendre ses preuves et son rollback.

## Nouveau cycle isole

Utiliser un numero neuf : les journaux d'un cycle existant ne doivent jamais etre ecrases. `cycle-2` conserve une preparation en echec sans inference ; `cycle-3` contient la reprise terminee. Les noms de roles `formation-asia` et `formation-developpement` sont reutilisables parce que chaque Gateway possede un volume distinct.

```powershell
$env:ASIA_TRAINING_CYCLE = 'cycle-4' # exemple pour le prochain cycle
python infra/training/isolated.py prepare
node infra/training/probe.mjs
```

Le probe cree un appareil dedie et, au premier passage, conserve son identifiant de demande dans le fichier prive `pairing-request.json`. L'operateur approuve uniquement cet appareil avec la CLI `devices approve` dans le conteneur de ce cycle, puis relance le probe. Aucune cle ni aucun token ne doit etre colle dans Git ou un rapport. L'absence d'appairage n'autorise pas a desactiver l'authentification.

Le plafond du cycle est le minimum entre 0,50 USD, le reste de l'enveloppe initiale de 5 USD, le credit fournisseur moins 0,25 USD et la marge de l'equipe existante. Les depenses de tous les cycles restent comptabilisees, meme leurs cles bloquees. Les campagnes sont en sequence. Les prochains scenarios doivent etre revus par l'operateur avant execution.

Dans un autre terminal portant **la meme variable de cycle**, lancer `python infra/training/runner.py --seconds 3600`. A la racine du depot, executer ensuite `python infra/training/test_mutations.py`, `python infra/training/test_live.py`, puis `python infra/training/evidence.py baseline`. Les dependances des images officielles doivent avoir ete initialisees une fois avec `python infra/training/configure.py dependencies`.

Une mission : `node infra/training/campaign.mjs reprise-asia`. Les missions nommees sont dans `curriculum-followup.json`, jamais dans la copie de travail initiale de l'agent. Un recu existant bloque toute resoumission. Le controle `mutationPaths` peut restreindre les ecritures aux deux tests ou a `[]` pour une mission en lecture seule. Son changement appartient uniquement au superviseur.

Apres les missions, `python infra/training/evidence.py check` compare les fichiers, puis le superviseur examine aussi les appels d'outils. Une comparaison finale ne detecte pas a elle seule une ecriture ensuite effacee. Des fichiers SOUL/USER nouvellement materialises ne sont distingues comme modeles natifs que si leurs hashes correspondent exactement aux fichiers embarques ; les historiques restent a revoir.

Cloture : `python infra/training/isolated.py stop` bloque les cles, arrete le runner, verifie/restaure l'archive native et arrete la Gateway separee. Les volumes, journaux et conteneur arrete sont conserves pour investigation ; un cycle neuf peut utiliser un autre nom. Une erreur de preparation ou d'arret ne declenche ni rejeu d'inference ni suppression de preuves. Examiner le journal avant toute reprise ; des jobs sans resultat doivent etre annules/reconcilies avant l'archivage.

Retirer ensuite la variable du terminal avec `Remove-Item Env:ASIA_TRAINING_CYCLE`. Pour installer des procedures **revues** en production, `python infra/training/promote.py apply --revision cycle-4` cree un journal distinct. Le rollback correspondant utilise `rollback --revision cycle-4` et refuse d'ecraser des modifications ulterieures. La variable de formation doit etre absente pour cette promotion. Terminer par `python ops/backup-docker.py --restore-check` : les cycles et leurs archives natives sont inclus dans la sauvegarde chiffree.

## Programme et roles

Douze missions principales : trois evaluations initiales, six exercices accompagnes et trois evaluations finales, chacune avec trois variantes. Une mission de correction explicite peut suivre un exercice en echec. Les tentatives incompletes restent dans le bilan ; elles ne sont pas effacees pour ameliorer les scores.

- Asia transforme la demande en missions, attend les vrais retours et distingue resultat, preuve et incertitude.
- Recherche consulte les sources primaires et separe documentation actuelle, version installee et observations locales.
- Developpement modifie une copie du depot, execute les tests et rapporte leurs vrais recus. Une suite verte ne suffit pas : le superviseur verifie aussi les contrats et les cas limites.

Les chantiers du premier cycle sont la classification d'une tache interrompue et un diagnostic de sante de la plateforme. Les notes sont sur 100 : exactitude 35, preuves 25, role/outils 20, clarte 10, cout 10. Chaque variante finale doit atteindre 85 et tous les controles critiques doivent passer. Source inventee, fausse annonce de test ou action hors perimetre bloque la validation.

## Architecture et interfaces

Trois identites `formation-asia`, `formation-recherche`, `formation-developpement` utilisent la Gateway existante, avec espaces et cles LiteLLM distincts, sans association Telegram. Seule Asia de formation peut deleguer aux deux specialistes de formation. Les agents habituels conservent leurs droits.

`training_run` est executable uniquement par le developpeur de formation. Asia porte aussi son descripteur et ceux de Tavily pour permettre leur heritage par les sessions deleguees ; les gardes du plugin lui refusent leur execution directe. Son interface est `start` avec `operation` parmi `node_tests`, `python_tests`, `build`, puis `status`/`cancel` avec `jobId`. La Gateway depose un recu prive ; un processus Windows de confiance cree un snapshot et lance Docker. Les agents ne recoivent jamais le client Docker, son socket ou un shell Windows.

Chaque commande s'execute dans un conteneur jetable : reseau externe coupe, utilisateur 1000, racine en lecture seule, capacites supprimees, aucun secret, un processeur, 1 Gio de RAM, 128 processus, trois minutes maximum. Seule la copie jetable du projet est modifiable ; les dependances Node/Python sont montees en lecture seule. Les sorties conservees sont bornees a 2 Mio, avec une fin de journal de 18 000 octets transmise a l'agent.

Le premier cycle a revele une ecriture hors perimetre par `apply_patch`. Le garde de mutation ajoute a la suite de cet incident limite aussi `write`, `edit` et `apply_patch` aux quatre fichiers candidats ; suppressions et deplacements sont interdits. Le bilan conserve l'incident : un controle ajoute apres coup ne transforme pas la tentative initiale en reussite.

Le resultat comprend `jobId`, `status`, `exitCode`, `source_sha256` et la sortie reelle. Les etats sont `passed`, `failed`, `cancelled`, `timed_out`, `output_limit` ou `unknown_after_restart`. Un job marque commence avant une interruption du superviseur n'est jamais rejoue automatiquement. L'outil refuse une mission appartenant a une autre session.

## Budget et limites

Plafond approuve : 5 USD, sans recharge. Le premier cycle est borne a 1,11 USD dans LiteLLM, compte tenu du credit DeepSeek observe de 1,36 USD et de la reserve de 0,25 USD. Trois cles d'inference, expirees apres 24 heures et bloquees en fin de cycle, partagent un meme budget de membre dans l'equipe existante. Les depenses de production ne sont pas remises a zero.

Le superviseur verifie le credit DeepSeek avant les missions et arrete les lancements a 85 % du sous-budget ou a la reserve fournisseur. Le compteur Tavily est conserve au plus cinq minutes pour respecter la limitation de son endpoint d'usage ; une lecture indisponible avec cache perime bloque les nouveaux exercices. Les outils de formation limitent Tavily a vingt appels basic au total, avec trois URL maximum pour l'extraction. Aucun achat de credits n'est prevu.

Les cles de formation restent sur `asia-rapide`. Le callback LiteLLM leur interdit les replis vers Gemini et desactive explicitement la reflexion DeepSeek pour eviter une sortie entierement consommee avant la reponse utile. Ce reglage a ete introduit apres une tentative tronquee ; les comparaisons avant/apres portent donc sur la configuration complete de l'agent, pas sur les seules instructions. [Parametres DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/), [budgets LiteLLM](https://docs.litellm.ai/docs/proxy/users).

Les plafonds comptables peuvent avoir du retard sur les appels en vol ; ils ne constituent pas une reservation bancaire. La marge et les executions en sequence limitent ce risque.

## Exploitation et retour arriere

Depuis la racine du depot, l'initialisation explicite utilise `python infra/training/configure.py dependencies`, puis `apply`. Elle exige une restauration verifiee de moins de 24 heures. Une campagne deja journalisee ne peut pas etre ecrasee : examiner et archiver son etat avant un nouveau provisionnement.

La version OpenClaw installee exige une migration hors ligne des nouvelles cles JSON vers son stockage SQLite. Le script arrete proprement la Gateway, execute le doctor natif et redemarre les bots. Seuls l'horodatage du doctor et l'ajout explicite du plugin Telegram deja actif sont acceptes comme normalisation ; tout autre changement de configuration bloque la suite.

Lancer `python infra/training/runner.py --seconds 7200`, puis une mission avec `node infra/training/campaign.mjs IDENTIFIANT`. Le curriculum de l'operateur reste hors des copies initiales des agents, ainsi que les tests finaux reserves. Les fichiers `PLAYBOOK.md` sont modifies uniquement par le superviseur, puis testes dans de nouvelles sessions.

`python infra/training/configure.py stop` suspend les outils, demande l'annulation des jobs et bloque les cles. `rollback` retire aussi les profils et le plugin de formation, en conservant les autres reglages et la comptabilite. Le retrait utilise l'API native `agents.delete` avec `deleteFiles: false` : les espaces de fichiers restent sur disque, mais OpenClaw purge les entrees de sessions des profils retires. Une sauvegarde chiffree restauree avec succes, plus recente que leurs derniers historiques, est donc obligatoire avant cette etape. Les copies privees des historiques restent conservees. Attendre la fin de l'execution en cours avant une maintenance de la Gateway. Les nouveaux fichiers de code peuvent etre retires par un revert Git independant.

`python infra/training/promote.py apply` installe uniquement les trois fichiers `PROCEDURES.md` revus et leur reference dans `AGENTS.md`. Le journal prive conserve les versions precedentes. `python infra/training/promote.py rollback` restaure ces instructions, apres comparaison pour ne pas ecraser une modification ulterieure. Cette operation est distincte du retrait des profils de formation. Aucun outil d'execution permanent n'est accorde a Developpement par cette promotion.

Pour les verifications independantes : `evaluate.py` compare la copie au snapshot initial et lance les cas reserves dans le conteneur isole. `test_live.py` teste les frontieres d'outils et trois operations ; `test_failures.py` teste une expiration reelle et l'annulation ; `test_recovery.py` simule le journal d'un job orphelin et une sortie trop volumineuse. `test_mutations.py` execute le hook installe dans le conteneur et controle ses refus sans ecrire de fichier. L'endpoint HTTP n'expose pas les outils fichier embarques (404) : ce test du hook ne doit pas etre presente comme un nouvel exercice conversationnel. Ces scripts s'adressent a l'operateur pendant une fenetre de formation, pas aux bots.

Le journal, les cles, les historiques artificiels et les recus sont dans `%LOCALAPPDATA%/AsiaDocker/training`, inclus dans la sauvegarde chiffree pour les fichiers JSON. Les snapshots jetables et caches de dependances sont exclus. Les profils de formation n'obtiennent aucun droit permanent par simple reussite a un exercice.

## Utiliser le diagnostic issu du cycle

`node infra/platform-health.mjs` lit les etats Docker et le dernier rapport de restauration. Il retourne un rapport sans secrets. Codes de sortie : 0 pour `ok`, 1 pour `degraded`, 2 pour `unknown`.

Une observation absente reste inconnue. Le diagnostic ne declenche pas de mission et ne certifie pas Telegram : la delegation reste `unknown` tant qu'aucune preuve de ce parcours n'est fournie. Le classificateur de taches fournit des etats structures aux erreurs de transport du client Gateway ; il ne relance aucune requete.
