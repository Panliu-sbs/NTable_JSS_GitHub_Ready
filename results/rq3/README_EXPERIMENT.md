# Shared-Topology N-Table vs Pratt: 3000-expression incremental experiment

This experiment uses the latest N-Table shared-topology implementation.

## Compared methods

- **NTable_Fresh**: `NTableBuilder.build_ast(expression)`; constructs D from scratch, runs MRC, and returns a materialized `AstNode` tree.
- **NTable_SharedReuse**: `NTableBuilder.build_with_reuse(expression, repo).ast`; on a hot hit it reuses D and one immutable AST topology and returns `BoundAst(topology, operands)`. The timed hot path does **not** call `materialize()`.
- **Pratt**: direct contract-aligned Pratt parsing under the same operator specification and tokenizer/normalization contract; returns a materialized `AstNode` tree.

## Incremental protocol

The 3000 generated expressions are shuffled once with seed `20260914` and divided into 15 consecutive 200-row batches. Unsupported structural seed families are excluded symmetrically from all methods.

For shared reuse, the repository persists across the 15 batches inside each repetition:

`R0 -> R200 -> R400 -> ... -> R3000`

The repository is reset only between independent repetitions. There is one full warm-up pass and 10 measured full sequential repetitions. Median runtime is the principal statistic.

## Correctness

For every supported source family, the experiment checks:

- reused D equals fresh D;
- shared-reuse AST prefix equals fresh N-Table AST prefix;
- Pratt AST prefix equals fresh N-Table AST prefix;
- hot reuse returns a non-materialized `BoundAst`;
- same-family reuse hits share the exact same topology object.

## Main result

At the 3000-input endpoint, 2930 expressions are in the common comparison set and the repository contains 67 unique structural signatures. The final 200-row batch has a 100% reuse hit rate.

Median cumulative runtime through the 3000-input endpoint:

- NTable Fresh: 156.369 ms
- NTable Shared Reuse: 85.630 ms
- Pratt: 91.182 ms

Thus shared-topology reuse is about 45.2% faster than fresh N-Table and about 6.1% faster than direct Pratt in cumulative runtime at the 3000-input endpoint. On the final 200-row batch, shared reuse is about 10.3% faster than Pratt.
