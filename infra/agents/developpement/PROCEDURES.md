# Procedures validees — developpement

Avant de proposer un changement, explicite le contrat et les fichiers concernes. Verifie les valeurs absentes, nulles, de mauvais type, les erreurs de transport et les champs supplementaires. Ne transforme pas une valeur absente en succes par coercition. Une issue inconnue n'autorise pas une relance automatique.

Les tests doivent couvrir des erreurs possibles et pas seulement reproduire le code. Conserve les echecs dans ton compte rendu. Ne change une assertion que si son ancien comportement contredit le contrat, en expliquant pourquoi ; ne l'affaiblis pas pour obtenir une suite verte.

Utilise seulement un executeur effectivement disponible. Dans le profil habituel, le shell et le bac a sable de formation ne sont pas exposes : une lecture de code reste une revue statique. Si un executeur est ajoute plus tard, rapporte son identifiant de tache, son code de sortie reel, les tests lances et la version des fichiers testes.

Ne declare pas de verification complete a partir d'une commande proposee, d'un fichier de test ou d'un message d'un autre agent. Distingue tests unitaires, compilation, integration et parcours Telegram. Ne revele aucun champ secret dans les rapports de diagnostic.
