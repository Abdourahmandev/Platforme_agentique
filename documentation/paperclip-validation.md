# Bilan de validation Paperclip — 12 octobre 2026

## Résultats exécutés

| Contrôle | Résultat |
| --- | --- |
| Image amont officielle, version et digest | Vérifiés ; image figée dans Compose |
| Premier compte, entreprise, projet, trois profils | Créés dans PostgreSQL dédié |
| Accès HTTPS Tailscale et écran de connexion | Connexion propriétaire et interface Tasks vérifiées dans le navigateur |
| Requête anonyme sur `/api/companies` | Refusée, HTTP 403 |
| Authentification Gateway signée | Protocole 4, scopes `operator.read` et `operator.write` |
| Tentative d'administration Gateway | `config.set` refusé |
| Recherche : mission réelle | EQU-2, trois recommandations publiées sous son identité |
| Asia : coordination réelle | EQU-1, lecture de Recherche et création de la sous-tâche EQU-3 |
| Développement : revue réelle | EQU-3, résultat puis correction après revue superviseur |
| Conversation ordinaire sans tâche | Réponse finale d'Asia ; nombre de tickets inchangé, trois avant/après |
| Demande explicite depuis une conversation | Un seul ticket supplémentaire EQU-4, créé par Asia, traité par Recherche, lien `/EQU/issues/EQU-4` retourné |
| Clôture | Quatre tickets `in_review`, attribués au propriétaire pour validation |
| Recréation puis redémarrage de Paperclip | Compte, entreprise, agents, tickets et commentaires conservés |
| Redémarrage OpenClaw | Plugin chargé, Gateway accessible, trois comptes Telegram `running=true` et `probe.ok=true` |
| Configuration historique | Identique au snapshot avant ajout après retrait des seules entrées du plugin et de l'outil |
| Script Windows de démarrage | Exécuté avec succès avec Paperclip inclus ; aucun redémarrage Windows complet supplémentaire |
| Tests Node | 66 réussis, dont cinq tests Paperclip |
| Tests Python | 50 réussis, dont rejet d'une sauvegarde Paperclip incomplète et nettoyage après échec de restauration |
| Compilation de l'interface existante | Réussie |

Les tests Paperclip couvrent la discussion ordinaire et la négation d'une création, l'interdiction de créer depuis un spécialiste, les liens parent/enfant, l'attribution, l'approbation humaine, la déduplication, le rejet d'un changement de contenu avec le même identifiant, l'arrêt après perte réseau, les limites de projet et de passage, le refus de clôture automatique et l'ordre des commentaires récents.

## Sauvegarde et restauration

Archive vérifiée : `D:\AsiaBackups\docker-20261012T053910-265f50f8.aes`.

- 294 fichiers vérifiés par empreinte.
- Sauvegarde native OpenClaw vérifiée et restaurée dans un emplacement isolé.
- PostgreSQL LiteLLM restauré : 91 tables.
- Volume de données Paperclip extrait dans le dossier privé de vérification.
- PostgreSQL Paperclip restauré dans une base séparée : une entreprise, trois agents, trois tickets et sept commentaires.
- Trois reçus d'approbation et 38 reçus d'exercices préexistants conservés.

L'archive contient la configuration finale du plugin et les secrets nécessaires à la reprise. La base de contrôle et le dossier déchiffré temporaires ont été nettoyés après vérification. La production n'a pas été remplacée.

## Corrections et réserves

1. **Connexion locale après activation HTTPS** : les cookies sécurisés ne sont pas renvoyés sur HTTP. Le client opérateur utilise maintenant l'adresse Tailscale HTTPS. Les données n'avaient pas disparu.
2. **Résultat Développement** : un retry proposé après résultat réseau incertain a été rejeté. Le commentaire corrigé contient `PAPERCLIP_PILOT_DEV_CORRIGE`. Le pseudo-code reste un livrable de revue et n'a pas été déployé ; la protection exécutée est celle du plugin testé.
3. **Commentaires** : l'API les renvoie du plus récent au plus ancien. Le plugin trie avant de sélectionner les 30 derniers.
4. **Liens** : les liens produits par l'outil incluent désormais le préfixe d'entreprise `/EQU`. Les commentaires historiques du premier pilote peuvent encore contenir la première forme de lien ; utiliser les liens natifs des références EQU-1, EQU-2, EQU-3.
5. **Passages annulés au transfert humain** : le moteur amont peut enregistrer `cancelled / issue_reassigned` après publication du résultat et affectation au propriétaire. Les résultats et commentaires sont conservés ; ce compteur ne prouve donc pas un échec du livrable.
6. **Coûts** : lire LiteLLM pour les dépenses et budgets ; le zéro affiché dans Paperclip n'est pas une preuve de gratuité.
7. **Ressources Windows** : Paperclip ajoute deux conteneurs à une machine de 12 Gio de RAM. Les limites mémoire sont configurées ; la disponibilité sous une charge prolongée n'a pas fait l'objet d'un test d'endurance.
8. **Parcours Telegram** : le comportement conversation/ticket a été testé par Gateway dans une session synthétique privée. Il reste à essayer une demande de ticket depuis le téléphone du propriétaire. La réception Telegram est saine ; aucun nouveau message n'a été envoyé au propriétaire par les essais automatisés.

Le test EQU-4 a été ajouté après la restauration de l'archive ci-dessus. Il vérifie la version finale du plugin : création explicite depuis une conversation, attribution à Recherche, lecture, prise en charge, commentaires et transfert humain. La limite mémoire de PostgreSQL a ensuite été relevée de 256 à 512 Mio, l'usage observé étant proche du premier plafond.

Les secrets, traces complètes et identifiants de connexion restent dans `%LOCALAPPDATA%\AsiaPaperclip`. Le [guide Paperclip](paperclip.md) précise les limites d'autorisation, le démarrage et le retour arrière.
