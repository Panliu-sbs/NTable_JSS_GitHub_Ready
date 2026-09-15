# -*- coding: utf-8 -*-
import ast
import os
import unittest

from ast_ep_2023 import ASTEP2023
from ht_ep_2025 import HTEP2025, build_layer_table, format_hierarchy


class PaperExamplesTest(unittest.TestCase):
    def test_2023_running_example_has_30_sequences(self):
        result = ASTEP2023().run("(a|b)c(d|e*)(f||gh)")
        self.assertEqual(30, len(result.sequences))
        expected = {
            "acdfgh", "acdgfh", "acdghf", "acfgh", "acgfh", "acghf",
            "acefgh", "acegfh", "aceghf", "aceefgh", "aceegfh", "aceeghf",
            "aceeefgh", "aceeegfh", "aceeeghf",
            "bcdfgh", "bcdgfh", "bcdghf", "bcfgh", "bcgfh", "bcghf",
            "bcefgh", "bcegfh", "bceghf", "bceefgh", "bceegfh", "bceeghf",
            "bceeefgh", "bceeegfh", "bceeeghf",
        }
        self.assertEqual(expected, set(result.sequences))
        self.assertEqual(8, result.operation_count)

    def test_2025_layer_table_matches_table_2(self):
        table = build_layer_table("(a|(b||k)2)c(d|e)")
        self.assertEqual(
            [0, 1, 1, 2, 3, 3, 3, 2, 2, 0, 0, 0, 1, 1, 1, 0],
            table.final_depths,
        )

    def test_2025_running_example_has_10_sequences(self):
        result = HTEP2025().run("(a|(b||k)2)c(d|e)")
        expected = {
            "acd", "bkbkcd", "bkkbcd", "kbbkcd", "kbkbcd",
            "ace", "bkbkce", "bkkbce", "kbbkce", "kbkbce",
        }
        self.assertEqual(expected, set(result.sequences))
        self.assertEqual(4, result.tree_height)
        tree_text = format_hierarchy(result.tree)
        self.assertIn("b||k", tree_text)
        self.assertIn("d|e", tree_text)

    def test_2025_closure_example_has_15_sequences(self):
        result = HTEP2025().run("c(a|b)*")
        self.assertEqual(15, len(result.sequences))
        self.assertIn("c", result.sequences)
        self.assertIn("caaa", result.sequences)
        self.assertIn("cbbb", result.sequences)

    def test_multichar_explicit_concat(self):
        expression = "Open.File.(New|Merge).Close"
        a = ASTEP2023().run(expression, separator=".")
        h = HTEP2025().run(expression, separator=".")
        expected = {"Open.File.New.Close", "Open.File.Merge.Close"}
        self.assertEqual(expected, set(a.sequences))
        self.assertEqual(expected, set(h.sequences))


class Python38GrammarTest(unittest.TestCase):
    def test_sources_parse_as_python38(self):
        base = os.path.dirname(__file__)
        for name in ["common.py", "ast_ep_2023.py", "ht_ep_2025.py", "demo.py", "test_reconstruction.py"]:
            with open(os.path.join(base, name), "r", encoding="utf-8") as f:
                source = f.read()
            # Current interpreter may be newer; feature_version checks Python 3.8 grammar.
            ast.parse(source, filename=name, feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()
