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

    def test_unknown_route(self):
        with self.assertRaises(bridge.BridgeError) as ctx:
            bridge.handle('DELETE', '/projects', {})
        self.assertEqual(ctx.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
