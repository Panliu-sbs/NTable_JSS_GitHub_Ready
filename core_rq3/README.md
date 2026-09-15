# N-Table Shared-Topology Reuse (Python 3.8+)

This is the new N-Table implementation discussed in the manuscript experiments.
It changes the reuse path from **"replay an AST template and allocate a new tree"**
to **"share one immutable AST topology and bind only the current operands"**.

## Core idea

For a normalized expression `S0`, the tokenizer performs one pass and produces:

- `S`: parenthesis-free token sequence used by N-Table;
- `operands`: operand occurrences in left-to-right order;
- `signature`: collision-safe structural signature of `Skel(S0)`.

Example:

```text
a.b.(c||d|e*)
A.B.(C||D|E*)
Open.Read.(Send||Receive|Close*)
```

all have the same human-readable structural rule:

```text
ω.ω.(ω||ω|ω*)
```

The repository key is conceptually `<C, dinit, signature>`. In the implementation,
the contract (including `dinit`) selects a repository namespace and the canonical
structural signature indexes the entry inside that namespace. It does not iterate
over raw regular expressions. Expected lookup cost is O(1) after the O(n)
tokenization/signature pass.

### Cold miss

```text
expression
  -> tokenize/normalize
  -> construct D
  -> MRC AST once
  -> compile immutable SharedAstTopology
  -> repository[<contract, dinit, signature>] = (D, topology, pattern)
  -> return BoundAst(topology, operands)
```

### Hot hit

```text
expression
  -> tokenize/normalize + capture operands + signature
  -> repository lookup
  -> reuse D
  -> BoundAst(shared_topology, current_operands)
```

A hot hit does **not**:

- recompute D;
- run MRC;
- replay AST-template bytecode;
- allocate one `AstNode` object per AST node.

Instead, `BoundAst` is a small expression-specific view over a topology object
that is shared by all structurally equivalent expressions.

## Important representation distinction

`BoundAst` is the fast shared AST representation:

```text
AST(e) = <shared immutable topology, expression-specific operand tuple>
```

It supports:

- `prefix()` without materializing a new tree;
- `pretty()` without materializing a new tree;
- lazy `root`, `left`, and `right` node views;
- explicit `materialize()` when a consumer requires an independent `AstNode` tree.

Calling `materialize()` necessarily allocates all AST nodes and therefore costs
O(number of AST nodes).  The intended reuse benchmark should time the `BoundAst`
path if the research claim is that the topology itself is reused rather than
reconstructed.

## Quick start

```python
from ntable import NTableBuilder, StructuralTemplateRepository

builder = NTableBuilder()
repo = StructuralTemplateRepository()

r1 = builder.build_with_reuse("a.b.(c||d|e*)", repo)
r2 = builder.build_with_reuse("A.B.(C||D|E*)", repo)
r3 = builder.build_with_reuse("Open.Read.(Send||Receive|Close*)", repo)

print(r1.reused)  # False: cold miss
print(r2.reused)  # True
print(r3.reused)  # True

print(r2.pattern)
# ω.ω.(ω||ω|ω*)

print(r2.table.tokens)   # current expression's S
print(r2.table.values)   # reused D
print(r2.ast.prefix())   # reads shared topology directly

print(r1.ast.topology is r2.ast.topology is r3.ast.topology)
# True

# Only if an independent conventional tree is required:
materialized = r2.ast.materialize()
print(materialized.prefix())
```

## Persistent-repository experiment

To study whether reuse becomes more effective as structural knowledge accumulates,
do not clear the repository between successive batches:

```python
repo = StructuralTemplateRepository()

for start in range(0, 3000, 200):
    batch = expressions[start:start + 200]
    for expression in batch:
        result = builder.build_with_reuse(expression, repo)
```

This models the intended learning/reuse process:

```text
R0 -> R200 -> R400 -> ... -> R3000
```

It is different from a cumulative benchmark that recreates an empty repository
for every workload size.

## Main API

### Fresh N-Table

```python
table = builder.build(expression)
```

### Fresh materialized AST

```python
ast = builder.build_ast(expression)
```

### Shared-topology reuse

```python
result = builder.build_with_reuse(expression, repo)
```

The result provides:

```python
result.table       # NTable(S, D)
result.ast         # BoundAst: shared topology + current operands
result.reused      # cache hit/miss
result.signature   # canonical structural key
result.pattern     # human-readable omega skeleton
result.topology    # shared immutable topology
```

### Explicit independent AST

```python
ast_node = result.materialize_ast()
# or
ast_node = result.ast.materialize()
```

## Run the tests

From the project root:

```bash
python -m unittest discover -s tests -v
```

The package currently includes tests for:

- dominance-row construction;
- operand-independent structural signatures;
- shared-topology identity across reuse hits;
- no materialized `AstNode` result on the hot path;
- equivalence with the fresh AST;
- explicit materialization correctness;
- lazy tree navigation;
- repository hit-rate accounting;
- differential testing of the optimized numeric assignment routine.

## Demo

```bash
python examples/shared_topology_demo.py
```

## Convenience benchmark

```bash
python benchmarks/benchmark_shared_topology.py
```

The convenience benchmark is not a substitute for the manuscript experiment;
for the paper use fixed data, warm-up, repeated trials, median runtime, and a
persistent repository when evaluating incremental reuse.

## Python version

Python 3.8 or newer.  There are no third-party runtime dependencies.
