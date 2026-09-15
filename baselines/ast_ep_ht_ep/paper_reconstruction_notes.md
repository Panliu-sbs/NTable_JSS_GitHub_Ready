# Reconstruction notes and paper-to-code mapping

## 1. JSS 2023: AST-EP

### Directly implemented from the paper

1. Build an AST and obtain a post-order list.
2. Repeatedly find the first operator in that list.
3. Binary operators (`Op1`) reduce the two immediately preceding values plus the
   operator (Theorem 3(1)).
4. Postfix/closure operators (`Op2`) reduce the immediately preceding value plus the
   operator (Theorem 3(2)).
5. `ParsingClosure` follows Eqs. (16)-(18):
   - non-choice operand: `k=3`;
   - top-level choice `a1|...|an`: `k=n`.
6. The operation lookup is represented as the paper's `T`/`V` concept, although the
   executable rules are Python functions rather than equation strings.

### Reconstruction choice

The paper says its AST is produced with a modified RE2. The modified source and exact
extended-operator precedence are not fully specified. `common.py` therefore supplies an
independent parser. This should be described in the experiment as a **paper-based
reimplementation**, not the original implementation.

## 2. JSS 2025: HT-EP

### Directly implemented from the paper

1. `ConstructHierarchyTree` recursively uses 1-layer subexpressions.
2. Evaluation proceeds deepest layer -> root and propagates each result to its father.
3. Operator priority is: constraint symbols, concatenation, concurrent/alternate,
   choice. Equal-priority operators are processed left-to-right.
4. Eqs. (38)-(39) generate the initial layer depth.
5. Numeric repetition and constraints are postfix constraint symbols.
6. Eq. (41) bounds `*` to powers 0,1,2,3.

### Printed ambiguities resolved from the paper's own examples

1. **Algorithm 3 vs Eq. (41):** Algorithm 3's text says to set `0,1,2` for `*`, while
   Eq. (41) and Fig. 5(e) clearly use `0,1,2,3` and produce 15 sequences for
   `c(a|b)*`. The code follows Eq. (41) + Fig. 5(e): powers 0..3.
2. **Eq. (40) indexing/boundary condition:** the printed `w(j)`/boundary expression is
   ambiguous for a postfix operator after `)`. The implementation uses the behavior
   demonstrated by Table 2 and Fig. 5(a)-(d): a postfix constraint raises the depth of
   its constrained span only when that span is a proper subexpression of the current
   node. This reproduces Table 2 exactly for `(a|(b||k)2)c(d|e)`.
3. **Algorithm 3 single final operation:** the pseudocode says "find an algebraic
   operation" after constraint processing, but the worked example at the root applies
   several equations. The implementation therefore repeatedly reduces operators in the
   stated priority order until the node becomes a finite sequence set.

## 3. Algebraic operation semantics

The papers define operation *sets*, so a reimplementation needs executable rules.
`common.AlgebraEngine` instantiates the paper equations over finite sets of token
sequences:

- choice = set union;
- concatenation = Cartesian concatenation;
- `||` = all order-preserving shuffles (the recursive form of the alternation rules);
- `[]` = the concurrency rule `a[]b = a | b(a||b)` with the stated identities;
- `*` = bounded closure (2023 heuristic or 2025 fixed 0..3);
- integer postfix = exact repetition;
- `/{#LEN=n}` = sequence-length filter;
- other constraints can be supplied through `constraint_handler`.

This separation is useful for the planned experiment: tree/parsing strategy can be held
constant with respect to the same algebraic semantic engine.
