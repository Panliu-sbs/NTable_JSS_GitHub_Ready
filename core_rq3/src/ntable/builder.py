from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from ._segment import LazyMaxSegmentTree, MaxIndexSegmentTree
from .ast import AstBuilder
from .model import AstNode, NTable
from .reuse import (
    ReuseBuildResult,
    SharedAstTopology,
    StructuralTemplateEntry,
    StructuralTemplateRepository,
    make_contract_fingerprint,
)
from .spec import OperatorSpec, default_operator_spec
from .tokenizer import NormalizationOptions, ReuseTokenization, Tokenizer


@dataclass(frozen=True)
class _ParenPart:
    placeholder: str
    inner_tokens: Tuple[str, ...]


class NTableBuilder:
    """N-Table construction with structural-template reuse.

    Fresh construction:
        expression -> normalized S0 -> D -> NTable -> MRC -> AST

    Reuse hit:
        expression -> (S, operands, structural signature) -> dictionary lookup
                   -> cached D + shared immutable AST topology
                   -> O(1)-size BoundAst(topology, operands)

    A hit therefore skips dominance resolution, skips MRC, and does not allocate
    a fresh AstNode tree.  The operator topology is shared directly.  A fully
    materialized independent AstNode tree remains available on explicit demand.
    """

    __slots__ = ("spec", "dinit", "tokenizer", "_contract", "_ast_builder")

    def __init__(
        self,
        spec: Optional[OperatorSpec] = None,
        dinit: int = -1,
        *,
        insert_explicit_concat: bool = True,
    ) -> None:
        self.spec = spec or default_operator_spec()
        self.dinit = dinit
        self.tokenizer = Tokenizer(
            self.spec,
            NormalizationOptions(insert_explicit_concat=insert_explicit_concat),
        )
        self._contract = make_contract_fingerprint(
            self.spec,
            self.dinit,
            insert_explicit_concat,
        )
        self._ast_builder = AstBuilder(self.spec)

    # ------------------------------------------------------------------
    # Ordinary N-Table / AST construction
    # ------------------------------------------------------------------

    def build(self, expression: str) -> NTable:
        tokens = self.tokenizer.tokenize(expression)
        return self.build_tokens(tokens)

    def build_ast(self, expression: str) -> AstNode:
        """Fresh path: construct N-Table and then reconstruct the AST."""
        return self._ast_builder.build(self.build(expression))

    # ------------------------------------------------------------------
    # Structural pattern / signature diagnostics
    # ------------------------------------------------------------------

    def structural_skeleton(self, expression: str) -> Tuple[str, ...]:
        scan = self.tokenizer.tokenize_for_reuse(expression)
        return self.tokenizer.decode_signature(scan.structural_signature)

    def structural_pattern(self, expression: str) -> str:
        """Human-readable structural rule with operands replaced by omega."""
        return "".join(self.structural_skeleton(expression))

    def structural_signature(self, expression: str) -> str:
        """Collision-safe cache key encoding used by the hot path."""
        return self.tokenizer.tokenize_for_reuse(expression).structural_signature

    # ------------------------------------------------------------------
    # Shared-topology Algorithm 4
    # ------------------------------------------------------------------

    def build_with_reuse(
        self,
        expression: str,
        repository: StructuralTemplateRepository,
    ) -> ReuseBuildResult:
        """Build N-Table plus a shared-topology AST view.

        The tokenizer obtains S0, S, operand occurrences, and the structural
        signature together. On a hit, this method executes neither Algorithm 2
        nor MRC and allocates no per-node AstNode tree. It pairs current S with
        cached D and returns BoundAst(shared_topology, current_operands).
        """
        scan = self.tokenizer.tokenize_for_reuse(expression)
        return self._build_scan_with_reuse(scan, repository)

    # Explicit name useful in experiments and manuscript code.
    build_ast_with_shared_reuse = build_with_reuse
    build_ast_with_template_reuse = build_with_reuse

    def build_tokens_with_reuse(
        self,
        tokens: Union[List[str], Tuple[str, ...]],
        repository: StructuralTemplateRepository,
    ) -> ReuseBuildResult:
        """Template reuse for an already normalized S0 token sequence."""
        toks = tuple(tokens)
        scan = self.tokenizer.encode_normalized_tokens(toks)
        return self._build_scan_with_reuse(scan, repository)

    def _build_scan_with_reuse(
        self,
        scan: ReuseTokenization,
        repository: StructuralTemplateRepository,
    ) -> ReuseBuildResult:
        signature = scan.structural_signature
        entry = repository.lookup_signature(self._contract, signature)

        if entry is not None:
            # Hot path: exact structural match. Current S and operands have
            # already been produced by normalization. Reuse both resolved D and
            # the immutable AST topology. No AstNode tree is created here.
            table = NTable(scan.flat_tokens, entry.dominance_row)
            ast = entry.ast_topology.bind(scan.operands)
            reused = True
        else:
            # Cold path: resolve D and materialize the AST exactly once. Compile
            # it into immutable shared topology, store it, and return a BoundAst
            # view over that topology. Future hits allocate no AstNode tree.
            table = self._build_tokens_validated(scan.grouped_tokens)
            materialized = self._ast_builder.build(table)
            topology = SharedAstTopology.compile(materialized)
            if topology.operand_count != len(scan.operands):
                raise ValueError(
                    "Shared AST topology operand count disagrees with tokenization"
                )
            entry = StructuralTemplateEntry(
                dominance_row=table.values,
                ast_topology=topology,
                pattern="".join(
                    self.tokenizer.decode_signature(signature)
                ),
            )
            repository.store_signature(self._contract, signature, entry)
            ast = topology.bind(scan.operands)
            reused = False

        return ReuseBuildResult(
            table=table,
            ast=ast,
            reused=reused,
            contract=self._contract,
            signature=signature,
            pattern=entry.pattern,
            operand_count=len(scan.operands),
        )

    def build_tokens(self, tokens: Union[List[str], Tuple[str, ...]]) -> NTable:
        toks = tuple(tokens)
        self._validate_tokens(toks)
        return self._build_tokens_validated(toks)

    def _build_tokens_validated(self, toks: Tuple[str, ...]) -> NTable:
        if "(" not in toks and ")" not in toks:
            return self._build_simple(toks)
        return self._build_general(toks)

    def _validate_tokens(self, tokens: Tuple[str, ...]) -> None:
        depth = 0
        for tok in tokens:
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced parentheses")
        if depth != 0:
            raise ValueError("Unbalanced parentheses")

    def _build_general(self, tokens: Tuple[str, ...]) -> NTable:
        outer_tokens, parts = self._replace_outermost(tokens)

        if len(outer_tokens) == 1 and parts and outer_tokens[0] == parts[0].placeholder:
            return self.build_tokens(parts[0].inner_tokens)

        outer_table = self._build_simple(outer_tokens)

        # Compute binding numeric values against the original outer table before any splice.
        bind_values: Dict[str, int] = {}
        for part in parts:
            placeholder_index = outer_table.tokens.index(part.placeholder)
            bind_values[part.placeholder] = self._binding_value(
                outer_table, placeholder_index
            )

        current = outer_table
        for part in parts:
            inner = self.build_tokens(part.inner_tokens)
            idx = current.tokens.index(part.placeholder)

            if not inner.has_operator():
                current = self._splice(current, idx, inner)
                continue

            d_bind = bind_values[part.placeholder]
            delta = d_bind - inner.operator_max() - 1
            current = self._splice(current, idx, inner.shifted(delta))

        return current

    def _replace_outermost(
        self, tokens: Tuple[str, ...]
    ) -> Tuple[Tuple[str, ...], List[_ParenPart]]:
        out: List[str] = []
        parts: List[_ParenPart] = []
        depth = 0
        start = -1
        counter = 0

        for i, tok in enumerate(tokens):
            if tok == "(":
                if depth == 0:
                    start = i
                depth += 1
                if depth > 1:
                    # Nested contents are captured as part of the outermost slice.
                    pass
            elif tok == ")":
                depth -= 1
                if depth == 0:
                    counter += 1
                    placeholder = f"$k{counter}"
                    inner_tokens = tokens[start + 1 : i]
                    if not inner_tokens:
                        raise ValueError("Empty parenthesized subexpression")
                    parts.append(_ParenPart(placeholder, inner_tokens))
                    out.append(placeholder)
                    start = -1
            elif depth == 0:
                out.append(tok)

        if depth != 0:
            raise ValueError("Unbalanced parentheses")
        return tuple(out), parts

    def _binding_value(self, table: NTable, placeholder_index: int) -> int:
        p_left: Optional[int] = None
        p_right: Optional[int] = None

        for i in range(placeholder_index - 1, -1, -1):
            if table.values[i] is not None:
                p_left = i
                break
        for i in range(placeholder_index + 1, len(table.tokens)):
            if table.values[i] is not None:
                p_right = i
                break

        if p_left is None and p_right is None:
            raise ValueError("No binding operator exists for placeholder")
        if p_left is None:
            return int(table.values[p_right])  # type: ignore[arg-type]
        if p_right is None:
            return int(table.values[p_left])  # type: ignore[arg-type]

        dl = int(table.values[p_left])   # type: ignore[arg-type]
        dr = int(table.values[p_right])  # type: ignore[arg-type]

        # Section 5.3.1: smaller numeric value binds directly;
        # numeric tie -> choose right operator under leftmost-maximum MRC.
        return dl if dl < dr else dr

    @staticmethod
    def _splice(outer: NTable, idx: int, inner: NTable) -> NTable:
        return NTable(
            outer.tokens[:idx] + inner.tokens + outer.tokens[idx + 1 :],
            outer.values[:idx] + inner.values + outer.values[idx + 1 :],
        )

    def _build_simple(self, tokens: Tuple[str, ...]) -> NTable:
        op_positions: List[int] = []
        ranks: List[int] = []

        for i, tok in enumerate(tokens):
            if tok in self.spec:
                op_positions.append(i)
                ranks.append(self.spec.rank(tok))
            elif tok in {"(", ")"}:
                raise ValueError("_build_simple received parentheses")

        k = len(op_positions)
        if k == 0:
            return NTable(tokens, (None,) * len(tokens))

        numeric = self._assign_fast(ranks)
        values: List[Optional[int]] = [None] * len(tokens)
        for pos, d in zip(op_positions, numeric):
            values[pos] = d
        return NTable(tokens, tuple(values))

    def _assign_fast(self, ranks: List[int]) -> List[int]:
        """
        Optimized Rules 1-4.

        For rt <= r(t-1), Rules 3 and 4 have the same numeric update:
        find largest u <= t-2 with r[u] < r[t], shift u+1..t-1 by -1,
        and set d[t] = d[u]-1; if no u exists, use max(previous)+1.
        """
        k = len(ranks)
        if k == 0:
            return []

        numeric_tree = LazyMaxSegmentTree(k)
        sorted_ranks = sorted(set(ranks))
        rank_to_idx = {r: i for i, r in enumerate(sorted_ranks)}
        last_index_tree = MaxIndexSegmentTree(len(sorted_ranks))

        numeric_tree.point_set(0, self.dinit)
        last_index_tree.update_max(rank_to_idx[ranks[0]], 0)

        for t in range(1, k):
            rt = ranks[t]
            prev_rank = ranks[t - 1]

            if rt > prev_rank:
                dt = numeric_tree.point_query(t - 1) - 1
            else:
                compressed = bisect_left(sorted_ranks, rt)
                u = last_index_tree.prefix_max(compressed)

                # Rule searches only through 0..t-2. Since rt <= prev_rank,
                # t-1 can never satisfy rank < rt, so the rank-tree result is safe.
                if u >= 0:
                    numeric_tree.range_add(u + 1, t - 1, -1)
                    dt = numeric_tree.point_query(u) - 1
                else:
                    dt = numeric_tree.range_max(0, t - 1) + 1

            numeric_tree.point_set(t, dt)
            last_index_tree.update_max(rank_to_idx[rt], t)

        return [numeric_tree.point_query(i) for i in range(k)]

    def _assign_reference(self, ranks: List[int]) -> List[int]:
        """Literal O(k^2) implementation used only for differential tests."""
        if not ranks:
            return []
        d = [self.dinit]
        for t in range(1, len(ranks)):
            rt = ranks[t]
            prev = ranks[t - 1]
            if rt > prev:
                d.append(d[t - 1] - 1)
                continue

            u = None
            for j in range(t - 2, -1, -1):
                if ranks[j] < rt:
                    u = j
                    break

            if u is None:
                d.append(max(d[:t]) + 1)
            else:
                for j in range(u + 1, t):
                    d[j] -= 1
                d.append(d[u] - 1)
        return d
