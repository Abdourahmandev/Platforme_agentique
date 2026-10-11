"""Generate the reviewable model inventory from the committed LiteLLM catalogue."""
from pathlib import Path
import yaml

root=Path(__file__).resolve().parents[1]
rows=yaml.safe_load((root/'gateway/config.yaml').read_text(encoding='utf-8'))['model_list']
lines=['# Catalogue des modèles', '',
       'Inventaire généré depuis `gateway/config.yaml` par `python scripts/document-models.py`. Les capacités ci-dessous sont déclarées dans la configuration ; elles ne constituent pas un nouveau test réel de chaque endpoint.', '',
       'Le catalogue contient '+str(len(rows))+' routes, dont '+str(sum(r['model_info']['mode']=='chat' for r in rows))+' conversationnelles. Les modèles spécialisés restent dans LiteLLM mais ne deviennent pas automatiquement des outils OpenClaw. Leur présence au catalogue ne garantit ni le quota fournisseur disponible, ni leur exposition dans Telegram.', '',
       '| Route | Mode | Entrées | Sorties | Outils | JSON Schema |',
       '| --- | --- | --- | --- | --- | --- |']
for row in rows:
    info=row['model_info']
    lines.append('| `'+row['model_name']+'` | '+info['mode']+' | '+', '.join(info.get('input_modalities',[]))+' | '+', '.join(info.get('output_modalities',[]))+' | '+('oui' if info.get('supports_function_calling') else 'non')+' | '+('oui' if info.get('supports_response_schema') else 'non')+' |')
lines += ['', '## Utilisation dans les agents', '',
          'Le défaut OpenClaw est `litellm/asia-auto`. La limite déclarée au moteur est de 128 000 tokens de contexte au maximum et 4 096 tokens de sortie, plus restrictive que certaines limites fournisseur. LiteLLM limite les appels Auto à 8 192 tokens ; la borne demandée par le moteur reste applicable.', '',
          'Les notes vocales passent d’abord par Speaches et deviennent du texte. Le test image a traversé OpenClaw puis LiteLLM. Les capacités PDF/audio/vidéo annoncées dans LiteLLM ne prouvent pas leur prise en charge comme pièces jointes natives par chaque client.', '',
          'Les essais réels antérieurs des 34 routes sont décrits dans [l’état de référence](../docs/operations.md). Les tests propres à la migration sont distingués dans [le bilan](revue-et-tests.md). Aucun test de contexte maximal ni nouvel essai de génération vidéo n’est revendiqué.', '',
          '## Réévaluation', '',
          'Les alias « latest », quotas, capacités et prix évoluent. Revalider une modification contre les API et documentations des fournisseurs, mettre à jour `model_info`, tester les replis, puis régénérer ce tableau. Sources utilisées par le catalogue : [DeepSeek](https://api-docs.deepseek.com/api/list-models/), [Gemini](https://ai.google.dev/gemini-api/docs/models).', '']
(root/'documentation/modeles.md').write_text('\n'.join(lines),encoding='utf-8')
print(f'Documented {len(rows)} model routes')
