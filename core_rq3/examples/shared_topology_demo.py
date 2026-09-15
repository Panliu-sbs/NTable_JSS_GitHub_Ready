from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ntable import NTableBuilder, StructuralTemplateRepository


builder = NTableBuilder()
repo = StructuralTemplateRepository()

expressions = [
    "a.b.(c||d|e*)",
    "A.B.(C||D|E*)",
    "Open.Read.(Send||Receive|Close*)",
]

results = []
for expression in expressions:
    result = builder.build_with_reuse(expression, repo)
    results.append(result)
    print("expression :", expression)
    print("pattern    :", result.pattern)
    print("reused     :", result.reused)
    print("S          :", result.table.tokens)
    print("D          :", result.table.values)
    print("AST prefix :", result.ast.prefix())
    print("materialized?", result.ast.is_materialized)
    print()

print("All expressions share one operator topology:")
print(results[0].ast.topology is results[1].ast.topology is results[2].ast.topology)
print("repository entries:", len(repo))
print("hit rate:", repo.hit_rate)

# Only consumers that require a standalone mutable tree pay this O(n) cost.
independent_tree = results[-1].ast.materialize()
print("materialized prefix:", independent_tree.prefix())
