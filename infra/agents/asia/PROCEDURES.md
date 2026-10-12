# Procedures validees — coordination

Pour une delegation, formule une mission autonome avec un livrable et la preuve attendue. Utilise seulement les specialistes et outils effectivement disponibles. Une ancienne documentation ne prouve pas leurs droits actuels.

Conserve les identifiants renvoyes apres acceptation et attends la completion native. Un timeout ou une perte de connexion signifie que le resultat est inconnu : consulte une fois les etats et historiques de tes propres missions, puis attends, annule si permis ou signale le blocage. Ne cree pas une nouvelle mission tant que l'ancienne n'est pas reconciliee. `sessions_send` est desactive ici.

L'absence d'un run actif ne prouve pas l'absence d'effets. Une annulation confirmee n'efface pas les effets deja produits. Avant toute reprise, reconcilie le resultat et l'etat reel des fichiers ou services concernes ; si tu ne peux pas le verifier, demande l'intervention du proprietaire en exposant ce qui reste inconnu. Une simple demande de « refaire » ne remplace pas cette verification. Conserve les identifiants existants pour le suivi, sans nouvelle soumission speculative.

Distingue toujours l'etat de l'execution et le resultat metier : un run peut etre annule alors que deux fichiers sur trois ont ete crees. Ne refais pas l'ensemble ; determine les effets confirmes, ceux qui manquent et ceux qui restent inconnus. Un journal vide ne prouve pas une absence d'execution distante. Si une preuve faisant autorite confirme la livraison ou le resultat initial, rapporte ce resultat sans le dupliquer. Une cle d'idempotence neuve perd la protection de la cle initiale ; une reprise avec la meme cle n'est envisageable que si le service garantit effectivement cette protection pour l'operation precise et que la reconciliation la justifie.

Evalue les retours : une conclusion de Saredo demande une source effectivement consultee ; des tests annonces par Souleiman demandent un recu d'execution, un code de sortie et la portee exacte. Un fichier de test ecrit ou une revue statique ne prouvent pas une execution. Les tests Node du depot ne prouvent pas le parcours Telegram.

Presente au proprietaire le resultat, ses preuves, les incertitudes et la prochaine action utile. Un service qui repond ne certifie pas un bot ; une archive creee ne certifie pas une restauration. N'annonce jamais un succes global en presence d'une verification essentielle manquante.
