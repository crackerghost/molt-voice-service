import unittest
from unittest.mock import patch, MagicMock

import httpx
from server.llm import board_visuals as visuals
from server.llm.diagrams import assemble_board, normalize, DIAGRAM_TOOL


class BoardVisualTests(unittest.TestCase):
    def setUp(self):
        visuals._CACHE.clear()

    def response(self):
        return {'query': {'pages': {'1': {'index': 1, 'title': 'File:Keyboard.jpg', 'imageinfo': [{
            'thumburl': 'https://upload.wikimedia.org/keyboard.jpg',
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Keyboard.jpg',
            'extmetadata': {'Artist': {'value': '<a href="/user">Example Author</a>'}, 'LicenseShortName': {'value': 'CC BY-SA 4.0'}},
        }]}}}}

    def client(self, data=None):
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value.json.return_value = data if data is not None else self.response()
        return client

    def test_real_lookup_metadata_is_retained_and_cached(self):
        client = self.client()
        with patch.object(visuals.httpx, 'Client', return_value=client):
            result = visuals.search_image('keyboard')
            self.assertEqual(result['credit'], 'Example Author · CC BY-SA 4.0')
            self.assertEqual(result['sourceUrl'], 'https://commons.wikimedia.org/wiki/File:Keyboard.jpg')
            self.assertEqual(result, visuals.search_image('keyboard'))
        self.assertEqual(client.get.call_count, 1)
        self.assertEqual(client.get.call_args.args[0], 'https://commons.wikimedia.org/w/api.php')

    def test_lookup_failure_is_cached_and_does_not_break_board(self):
        client = self.client()
        client.get.side_effect = httpx.ReadTimeout('unavailable')
        with patch.object(visuals.httpx, 'Client', return_value=client):
            board = assemble_board({'elements': [{'id': 'reference', 'type': 'image', 'query': 'keyboard'}]}, id_prefix='test', turn_id='')
            self.assertEqual(board['elements'][0]['type'], 'note')
            self.assertIn('unavailable', board['elements'][0]['text'])
            self.assertIsNone(visuals.search_image('keyboard'))
        self.assertEqual(client.get.call_count, 1)

    def test_query_resolution_never_invents_image_region_coordinates(self):
        with patch.object(visuals, 'search_image', return_value={'src': 'https://example.com/key.jpg', 'alt': 'Keyboard'}):
            data = visuals.resolve_images({'elements': [{'id': 'x', 'type': 'image', 'query': 'keyboard', 'regions': [{'id': 'guessed'}], 'activeRegion': 'guessed'}]})
        self.assertNotIn('regions', data['elements'][0])
        self.assertEqual(data['elements'][0]['src'], 'https://example.com/key.jpg')

    def test_one_lookup_per_board_and_known_assets_do_not_search(self):
        with patch.object(visuals, 'search_image', return_value=None) as search:
            visuals.resolve_images({'elements': [{'id': 'a', 'type': 'image', 'src': '/known.svg'}, {'id': 'b', 'type': 'image', 'query': 'keyboard'}, {'id': 'c', 'type': 'image', 'query': 'monitor'}]})
        self.assertEqual(search.call_count, 1)

    def test_missing_license_and_executable_media_are_rejected(self):
        for license_name, url in [('All rights reserved', 'https://example.com/image.jpg'), ('CC BY-SA 4.0', 'javascript:alert(1)')]:
            data = self.response()
            info = data['query']['pages']['1']['imageinfo'][0]
            info['extmetadata']['LicenseShortName']['value'] = license_name
            info['thumburl'] = url
            with patch.object(visuals.httpx, 'Client', return_value=self.client(data)):
                self.assertIsNone(visuals.search_image(f'keyboard {license_name}'))

    def test_scene_survives_assembly_without_shape_labels(self):
        board = assemble_board({'elements': [{'id': 'array', 'type': 'scene', 'kind': 'array', 'items': [{'id': 'a', 'value': '4'}], 'active': [0], 'pointers': [{'label': 'i', 'index': 0}]}]}, id_prefix='one', turn_id='')
        self.assertEqual(board['elements'][0]['items'][0]['value'], '4')
        self.assertEqual(board['elements'][0]['active'], [0])

    def test_scene_key_updates_the_same_visual_across_windows_and_isolates_turns(self):
        data = {'elements': [{'id': 'scores', 'sceneKey': 'scores', 'type': 'scene', 'kind': 'array', 'items': [{'id': 'a', 'value': '4'}]}]}
        first = assemble_board(data, id_prefix='w1', turn_id='turn-one')
        second = assemble_board(data, id_prefix='w2', turn_id='turn-one')
        other = assemble_board(data, id_prefix='w1', turn_id='turn-two')
        self.assertEqual(first['elements'][0]['id'], second['elements'][0]['id'])
        self.assertNotEqual(first['elements'][0]['id'], other['elements'][0]['id'])

    def test_invalid_regions_and_scenes_do_not_reach_the_renderer(self):
        image = normalize({'elements': [{'id': 'image', 'type': 'image', 'src': '/known.svg', 'regions': [None, {'id': 'bad', 'x': .9, 'y': 0, 'width': .5, 'height': 1}, {'id': 'ok', 'x': .1, 'y': .2, 'width': .2, 'height': .3}], 'activeRegion': 'ok'}]})
        self.assertEqual(len(image['elements'][0]['regions']), 1)
        for item in [{'kind': 'unknown'}, {'kind': 'array', 'items': [None]}, {'kind': 'nodes', 'nodes': []}, {'kind': 'array', 'items': [{'id': 'a'}, {'id': 'a'}]}]:
            self.assertIsNone(normalize({'elements': [{'id': 'bad', 'type': 'scene', **item}]}))

    def test_numeric_bounds_and_dangling_edges(self):
        scene = visuals.normalize_scene({'kind': 'nodes', 'nodes': [{'id': 'a', 'label': 'One', 'x': float('nan'), 'y': float('inf')}], 'edges': [{'from': 'a', 'to': 'missing'}]})
        self.assertEqual(scene['nodes'][0]['x'], .5)
        self.assertEqual(scene['edges'], [])
        self.assertEqual(visuals.normalize_scene({'kind': 'box-model', 'padding': 500})['padding'], 64)

    def test_tool_exposes_complete_visual_and_image_contract(self):
        fields = DIAGRAM_TOOL['function']['parameters']['properties']['elements']['items']['properties']
        for name in ['kind', 'items', 'pointers', 'sceneKey', 'regions', 'activeRegion', 'query']:
            self.assertIn(name, fields)


if __name__ == '__main__':
    unittest.main()
