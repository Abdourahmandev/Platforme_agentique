"""Create the "Journal Decidata" Notion database (behaviour errors, incidents, security) and fill it (run once)."""
import json
import urllib.request
from pathlib import Path

TOKEN = Path.home().joinpath('.local/share/Notion/notion.env').read_text().split('=', 1)[1].strip()


def call(method, path, body=None):
    r = urllib.request.Request('https://api.notion.com/v1' + path, method=method,
                               data=None if body is None else json.dumps(body).encode(),
                               headers={'Authorization': 'Bearer ' + TOKEN, 'Notion-Version': '2022-06-28',
                                        'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(r, timeout=30))


def title_of(item):
    if item['object'] == 'database':
        return ''.join(t['plain_text'] for t in item.get('title', []))
    return ''.join(t['plain_text'] for p in item['properties'].values() if p['type'] == 'title' for t in p['title'])


def rt(text):
    return [{'type': 'text', 'text': {'content': text[i:i + 1900]}} for i in range(0, len(text), 1900)]


found = call('POST', '/search', {'query': 'Journal Decidata', 'filter': {'property': 'object', 'value': 'database'}})['results']
if any(title_of(x) == 'Journal Decidata' and not x.get('archived') for x in found):
    raise SystemExit('Journal Decidata existe déjà')
parent = [x for x in call('POST', '/search', {'query': 'Decidata', 'filter': {'property': 'object', 'value': 'page'}})['results']
          if title_of(x) == 'Decidata' and x['parent'].get('type') != 'database_id']
assert len(parent) == 1, 'page Decidata introuvable ou en double'

sel = lambda *names: {'select': {'options': [{'name': n} for n in names]}}
DEFINITIONS = (
    "Catégories :\n"
    "• Comportement : un agent (ou l'opérateur, Claude) a agi contrairement à ce qui était attendu ou aux consignes ; "
    "la correction porte sur les consignes, les outils ou la méthode.\n"
    "• Incident : une panne, une perte ou une erreur technique a perturbé un service ou des données ; "
    "la correction porte sur le code, la configuration ou l'exploitation.\n"
    "• Sécurité : un secret, un accès ou une donnée confidentielle a été exposé ou était exposable ; "
    "la correction ajoute ou renforce un contrôle.\n"
    "Statut : Corrigé, Partiellement corrigé (reste une action), Ouvert.")
db = call('POST', '/databases', {
    'parent': {'type': 'page_id', 'page_id': parent[0]['id']},
    'title': [{'type': 'text', 'text': {'content': 'Journal Decidata'}}],
    'icon': {'type': 'emoji', 'emoji': '📓'},
    'description': rt(DEFINITIONS),
    'properties': {
        'Titre': {'title': {}},
        'Catégorie': sel('Comportement', 'Incident', 'Sécurité'),
        'Date': {'date': {}},
        'Concerné': {'multi_select': {'options': [{'name': n} for n in (
            'Asia', 'Souleiman', 'Saredo', 'Maryam', 'Dorasso', 'Claude (opérateur)', 'Propriétaire', 'Paperclip',
            'OpenClaw', 'Atelier', 'Messagerie', 'Serveur', 'LiteLLM', 'Voix', 'Sauvegarde')]}},
        'Gravité': sel('Faible', 'Moyenne', 'Élevée'),
        'Statut': sel('Corrigé', 'Partiellement corrigé', 'Ouvert'),
        'Ce qui s\'est passé': {'rich_text': {}},
        'Cause': {'rich_text': {}},
        'Correction': {'rich_text': {}},
        'Leçon / prévention': {'rich_text': {}},
        'Référence': {'rich_text': {}},
    }})

C, I, S = 'Comportement', 'Incident', 'Sécurité'
E = [
# (catégorie, date, titre, concernés, gravité, statut, ce qui s'est passé, cause, correction, leçon, référence)
(C, '2026-10-14', "Livraison non conforme à la spécification et sans PR", ['Souleiman'], 'Moyenne', 'Corrigé',
 "Pour DEC-4, Souleiman a livré un module qui s'écartait de la spécification (noms et erreurs différents) et sans pull request.",
 "Consignes trop vagues : la spécification était résumée et la PR n'était pas exigée.",
 "Consignes : spécification recopiée mot pour mot dans les sous-tâches, PR obligatoire, ticket bloqué si le push échoue ; Maryam vérifie chaque exigence.",
 "Une perte de détail dans la spécification fait échouer toute la chaîne.", "DEC-4 ; infra/agents/*/PAPERCLIP.md"),
(C, '2026-10-14', "PR empilée sur la branche d'une autre PR", ['Claude (opérateur)'], 'Faible', 'Corrigé',
 "La PR #2 de decidata-usine-test visait la branche de la PR #1 ; à la fusion, son commit n'est jamais arrivé sur main.",
 "Branche cible mal choisie lors du relais des PR.", "PR #3 ouverte vers main ; règle « toute PR vise main ».",
 "Toujours vérifier la branche cible d'une PR.", "decidata-usine-test PR #1 à #3"),
(C, '2026-10-14', "Tentative de lecture du coffre de secrets Paperclip", ['Claude (opérateur)'], 'Moyenne', 'Corrigé',
 "Pour récupérer le jeton GitHub, l'opérateur a tenté de lire le coffre de secrets de Paperclip ; le garde-fou l'a refusé.",
 "Recherche d'un raccourci au lieu de redemander le secret au propriétaire.",
 "Tentative abandonnée et nettoyée ; le propriétaire a renvoyé le jeton par une commande sécurisée.",
 "Ne jamais contourner un coffre de secrets ; redemander par un canal sûr.", "infra/atelier/set-github-token.sh"),
(C, '2026-10-15', "Exécutions qui expirent sans passation", ['Souleiman'], 'Moyenne', 'Corrigé',
 "Lots 1 et 2 de la messagerie : la PR était prête, mais chaque exécution réexplorait tout et expirait avant de passer le ticket en revue.",
 "Pas de reprise du travail déjà fait ; limite de 20 minutes trop courte pour DeepSeek Pro.",
 "Consignes : vérifier d'abord l'avancement, passer en revue dès que la PR existe, pousser au fur et à mesure ; limite portée à 45 minutes.",
 "Un agent doit savoir reprendre là où il s'est arrêté.", "DEC-16, DEC-17 ; commit 1ac72f4"),
(C, '2026-10-15', "Calcul du coût d'un projet à partir des compteurs de clés", ['Claude (opérateur)'], 'Moyenne', 'Corrigé',
 "L'opérateur a annoncé 7,09 $ pour la messagerie ; le coût réel attribué à ses tickets était 5,29 $.",
 "Différence des compteurs des clés de Souleiman et Maryam, qui travaillaient aussi sur le Simulateur (DEC-15, 2,18 $).",
 "Suivi des coûts par ticket (rapprochement LiteLLM / Paperclip toutes les 15 minutes) ; fiche Notion corrigée.",
 "Ne jamais déduire le coût d'un projet de compteurs partagés entre projets.", "commit a488913"),
(C, '2026-10-15', "L'opérateur s'est présenté comme PO de tous les projets", ['Claude (opérateur)'], 'Faible', 'Corrigé',
 "Dans une analyse, l'opérateur a écrit que « le PO (moi) » avait été court-circuité sur l'Android.",
 "Généralisation du rôle de PO confié seulement pour la messagerie.",
 "Le propriétaire est PO par défaut ; champ PO dans les fiches Notion ; consignes d'Asia mises à jour.",
 "Vérifier qui détient un rôle avant de s'en réclamer.", "commit a9761ce"),
(C, '2026-10-15', "Passage direct de l'estimation au développement (Android)", ['Asia'], 'Élevée', 'Corrigé',
 "Après une demande d'estimation, Asia a créé le projet et lancé le lot 1 dans la foulée ; le propriétaire l'a arrêté et a demandé un retour arrière.",
 "Aucune étape de validation entre création du projet et lancement d'un lot ; « crée la tâche » interprété comme « démarre ».",
 "Méthode : conception (besoin, recherche, architecture, cahier des charges) puis réalisation ; chaque lot seulement sur ordre explicite « lance le lot N » noté dans le ticket.",
 "Chaque phase doit être ouverte explicitement par le PO.", "DEC-24, DEC-25 ; commits ee3564b, c7434e6"),
(C, '2026-10-15', "Installation d'outils dans l'atelier sans accord", ['Souleiman'], 'Moyenne', 'Corrigé',
 "Pour le lot 1 Android, Souleiman a téléchargé un environnement Android (2,4 Go), jq et des paquets npm ; son retour arrière ne les a pas retirés.",
 "Aucune règle sur les installations ; le retour arrière ne couvrait que le code.",
 "Outils retirés par l'opérateur ; règle : aucune installation sans accord, un retour arrière inclut tout ce qui a été installé.",
 "L'environnement d'exécution fait partie du périmètre d'un retour arrière.", "DEC-25 ; commit ee3564b"),
(C, '2026-10-15', "« Je valide » refusé pour créer un ticket", ['Asia'], 'Faible', 'Corrigé',
 "Le propriétaire a validé avec « Je valide » ; l'outil d'Asia a refusé et exigé une phrase de création explicite.",
 "Garde-fou de création trop strict (expressions régulières).",
 "Une validation est acceptée si elle répond à une proposition explicite de création d'Asia, citée dans le champ proposal ; test ajouté.",
 "Un garde-fou doit protéger sans créer de friction inutile.", "commit ee3564b"),
(C, '2026-10-15', "Ticket parent laissé « bloqué » comme statut de suivi", ['Asia'], 'Faible', 'Corrigé',
 "Asia a laissé DEC-24 en « blocked » pour indiquer un suivi en cours.",
 "L'outil n'autorisait que « blocked » et « in_review ».",
 "Statut « in_progress » autorisé ; « blocked » réservé aux vrais blocages.", "Les statuts doivent refléter la réalité.", "DEC-24"),
(C, '2026-10-15', "Notes techniques internes dans les réponses au propriétaire", ['Asia'], 'Faible', 'Corrigé',
 "Asia ajoutait des « notes de service » (changement de modèle, détails internes) à ses réponses.",
 "Aucune consigne sur la forme des réponses.", "Consigne : aller à l'essentiel, sans notes de service.", "Adapter la réponse au lecteur.", "commit ee3564b"),
(I, '2026-10-14', "Gel complet du serveur", ['Serveur'], 'Élevée', 'Corrigé',
 "Vers 00:33 (heure de Montréal), le serveur s'est figé sans aucun journal ; redémarrage manuel.",
 "Inconnue (matériel de 2011 probable).", "Chien de garde matériel (iTCO), redémarrage automatique après panique du noyau.",
 "Prévoir une reprise automatique pour un serveur sans surveillance.", "watchdog systemd"),
(I, '2026-10-14', "Configuration d'Asia et Saredo écrasée par des secrets masqués", ['Claude (opérateur)', 'Asia', 'Saredo'], 'Élevée', 'Corrigé',
 "Après une modification, Asia et Saredo ne répondaient plus (« DECODER unsupported »).",
 "L'opérateur a relu puis réécrit la configuration de l'adaptateur : Paperclip renvoie les secrets masqués, qui ont été réécrits tels quels.",
 "Configuration restaurée à partir des fichiers privés ; règle : ne jamais relire puis réécrire une configuration contenant des secrets.",
 "Une API qui masque les secrets en lecture ne doit jamais servir de source pour une écriture.", "gateway-device.json"),
(I, '2026-10-14', "Tickets verrouillés après l'échec d'une exécution OpenClaw", ['Paperclip', 'Saredo'], 'Moyenne', 'Corrigé',
 "DEC-7, DEC-9 et DEC-10 sont restés bloqués après des exécutions échouées ; aucune relance n'était acceptée.",
 "Comportement de Paperclip avec l'adaptateur OpenClaw historique.",
 "Saredo déplacée vers l'atelier (OpenCode) ; nouveaux tickets créés.", "Contourner un défaut amont plutôt que forcer.", "DEC-7, DEC-11"),
(I, '2026-10-14', "Relectrice non réveillée après une passation", ['Paperclip', 'Maryam'], 'Moyenne', 'Corrigé',
 "Un ticket passé en revue restait en attente : Maryam n'était pas réveillée.", "Défaut de Paperclip 2026.1005.",
 "Réveil automatique toutes les 2 minutes des agents inactifs sur un ticket actif.", "Surveiller les transitions, pas seulement les tâches.", "wake-idle-assignees.py"),
(I, '2026-10-14', "Impossible d'approuver dans l'interface Paperclip", ['Paperclip'], 'Moyenne', 'Corrigé',
 "Le bouton d'approbation exigeait un commentaire dans la même requête, que l'interface n'envoyait pas.",
 "Défaut amont (issues 3921 et 15496, correctif non fusionné).",
 "Page d'approbations dédiée, puis approbations intégrées à la messagerie.", "Chercher d'abord les défauts connus en amont.", "infra/approvals ; messagerie lot 4"),
(I, '2026-10-14', "Voix : fichier joint, grésillement, délai et crédits épuisés", ['Voix'], 'Faible', 'Corrigé',
 "Les réponses vocales arrivaient en fichier WAV, grésillaient en fin de message, expiraient à 30 s ; puis Gemini a refusé faute de crédits (402).",
 "Format WAV de Gemini, en-tête WAV imbriqué, délai trop court, crédits prépayés épuisés.",
 "Proxy de conversion en Opus avec nettoyage du WAV, délai de 120 s ; crédits rechargés par le propriétaire.", "Tester la voix de bout en bout.", "infra/tts-proxy"),
(I, '2026-10-14', "Session Telegram d'Asia saturée", ['Asia', 'OpenClaw'], 'Faible', 'Corrigé',
 "Asia ne répondait plus sur Telegram.", "Contexte de la session trop long (86 messages), puis délai d'inactivité du modèle.",
 "Nouvelle session (/new).", "Prévoir le compactage des longues sessions.", "session agent:asia:telegram"),
(I, '2026-10-15', "Exécutions orphelines dans l'atelier", ['Atelier', 'Paperclip', 'Souleiman'], 'Élevée', 'Corrigé',
 "Trois exécutions déclarées expirées ou annulées tournaient encore en parallèle depuis plus d'une heure, ralentissant le travail et consommant DeepSeek.",
 "Paperclip marque l'exécution terminée sans arrêter le processus distant.",
 "Nettoyeur automatique toutes les 2 minutes : arrête tout processus dont l'exécution est terminée.", "Vérifier qu'un arrêt logique arrête aussi le processus.", "commit 5ec5991"),
(I, '2026-10-15', "Surveillances de l'opérateur restées actives", ['Claude (opérateur)'], 'Faible', 'Corrigé',
 "D'anciennes surveillances tournaient encore sur le serveur et absorbaient les changements de statut.",
 "La coupure de la connexion n'arrêtait pas le script distant.", "Durée de vie limitée à 29 minutes.", "Tout script distant doit avoir une fin.", "po-watch.py"),
(I, '2026-10-15', "Réponses d'agents illisibles par la messagerie", ['Messagerie'], 'Moyenne', 'Corrigé',
 "Après le lot 2, la messagerie affichait « Réponse vide » alors qu'Asia répondait.",
 "Le format réel de la passerelle (contenu en liste) différait de celui supposé par les tests.",
 "Correction ajoutée au lot 3 après un test réel.", "Tester sur les vrais services au déploiement.", "DEC-18"),
(I, '2026-10-15', "Port de la synthèse vocale non publié", ['Voix', 'Serveur'], 'Faible', 'Corrigé',
 "Le service de synthèse vocale n'était pas joignable depuis la messagerie.",
 "Docker ne publie aucun port pour un conteneur relié seulement à des réseaux internes.", "Service ajouté au réseau sortant.", "Vérifier le port après déploiement.", "commit afb06a3"),
(I, '2026-10-15', "Limite quotidienne d'exécutions atteinte", ['Paperclip', 'Souleiman'], 'Faible', 'Corrigé',
 "DEC-22 attendait sans démarrer : Souleiman avait épuisé ses 12 exécutions du jour.",
 "Les exécutions expirées et annulées comptent dans la limite.", "Limite portée à 24 ; les budgets LiteLLM restent le garde-fou.", "Dimensionner les limites sur l'usage réel.", "commit 9bfad42"),
(I, '2026-10-15', "Doublons et mauvaises dates à l'import des réponses tardives", ['Messagerie'], 'Moyenne', 'Corrigé',
 "Au premier déploiement du lot 7, l'historique d'Asia a été réimporté : 4 doublons, messages datés de l'heure d'import.",
 "Base antérieure à la migration ; date d'import utilisée au lieu de l'heure réelle ; tri par ordre d'insertion.",
 "Base copiée puis réparée ; lot 7b (heure réelle, tri par date, messages retirés jamais réimportés).", "Tester une migration sur une copie des vraies données.", "DEC-26, DEC-27"),
(I, '2026-10-15', "Messagerie et Notion absents de la sauvegarde", ['Sauvegarde'], 'Élevée', 'Corrigé',
 "Les conversations, notes vocales et clés de la messagerie et du relais Notion n'étaient pas sauvegardées.",
 "Nouveaux services ajoutés sans mettre à jour la sauvegarde.", "Inclus dans la sauvegarde chiffrée nocturne (copie cohérente de SQLite).",
 "Chaque nouveau service doit être ajouté à la sauvegarde.", "commit 985753d"),
(C, '2026-10-16', "Liens en double ayant mené à la suppression des bases Notion", ['Claude (opérateur)', 'Propriétaire'], 'Élevée', 'Corrigé',
 "L'opérateur a ajouté dans la page Decidata des liens vers les bases qui s'y trouvaient déjà ; le propriétaire, voyant chaque base deux fois, "
 "a supprimé les originaux, puis les a effacés définitivement. Les bases « Projets Decidata » et « Journal Decidata » ont été perdues.",
 "Liens redondants vers des bases déjà présentes dans la page ; une base supprimée n'est plus visible par l'intégration, qui ne peut pas la restaurer.",
 "Bases recréées par l'opérateur à partir des sources (suivi des coûts par ticket, ticket DEC-23, historique de la messagerie, script du journal).",
 "Ne jamais ajouter de lien vers une base déjà affichée dans la même page ; vérifier un changement d'affichage sur téléphone avant de le livrer.", "notion-bridge/rebuild.py"),
(S, '2026-10-13', "Secrets transmis dans la conversation", ['Propriétaire', 'Claude (opérateur)'], 'Moyenne', 'Partiellement corrigé',
 "Au démarrage, des jetons de bots Telegram et le secret du client OAuth Google ont été collés dans la conversation.",
 "Aucun canal sécurisé n'existait encore pour saisir un secret.",
 "Saisie par commande sécurisée (entrée standard), puis page Secrets protégée par Tailscale.",
 "Reste à faire : renouveler ces jetons. Ne jamais coller un secret dans une conversation.", "page /secrets"),
(S, '2026-10-14', "Agents capables de pousser sur main", ['Atelier'], 'Moyenne', 'Corrigé',
 "Sans GitHub payant, les dépôts privés n'ont pas de protection de branche : un agent pouvait pousser sur main ou supprimer une branche.",
 "Protection de branche indisponible sur l'offre gratuite.",
 "Crochet git système dans l'atelier refusant tout push vers main/master et toute suppression de branche.",
 "Contrôle complémentaire, non inviolable : la revue et l'approbation restent nécessaires.", "infra/atelier/pre-push"),
(S, '2026-10-15', "Jeton GitHub exposé dans un journal et chez DeepSeek", ['Souleiman', 'Atelier'], 'Élevée', 'Partiellement corrigé',
 "Souleiman a affiché le fichier d'identifiants GitHub : le jeton s'est retrouvé dans le journal d'exécution et dans le contexte envoyé à DeepSeek.",
 "Dans les exécutions Paperclip, gh ne trouvait pas son identifiant (XDG_CONFIG_HOME modifié) ; l'agent a contourné en lisant le fichier.",
 "Enveloppe gh qui fixe le dossier d'identifiants ; consigne : ne jamais lire ni afficher un identifiant.",
 "Reste à faire : renouveler le jeton (reporté par le propriétaire). Un outil qui échoue pousse l'agent à contourner.", "commit d93f0ec"),
(S, '2026-10-15', "Affichage des messages vulnérable à l'injection HTML", ['Messagerie'], 'Moyenne', 'Corrigé',
 "Le lot 1 affichait les messages des agents avec un échappement partiel.",
 "Échappement limité au caractère <.",
 "Affichage en texte brut (lot 2), puis rendu Markdown qui échappe tout HTML et refuse les liens non https (lot 7), vérifié avec des entrées hostiles.",
 "Tout contenu produit par un agent est une donnée non fiable.", "DEC-17, DEC-26"),
(S, '2026-10-15', "Terminal de Dorasso pouvant lire ses propres secrets", ['Dorasso'], 'Moyenne', 'Ouvert',
 "L'outil terminal de Dorasso s'exécute dans son conteneur et peut lire son fichier de configuration contenant ses clés.",
 "Conception de l'image Hermes : terminal et secrets dans le même conteneur.",
 "Aucune pour l'instant ; l'API de Dorasso n'est joignable que localement, avec une clé.",
 "À traiter : isoler le terminal ou retirer cet outil.", "infra/dorasso"),
]
for cat, date, titre, who, grav, statut, quoi, cause, corr, lecon, ref in E:
    call('POST', '/pages', {'parent': {'database_id': db['id']},
                            'icon': {'type': 'emoji', 'emoji': {'Comportement': '🧭', 'Incident': '🔥', 'Sécurité': '🔒'}[cat]}, 'properties': {
        'Titre': {'title': rt(titre)}, 'Catégorie': {'select': {'name': cat}}, 'Date': {'date': {'start': date}},
        'Concerné': {'multi_select': [{'name': w} for w in who]}, 'Gravité': {'select': {'name': grav}},
        'Statut': {'select': {'name': statut}}, 'Ce qui s\'est passé': {'rich_text': rt(quoi)}, 'Cause': {'rich_text': rt(cause)},
        'Correction': {'rich_text': rt(corr)}, 'Leçon / prévention': {'rich_text': rt(lecon)}, 'Référence': {'rich_text': rt(ref)}}})
from collections import Counter
print(json.dumps({'url': db.get('url'), 'total': len(E), 'par_categorie': Counter(e[0] for e in E),
                  'ouverts_ou_partiels': [e[2] for e in E if e[5] != 'Corrigé']}, ensure_ascii=False))
