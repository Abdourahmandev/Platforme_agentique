"""Rebuild the Notion "Projets Decidata" database and its three project pages after their permanent deletion (2026-10-16)."""
import importlib.util
import json
import os
import re
from pathlib import Path

os.environ.setdefault('NOTION_TOKEN_FILE', str(Path.home() / '.local/share/Notion/notion.env'))
spec = importlib.util.spec_from_file_location('bridge', Path.home() / 'Platforme_agentique/infra/notion-bridge/server.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
src = json.loads(Path('/tmp/rebuild-src.json').read_text())

db = bridge.database(create=True)
existing = {p['name'] for p in bridge.handle('GET', '/projects', {})[1]['projects']}


def icon(page_id, emoji):
    bridge.notion('PATCH', f'/pages/{page_id}', {'icon': {'type': 'emoji', 'emoji': emoji}})


def project(fields, emoji, sections):
    if fields['name'] in existing:
        print('existe deja :', fields['name']); return
    status, page = bridge.handle('POST', '/projects', {'fields': fields})
    icon(page['id'], emoji)
    for title, text in sections:
        bridge.handle('POST', f"/projects/{page['id']}/sections", {'title': title, 'text': text})
    print('recree :', fields['name'], '-', len(sections), 'sections')


costs = {r[0]: r for r in src['costs']}
lots = ['DEC-16', 'DEC-17', 'DEC-18', 'DEC-19', 'DEC-20', 'DEC-21', 'DEC-26', 'DEC-27']
docs = ['DEC-22', 'DEC-23']
money = lambda v: f'{v:.2f} $'.replace('.', ',')
total_lots = sum(costs[k][3] for k in lots); total_docs = sum(costs[k][3] for k in docs)

# Saredo's overview (DEC-23) with the PO corrections already applied when first published.
saredo = src['saredo']
fixes = [("une ligne chiffrée exclusive", "une ligne protégée par une clé"),
         ("en reconnaissant sans faute les noms propres", "en reconnaissant mieux les noms propres"),
         ("Pour sauvegarder l'intégralité de vos conversations et réglages, il suffit de copier ce dossier.",
          "Les conversations, les notes vocales et les réglages sont inclus dans la sauvegarde chiffrée automatique de chaque nuit (3 h)."),
         ("(DeepSeek pour Asia, Gemini pour Saredo, Dorasso et la voix Kore)",
          "(DeepSeek ou Gemini selon l'agent ; Gemini uniquement pour Dorasso et pour la voix Kore)")]
applied = 0
for a, b in fixes:
    if a in saredo:
        saredo = saredo.replace(a, b); applied += 1
print('corrections appliquees a la vue d ensemble :', applied, '/', len(fixes))
overview = saredo[saredo.index('## 2.'):saredo.index('## 3. Tableau')]
conclusion = saredo[saredo.index('## 1. Conclusion courte'):saredo.index('## 2.')].split('\n', 1)[1].strip().strip('-').strip()
parts = re.split(r'\n### (\d\. [^\n]+)\n', overview)
clean = lambda t: re.sub(r'\*\*|`', '', t).replace('\n---', '').strip()
overview_sections = [("Vue d'ensemble pour le propriétaire", clean(conclusion))]
names = {'1': "1. À quoi sert l'application", '2': '2. Les grandes pièces (le standard privé)',
         '3': "3. Le trajet d'un message et d'une note vocale", '4': "4. Ce qui protège l'application",
         '5': '5. Coûts et limites', '6': '6. Glossaire'}
for i in range(1, len(parts), 2):
    overview_sections.append((names.get(parts[i][0], parts[i]), clean(parts[i + 1])))

lot_lines = '\n'.join(f'- {k} {costs[k][1]} : {money(costs[k][3])}' for k in lots)
project({'name': 'Messagerie (web)', 'po': 'Claude (délégué par le propriétaire)', 'status': 'Termine',
         'repo': 'https://github.com/Abdourahmandev/decidata-messagerie', 'start': '2026-10-15', 'end': '2026-10-16',
         'lots': len(lots), 'realCost': round(total_lots + total_docs, 2), 'realDays': 1,
         'summary': "Application web privée (Tailscale) pour discuter avec Asia, Souleiman, Saredo, Maryam et Dorasso : conversations, notes vocales, approbations Paperclip et budgets IA."},
        '💬', [
    ('Contexte', "Demande du propriétaire : une application maison pour parler à tous les agents. Maquette approuvée, PO délégué : Claude. "
                 "Équipe : Asia (cheffe de projet), Souleiman (développement), Maryam (QA). Pas d'estimation de départ : le processus "
                 "d'estimation a été décidé pendant le projet."),
    ('Lots de travail', lot_lines + f"\n\nTotal des lots : {money(total_lots)}."),
    ('Documentation', f"- DEC-22 Documentation technique et guide d'exploitation (dépôt GitHub, docs/) : {money(costs['DEC-22'][3])}\n"
                      f"- DEC-23 Vue d'ensemble pour le propriétaire (sections ci-dessous) : {money(costs['DEC-23'][3])}"),
    ('Bilan', f"Coût réel attribué aux tickets : {money(total_lots + total_docs)} (lots {money(total_lots)}, documentation {money(total_docs)}), "
              "suivi automatique par ticket depuis LiteLLM. S'y ajoutent environ 0,26 $ de messages à Asia non rattachés à un ticket. "
              "Lots 1 à 6 : 5,29 $ ; environ 1 $ perdu en exécutions expirées ou orphelines avant le nettoyeur automatique.\n\n"
              "- Compter environ 0,40 à 1,80 $ par lot (développement et revue).\n- La revue QA coûte presque autant que le développement.\n"
              "- Découper en petits lots livrables.\n- Tester sur les vrais services au déploiement (bugs trouvés aux lots 3 et 7)."),
    *overview_sections,
])

android = src['android']
project({'name': 'App Android (en pause)', 'po': 'Propriétaire', 'status': 'En pause', 'start': '2026-10-15',
         'estimateCost': 7.25, 'estimateDays': 1.25, 'realCost': round(costs['DEC-24'][3] + costs['DEC-25'][3], 2),
         'summary': "Transformer la messagerie en application Android ; mis en pause après un lancement prématuré du lot 1."},
        '📱', [
    ('Estimation (Asia)', clean(android)[:9000]),
    ('Mise en pause (15 octobre)', f"Le propriétaire a arrêté le lot 1 : l'estimation ne devait pas partir directement en développement. "
                                   f"Code annulé (revert, PR #9 fermée), outils Android retirés de l'atelier. Coût de l'essai : "
                                   f"{money(costs['DEC-24'][3] + costs['DEC-25'][3])} (DEC-24 et DEC-25).\n\n"
                                   "À revoir avant toute reprise : passer par la phase de conception et comparer avec une application web installable (PWA)."),
])

project({'name': 'Vitrine technique', 'po': 'Propriétaire', 'status': 'Conception', 'start': '2026-10-16', 'lots': 7, 'estimateCost': 15,
         'summary': "Démontrer la fiabilité, la contribution personnelle et l'exploitation de la plateforme agentique : tableau de bord de fiabilité, "
                    "banc d'évaluation, étude de cas et dépôt public, supervision, mesures de gains, pilote Jev."},
        '🏆', [
    ('Backlog et objectifs', "Le backlog est dans Paperclip, projet Conception, en statut backlog. Rien ne démarre sans l'ordre du propriétaire (« lance ... »).\n\n"
                             "- DEC-28 Préalables LinkedIn (DEC-34, DEC-35)\n- DEC-29 A. Tableau de bord de fiabilité : codé par le propriétaire, relu par l'équipe\n"
                             "- DEC-30 B. Banc d'évaluation\n- DEC-31 C. Étude de cas et dépôt public\n- DEC-32 D. Supervision et disponibilité\n"
                             "- DEC-33 E. Mesures Desjardins\n- DEC-62 F. Pilote Jev (DEC-63 à DEC-70)\n\n"
                             "Origine : retour d'un agent recruteur sur le profil LinkedIn (7,5/10) : bénéfices peu mesurés, qualité des agents non démontrée, "
                             "contribution personnelle à prouver, exploitation durable à valider.\n\nCoût IA estimé : environ 15 $ ; 2 à 3 semaines à temps partiel."),
    ('Pilote Jev : principe', "Jev (TypeSafe AI, 15 septembre 2026) est un modèle de décision : il ne génère pas de texte, il répond à des questions typées "
                              "(choix, oui/non, score) avec une probabilité. Usage courant : « le LLM écrit, Jev décide, le code agit ».\n\n"
                              "Limites : chiffres surtout fournis par l'éditeur ; faible en calcul, dates et documents croisés ; API hébergée aux États-Unis "
                              "en accès anticipé ; environ 0,042 $ par million de tokens ; seuils à calibrer, mode observation recommandé."),
    ('Pilote Jev : trois décisions testées', "- 1. La demande de création de tâche est-elle explicite ?\n- 2. L'exécution est-elle vraiment terminée ? "
                                             "(PR prête / en cours / bloqué / échec)\n- 3. Cette erreur est-elle une vraie panne ? (panne / dégradé / bruit)"),
    ('Pilote Jev : déroulement', "- Deux semaines en mode observation : Jev décide en parallèle, rien ne change dans le fonctionnement réel.\n"
                                 "- Rapport de calibration : taux d'accord, faux positifs et négatifs, coût, seuil recommandé.\n"
                                 "- Activation progressive sur décision du PO seulement.\n\nConfidentialité : jamais de données de Dorasso ni de "
                                 "données personnelles envoyées à Jev. Clé entrée par la page Secrets au lancement."),
])
bridge.notion('PATCH', f'/databases/{db}', {'icon': {'type': 'emoji', 'emoji': '🗂️'}})
print('base projets :', db)
