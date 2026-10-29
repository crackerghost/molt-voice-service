import unittest

from server.llm.diagrams import assemble_board, normalize, DIAGRAM_TOOL, _step_prompt


class RichBoardTests(unittest.TestCase):
    def test_source_is_separated_from_concept_shapes(self):
        board = assemble_board({"elements": [
            {"id": "concept", "type": "rectangle", "text": "<h1>\\nopening tag"},
            {"id": "source", "type": "rectangle", "text": "const value = 42;"},
            {"id": "edge", "type": "arrow", "startNodeId": "concept", "endNodeId": "source"},
        ]}, id_prefix="source-test", turn_id="")
        self.assertEqual([item["type"] for item in board["elements"]], ["rectangle", "code"])
        self.assertEqual(board["elements"][1]["code"], "const value = 42;")

    def test_fenced_code_preserves_its_language_without_markdown_markers(self):
        board = normalize({"elements": [{"id": "source", "type": "text", "text": "```python\nprint(42)\n```"}]})
        self.assertEqual(board["elements"][0]["type"], "code")
        self.assertEqual(board["elements"][0]["language"], "python")
        self.assertEqual(board["elements"][0]["code"], "print(42)")

    def test_image_survives_the_full_board_pipeline_without_a_title(self):
        board = assemble_board({"elements": [{"id": "image", "type": "image", "src": "/lessons/request.png", "alt": "Request and response", "credit": "Course materials"}]}, id_prefix="test-image", turn_id="")
        self.assertEqual(board["elements"][0]["src"], "/lessons/request.png")
        self.assertEqual(board["elements"][0]["alt"], "Request and response")

    def test_image_urls_are_bounded_and_non_executable(self):
        for src in ["javascript:alert(1)", "data:image/svg+xml,test", "//other.test/a.png", "/\\other.test/a.png", "http://example.com/a.png", "https://user:pass@example.com/a.png", "https://example.com/a b.png"]:
            self.assertIsNone(normalize({"elements": [{"id": "bad", "type": "image", "src": src}]}), src)
        self.assertIsNotNone(normalize({"elements": [{"id": "ok", "type": "image", "src": "https://example.com/a.png"}]}))

    def test_circles_and_squares_keep_equal_sides_after_layout(self):
        board = assemble_board({"elements": [{"id": "start", "type": "circle", "text": "Start"}, {"id": "step", "type": "square", "text": "Process"}, {"id": "end", "type": "circle", "text": "End"}, {"id": "edge", "type": "arrow", "startNodeId": "start", "endNodeId": "step", "arrowLabel": "request"}]}, id_prefix="test-shapes", turn_id="")
        shapes = [item for item in board["elements"] if item["type"] != "arrow"]
        self.assertEqual([item["type"] for item in shapes], ["ellipse", "rectangle", "ellipse"])
        for shape in shapes:
            self.assertEqual(shape["width"], shape["height"])
        edge = next(item for item in board["elements"] if item["type"] == "arrow")
        self.assertEqual(edge["arrowLabel"], "request")
        self.assertGreaterEqual(len(edge["points"]), 2)

    def test_untitled_comparison_survives_assembly_and_bad_fields_do_not_crash(self):
        board = assemble_board({"elements": [{"id": "table", "type": "table", "headers": ["Array", "List"], "rows": [["Indexed", "Linked"]]}]}, id_prefix="test-table", turn_id="")
        self.assertEqual(board["elements"][0]["rows"], [["Indexed", "Linked"]])
        normalize({"elements": [{"id": "bad", "type": "table", "headers": 123, "rows": {"bad": "value"}}]})

    def test_tool_schema_exposes_the_supported_visuals(self):
        fields = DIAGRAM_TOOL["function"]["parameters"]["properties"]["elements"]["items"]["properties"]
        for kind in ["circle", "square", "table", "image", "arrow"]:
            self.assertIn(kind, fields["type"]["enum"])
        self.assertIn("src", fields)
        self.assertIn("alt", fields)

    def test_planner_chooses_shapes_by_meaning_and_never_guesses_image_urls(self):
        prompt = _step_prompt("Draw how a request reaches the server", "HTTP")[0]["content"]
        self.assertIn("only for a real decision", prompt)
        self.assertNotIn("all-rectangle board is banned", prompt)
        self.assertIn("Never guess image links", prompt)

    def test_linear_process_uses_edge_order_instead_of_a_binary_tree(self):
        board = assemble_board({"elements": [
            {"id": "b", "type": "square", "text": "Process"},
            {"id": "c", "type": "circle", "text": "End"},
            {"id": "a", "type": "circle", "text": "Start"},
            {"id": "ab", "type": "arrow", "startNodeId": "a", "endNodeId": "b"},
            {"id": "bc", "type": "arrow", "startNodeId": "b", "endNodeId": "c"},
        ]}, id_prefix="chain", turn_id="")
        by_id = {item["id"]: item for item in board["elements"]}
        self.assertLess(by_id["chain-a"]["x"], by_id["chain-b"]["x"])
        self.assertLess(by_id["chain-b"]["x"], by_id["chain-c"]["x"])


if __name__ == "__main__":
    unittest.main()
