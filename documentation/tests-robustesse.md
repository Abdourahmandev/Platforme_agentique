# Tests de robustesse et confirmation Telegram

Campagne du 11 octobre 2026 (heure locale), `cycle-4`. Les preuves privées sont conservées dans `%LOCALAPPDATA%/AsiaDocker/training/cycles/cycle-4`. Aucun appel à un modèle ou à Tavily n'est nécessaire pour ces tests.

## Parcours Telegram confirmé par le propriétaire

À la demande d'envoyer un texte aux trois bots, puis une photo et un vocal à Asia, le propriétaire a répondu : « Les trois bots répondent, photo et vocal compris ». Cela confirme ces parcours depuis son compte. Il s'agit d'une déclaration utilisateur, pas d'une observation automatisée des conversations.

Cette confirmation ne couvre pas les boutons d'approbation, la synthèse vocale sortante, les médias des spécialistes ni une mission déléguée complète sur Telegram. Les boutons ont ensuite fait l'objet d'une [campagne distincte réussie](approbations-telegram.md), avec accord unique et refus du propriétaire.

## Défaut reproduit et correction

Le runner sauvegardait le résultat local **après** sa publication dans la Gateway. Une interruption de ce transport pouvait donc perdre le reçu. Le cas initial `bcaadd89d80e4d2eb8bbec26f54987a7` reproduit ce défaut : un seul effet dans la copie de test, aucune réexécution, mais aucun reçu local final avant la récupération.

Le runner écrit maintenant le début et le résultat localement avant toute publication, avec synchronisation du fichier et remplacement atomique. Le résultat contient l'empreinte de la requête complète. Après redémarrage explicite, il republie le même reçu sans exécuter de commande. Un début sans résultat reste inconnu ; une empreinte différente, une preuve corrompue ou une tentative d'écrasement provoque un refus. Un nettoyage non confirmé est signalé dans le résultat.

## Coupures réelles exécutées

| Cas | Identifiant du job | Résultat vérifié |
| --- | --- | --- |
| Transport coupé pendant l'exécution | `30dfc7a940594e8b8b88409ae425761c` | `unknown_after_transport`, reçu local conservé et republié identiquement |
| Transport coupé après réussite, au moment de publier | `bc56946d97c8491693c216d7ee7540a7` | `passed` conservé, reçu identique après reprise |
| Processus Python tué pendant l'exécution | `55045e7feec3478da99c841d973713cb` | `unknown_after_restart`, conteneur orphelin supprimé |

Dans les trois cas, le compteur d'effets reste à un, la copie de travail n'est pas recréée et le conteneur d'exécution a disparu après récupération. Le runner redémarré termine correctement. Ces contrôles vérifient l'absence de double exécution dans les scénarios exercés, pas une garantie universelle « exactement une fois ».

La file de contrôle persistante est hébergée dans un petit conteneur Node officiel, sans réseau, port publié ou clé, limité à 64 Mio. Sa destruction coupe le même transport `docker exec` et fichiers que celui du runner réel. Avec environ 1,1 Gio de mémoire Windows disponible au début, cette méthode évite une seconde Gateway complète. Elle ne constitue **ni un crash du moteur OpenClaw, ni un redémarrage Windows, ni un test de perte électrique**.

Le premier provisionnement a échoué sur l'ordre `chown`/`chmod` avec capacités réduites. L'ordre est corrigé et la préparation a été reprise sur le volume vide, sans modèle ni modification de production. Le journal conserve cet incident.

## Limites, sauvegarde et clôture

| Contrôle | Preuve |
| --- | --- |
| Annulation pendant un travail réel | Job `08aff39645024ee4bbafc3e862f630e5`, `cancelled`, reçu conservé et conteneur supprimé |
| Sortie de 3 Mio | Job `7d0c0539afb34ddc8cd970602dac5db4`, `output_limit`, journal ≤ 2 Mio et réponse ≤ 18 000 octets |
| Délai réel de trois minutes | Job `59fdf7788f2e497fb8fbe6a2ebf06537`, `timed_out` après 182,30 secondes, reçu conservé et conteneur supprimé |
| Régressions locales | 57 tests Node, 47 tests Python, compilation et syntaxes Python/PowerShell réussis |
| Production après les essais | Cinq services sains ; empreinte de configuration et date de démarrage OpenClaw inchangées |
| Fin du cycle | Conteneur de contrôle arrêté, aucun conteneur de formation ou de job en cours ; preuves conservées |

Huit nouveaux tests Python couvrent les reçus après échec de publication, la requête modifiée, le début local sans marqueur distant, la corruption, le refus d'écrasement, le nettoyage défaillant, le refus d'une cible de coupure non dédiée et l'inclusion des reçus dans la sauvegarde. Les tests Node et la compilation existants restent verts.

Les fichiers `jobs/<identifiant>.started.json` et `jobs/<identifiant>.result.json` sont maintenant inclus dans la sauvegarde chiffrée, pour les cycles historiques et nommés. Les snapshots de projet et les journaux volumineux restent exclus. La restauration de contrôle du point `D:\AsiaBackups\docker-20261012T023143-0a77bc0d.aes` a réussi : **246 fichiers vérifiés, dont 38 reçus individuels**, archive native OpenClaw restaurée dans un emplacement distinct et **91 tables PostgreSQL** restaurées dans une base temporaire. Cette sauvegarde inclut le correctif de travail avant son commit Git, ce que son manifeste signale.

Coût d'inférence de cette campagne technique : **0 USD**. Les éventuels échanges personnels du propriétaire avec les bots relèvent de l'usage de production. La campagne ne change aucune permission d'agent et ne qualifie pas leur autonomie générale.

## Reproduire sans toucher aux bots

Choisir un numéro de cycle neuf. `cycle-4` contient déjà les preuves ; ne pas le réutiliser.

```powershell
$env:ASIA_TRAINING_CYCLE = 'cycle-5' # remplacer si déjà utilisé
python -X utf8 infra/training/test_outage.py prepare
python -X utf8 infra/training/test_outage.py verify
python -X utf8 infra/training/test_outage.py limits
python -X utf8 infra/training/test_outage.py close
Remove-Item Env:ASIA_TRAINING_CYCLE
```

Chaque commande doit réussir avant la suivante. `limits` attend réellement trois minutes pour éprouver l'expiration. Les coupures exigent un journal actif de fixture et le label dédié du conteneur. Un numéro existant ou un rapport déjà présent est refusé. La commande `baseline` sert uniquement à reproduire le défaut avec l'ancien runner ; elle échoue volontairement si celui-ci est déjà corrigé.

En cas d'échec, conserver les journaux, arrêter le runner du cycle concerné et inspecter ses jobs avant tout nouvel essai. Ne pas supprimer ses marqueurs pour obtenir une relance. Le conteneur et son volume de contrôle restent conservés après `close`, mais sans redémarrage automatique. Le rollback du code passe par un revert Git après arrêt du runner et réconciliation ; il n'exige aucun transfert de bot ou de budget. Les nouveaux reçus ne doivent pas être réinterprétés avec l'ancien runner.
