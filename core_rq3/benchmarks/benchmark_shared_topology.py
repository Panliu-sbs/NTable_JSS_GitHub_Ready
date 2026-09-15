"""Small benchmark showing the intended persistent-repository workflow.

This benchmark compares:
  1. Fresh N-Table + fully materialized AST.
  2. Shared-topology reuse returning BoundAst (no per-hit tree allocation).

It deliberately keeps one repository alive across successive expressions.
For publication experiments, use repeated trials, warm-up, fixed datasets, and
report medians rather than relying on this convenience benchmark alone.
"""

from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ntable import NTableBuilder, StructuralTemplateRepository


builder = NTableBuilder()
expressions = [
    f"A{i}.B{i}.(C{i}||D{i}|E{i}*)"
    for i in range(3000)
]

start = time.perf_counter_ns()
for expression in expressions:
    builder.build_ast(expression)
fresh_ns = time.perf_counter_ns() - start

repo = StructuralTemplateRepository()
start = time.perf_counter_ns()
last = None
for expression in expressions:
    last = builder.build_with_reuse(expression, repo)
shared_ns = time.perf_counter_ns() - start

assert last is not None
print("Fresh materialized AST: %.3f ms" % (fresh_ns / 1_000_000.0))
print("Shared-topology reuse:  %.3f ms" % (shared_ns / 1_000_000.0))
print("Reduction:              %.2f%%" % ((1.0 - shared_ns / fresh_ns) * 100.0))
print("Repository entries:", len(repo))
print("Reuse hit rate: %.2f%%" % (repo.hit_rate * 100.0))
print("Last result materialized?", last.ast.is_materialized)
