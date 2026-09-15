import itertools
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ntable import (
    AstBuilder,
    AstNode,
    BoundAst,
    NTableBuilder,
    StructuralTemplateRepository,
)


class SharedTopologyReuseTests(unittest.TestCase):
    def setUp(self):
        self.builder = NTableBuilder()
        self.ast_builder = AstBuilder(self.builder.spec)

    def test_fresh_parenthesized_example(self):
        table = self.builder.build("a.b.(c||d|e*)")
        self.assertEqual(
            table.tokens,
            ("a", ".", "b", ".", "c", "||", "d", "|", "e", "*"),
        )
        self.assertEqual(
            table.values,
            (None, -1, None, 0, None, -2, None, -1, None, -2),
        )

    def test_signature_is_operand_independent(self):
        s1 = self.builder.structural_signature("a.b.(c||d|e*)")
        s2 = self.builder.structural_signature(
            "Open.Read.(Send||Receive|Close*)"
        )
        self.assertEqual(s1, s2)
        self.assertEqual(
            self.builder.structural_pattern("a.b.(c||d|e*)"),
            "ω.ω.(ω||ω|ω*)",
        )

    def test_hot_hit_reuses_same_topology_object(self):
        repo = StructuralTemplateRepository()

        cold = self.builder.build_with_reuse("a.b.(c||d|e*)", repo)
        hit1 = self.builder.build_with_reuse("A.B.(C||D|E*)", repo)
        hit2 = self.builder.build_with_reuse(
            "Open.Read.(Send||Receive|Close*)", repo
        )

        self.assertFalse(cold.reused)
        self.assertTrue(hit1.reused)
        self.assertTrue(hit2.reused)
        self.assertIs(cold.ast.topology, hit1.ast.topology)
        self.assertIs(hit1.ast.topology, hit2.ast.topology)
        self.assertTrue(hit1.ast.shares_topology_with(hit2.ast))
        self.assertEqual(len(repo), 1)

    def test_hot_hit_returns_bound_ast_not_materialized_tree(self):
        repo = StructuralTemplateRepository()
        self.builder.build_with_reuse("a.b|c", repo)
        hit = self.builder.build_with_reuse("x.y|z", repo)

        self.assertIsInstance(hit.ast, BoundAst)
        self.assertFalse(hit.ast.is_materialized)
        self.assertNotIsInstance(hit.ast, AstNode)
        self.assertEqual(hit.ast.operands, ("x", "y", "z"))
        self.assertEqual(hit.ast.prefix(), "(| (. x y) z)")

    def test_bound_ast_matches_fresh_ast_without_materialization(self):
        repo = StructuralTemplateRepository()
        self.builder.build_with_reuse("a.b.(c||d|e*)", repo)
        hit = self.builder.build_with_reuse("A.B.(C||D|E*)", repo)
        fresh = self.builder.build_ast("A.B.(C||D|E*)")

        self.assertEqual(hit.ast.prefix(), fresh.prefix())
        self.assertEqual(hit.table.values, self.builder.build("A.B.(C||D|E*)").values)

    def test_materialize_is_explicit_and_equivalent(self):
        repo = StructuralTemplateRepository()
        self.builder.build_with_reuse("a.b|c", repo)
        hit = self.builder.build_with_reuse("x.y|z", repo)

        materialized = hit.ast.materialize()
        fresh = self.builder.build_ast("x.y|z")

        self.assertIsInstance(materialized, AstNode)
        self.assertEqual(materialized.prefix(), fresh.prefix())
        self.assertIsNot(materialized, fresh)

    def test_lazy_node_navigation(self):
        repo = StructuralTemplateRepository()
        result = self.builder.build_with_reuse("a.b|c", repo)
        root = result.ast.root

        self.assertEqual(root.label, "|")
        self.assertFalse(root.is_leaf)
        self.assertIsNotNone(root.left)
        self.assertEqual(root.left.label, ".")
        self.assertEqual(root.left.left.label, "a")
        self.assertEqual(root.left.right.label, "b")
        self.assertEqual(root.right.label, "c")

    def test_repeated_operand_labels_are_bound_by_occurrence(self):
        repo = StructuralTemplateRepository()
        self.builder.build_with_reuse("a.a|b", repo)
        hit = self.builder.build_with_reuse("x.y|z", repo)
        fresh = self.builder.build_ast("x.y|z")
        self.assertTrue(hit.reused)
        self.assertEqual(hit.ast.prefix(), fresh.prefix())

    def test_grouping_changes_signature(self):
        self.assertNotEqual(
            self.builder.structural_signature("a.(b|c)"),
            self.builder.structural_signature("(a.b)|c"),
        )

    def test_tokenizer_collects_all_hot_path_data_in_one_pass(self):
        scan = self.builder.tokenizer.tokenize_for_reuse(
            "Open.Read.(Send||Receive|Close*)"
        )
        self.assertEqual(
            scan.flat_tokens,
            (
                "Open",
                ".",
                "Read",
                ".",
                "Send",
                "||",
                "Receive",
                "|",
                "Close",
                "*",
            ),
        )
        self.assertEqual(
            scan.operands,
            ("Open", "Read", "Send", "Receive", "Close"),
        )
        self.assertIn("A;", scan.structural_signature)
        self.assertIn("O2:||;", scan.structural_signature)

    def test_repository_hit_rate(self):
        repo = StructuralTemplateRepository()
        expressions = ["a.b|c", "x.y|z", "p.q|r", "u.v|w"]
        results = [self.builder.build_with_reuse(e, repo) for e in expressions]
        self.assertFalse(results[0].reused)
        self.assertTrue(all(r.reused for r in results[1:]))
        self.assertEqual(repo.misses, 1)
        self.assertEqual(repo.hits, 3)
        self.assertAlmostEqual(repo.hit_rate, 0.75)

    def test_fast_numeric_assignment_matches_reference(self):
        for length in range(1, 7):
            for ranks in itertools.product(range(4), repeat=length):
                ranks = list(ranks)
                self.assertEqual(
                    self.builder._assign_fast(ranks),
                    self.builder._assign_reference(ranks),
                )


if __name__ == "__main__":
    unittest.main()
