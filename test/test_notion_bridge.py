import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('notion_bridge', ROOT / 'infra/notion-bridge/server.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
DB = 'a' * 32


class NotionBridgeTest(unittest.TestCase):
    def setUp(self):
        bridge.STATE['db'] = DB
        self.env = mock.patch.dict(os.environ, {'BRIDGE_KEY': 'k'})
        self.env.start()
        self.tok = mock.patch.object(bridge, 'token', return_value='ntn_test')
        self.tok.start()

    def tearDown(self):
        self.env.stop()
        self.tok.stop()

    def test_properties_validate_fields(self):
        props = bridge.properties({'name': 'Messagerie', 'status': 'Termine', 'realCost': 7.09,
                                   'start': '2026-10-15', 'repo': 'https://github.com/x/y'}, True)
        self.assertEqual(props['Cout reel ($)'], {'number': 7.09})
        self.assertEqual(props['Statut'], {'select': {'name': 'Termine'}})
        for bad in ({'unknown': 1}, {'status': 'Fini'}, {'realCost': '7'}, {'start': '15/10/2026'},
                    {'repo': 'http://x'}):
            with self.assertRaises(bridge.BridgeError):
                bridge.properties(dict(bad, name='x'), True)
        with self.assertRaises(bridge.BridgeError):
            bridge.properties({'status': 'Termine'}, True)  # name required on create

    def test_blocks_paragraphs_and_bullets(self):
        out = bridge.blocks('Bilan', 'Premier paragraphe\nsuite.\n\n- point un\n- point deux')
        self.assertEqual([b['type'] for b in out], ['heading_2', 'paragraph', 'bulleted_list_item', 'bulleted_list_item'])
        self.assertEqual(out[1]['paragraph']['rich_text'][0]['text']['content'], 'Premier paragraphe suite.')

    def test_blocks_markdown_rendering(self):
        md = ("### Titre\n1. premier\n2. **second** avec `code`\n\n| A | B |\n|---|---|\n| <b>x</b> | 2 |\n\n"
              "<details>\n<summary>Plus</summary>\n\n- cache\n</details>\nVoir https://example.com/x et <script>alert(1)</script>")
        out = bridge.blocks('S', md)
        self.assertEqual([b['type'] for b in out],
                         ['heading_2', 'heading_3', 'numbered_list_item', 'numbered_list_item', 'table', 'toggle', 'paragraph'])
        second = out[3]['numbered_list_item']['rich_text']
        self.assertEqual([t.get('annotations', {}) for t in second][:3], [{'bold': True}, {}, {'code': True}])
        cell = out[4]['table']['children'][1]['table_row']['cells'][0][0]['text']['content']
        self.assertEqual(cell, '<b>x</b>')  # HTML stays text
        self.assertEqual(out[5]['toggle']['children'][0]['type'], 'bulleted_list_item')
        last = out[6]['paragraph']['rich_text']
        self.assertTrue(any(t['text'].get('link') for t in last))
        self.assertIn('<script>', ''.join(t['text']['content'] for t in last))

    def test_rejects_pages_outside_the_database(self):
        other = {'parent': {'type': 'database_id', 'database_id': 'b' * 32}}
        with mock.patch.object(bridge, 'notion', return_value=other):
            with self.assertRaises(bridge.BridgeError) as ctx:
                bridge.handle('PATCH', '/projects/' + 'c' * 32, {'fields': {'realCost': 1}})
        self.assertEqual(ctx.exception.status, 403)

    def test_updates_a_page_of_the_database(self):
        calls = []

        def fake(method, path, body=None):
            calls.append((method, path))
            if method == 'GET':
                return {'parent': {'type': 'database_id', 'database_id': DB}}
            return {'id': 'c' * 32, 'properties': {}}
        with mock.patch.object(bridge, 'notion', side_effect=fake):
            status, _ = bridge.handle('PATCH', '/projects/' + 'c' * 32, {'fields': {'realCost': 7.09}})
        self.assertEqual(status, 200)
        self.assertEqual(calls[-1], ('PATCH', '/pages/' + 'c' * 32))

    def test_create_refuses_duplicates(self):
        with mock.patch.object(bridge, 'notion', return_value={'results': [{'id': 'd' * 32}]}):
            with self.assertRaises(bridge.BridgeError) as ctx:
                bridge.handle('POST', '/projects', {'fields': {'name': 'Messagerie'}})
        self.assertEqual(ctx.exception.status, 409)

    def test_adds_missing_columns_to_existing_database(self):
        bridge.STATE['db'] = None
        existing = {'id': DB, 'title': [{'plain_text': bridge.DB_TITLE}],
                    'properties': {k: bridge.SCHEMA[k] for k in bridge.SCHEMA if k != 'PO'}}
        calls = []

        def fake(method, path, body=None):
            calls.append((method, path, body))
            return {'results': [existing]} if path == '/search' else {}
        with mock.patch.object(bridge, 'notion', side_effect=fake):
            self.assertEqual(bridge.database(), DB)
        self.assertEqual(calls[-1], ('PATCH', f'/databases/{DB}', {'properties': {'PO': {'rich_text': {}}}}))

    def test_adds_new_statuses_to_existing_database(self):
        bridge.STATE['db'] = None
        props = {k: {} for k in bridge.SCHEMA}
        props['Statut'] = {'select': {'options': [{'name': 'Estimation'}, {'name': 'En cours'}]}}
        existing = {'id': DB, 'title': [{'plain_text': bridge.DB_TITLE}], 'properties': props}
        calls = []

        def fake(method, path, body=None):
            calls.append((method, path, body))
            return {'results': [existing]} if path == '/search' else {}
        with mock.patch.object(bridge, 'notion', side_effect=fake):
            bridge.database()
        names = [o['name'] for o in calls[-1][2]['properties']['Statut']['select']['options']]
        self.assertIn('Besoin', names)
        self.assertIn('Conception', names)

    def test_unknown_route(self):
        with self.assertRaises(bridge.BridgeError) as ctx:
            bridge.handle('DELETE', '/projects', {})
        self.assertEqual(ctx.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
