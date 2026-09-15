from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Tuple

from .model import AstNode, NTable
from .spec import OperatorSpec


DominanceRow = Tuple[Optional[int], ...]

# Shared AST-topology node kinds.
_TOPOLOGY_OPERAND = 0
_TOPOLOGY_UNARY = 1
_TOPOLOGY_BINARY = 2


class TopologyRecord(NamedTuple):
    """One immutable node in a shared AST topology.

    For operand nodes, ``value`` is the integer operand-slot index.
    For operator nodes, ``value`` is the operator label.
    Child indexes refer to records in ``SharedAstTopology.nodes``; ``-1`` means
    that a child does not exist.
    """

    kind: int
    value: object
    left: int
    right: int


@dataclass(frozen=True)
class ContractFingerprint:
    """Hashable implementation-level fingerprint of reconstruction contract C."""

    operators: Tuple[Tuple[str, int, int, str], ...]
    associativity: str
    tie_breaking: str
    dinit: int
    insert_explicit_concat: bool


@dataclass(frozen=True)
class StructuralReuseKey:
    """Diagnostic representation of K(S0, C)."""

    contract: ContractFingerprint
    signature: str


@dataclass(frozen=True)
class SharedAstTopology:
    """Immutable operand-abstracted AST topology shared by many expressions.

    Unlike the previous template implementation, a reuse hit does *not* replay
    a bytecode program and does *not* allocate a fresh ``AstNode`` for every
    operator and operand.  The topology is created once on a cold miss and then
    shared.  A new expression only creates a tiny ``BoundAst`` view containing
    a reference to this topology and its own operand tuple.
    """

    nodes: Tuple[TopologyRecord, ...]
    root_index: int
    operand_count: int

    @classmethod
    def compile(cls, ast: AstNode) -> "SharedAstTopology":
        nodes: List[TopologyRecord] = []
        next_slot = [0]

        def visit(node: AstNode) -> int:
            if node.is_leaf:
                slot = next_slot[0]
                next_slot[0] += 1
                index = len(nodes)
                nodes.append(TopologyRecord(_TOPOLOGY_OPERAND, slot, -1, -1))
                return index

            if node.left is None:
                raise ValueError("Malformed AST: non-leaf node lacks a child")

            left_index = visit(node.left)

            if node.right is None:
                index = len(nodes)
                nodes.append(
                    TopologyRecord(_TOPOLOGY_UNARY, node.label, left_index, -1)
                )
                return index

            right_index = visit(node.right)
            index = len(nodes)
            nodes.append(
                TopologyRecord(
                    _TOPOLOGY_BINARY,
                    node.label,
                    left_index,
                    right_index,
                )
            )
            return index

        root_index = visit(ast)
        return cls(tuple(nodes), root_index, next_slot[0])

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def bind(self, operands: Tuple[str, ...]) -> "BoundAst":
        """Create an O(1)-size AST binding over the shared topology."""
        if len(operands) != self.operand_count:
            raise ValueError(
                "Operand count does not match shared AST topology: "
                f"expected {self.operand_count}, got {len(operands)}"
            )
        return BoundAst(self, operands)

    def materialize(self, operands: Tuple[str, ...]) -> AstNode:
        """Build a conventional independent ``AstNode`` tree on demand.

        This method is intentionally separate from the hot reuse path.  Calling
        it costs O(number of AST nodes), because an independent tree must
        allocate all nodes.  The normal shared-reuse path returns ``BoundAst``
        and does not call this method.
        """
        return self.bind(operands).materialize()


class BoundAst:
    """Expression-specific AST view: shared topology + operand bindings.

    Construction of this object is constant-size after tokenization has already
    collected the operand tuple.  The operator topology is never copied on a
    reuse hit.

    ``prefix()`` and ``pretty()`` inspect the shared topology directly without
    materializing a conventional tree.  Use ``materialize()`` only when a
    consumer explicitly requires an independent mutable ``AstNode`` tree.
    """

    __slots__ = ("_topology", "_operands")

    def __init__(
        self,
        topology: SharedAstTopology,
        operands: Tuple[str, ...],
    ) -> None:
        if len(operands) != topology.operand_count:
            raise ValueError(
                "Operand count does not match shared AST topology: "
                f"expected {topology.operand_count}, got {len(operands)}"
            )
        self._topology = topology
        self._operands = operands

    @property
    def topology(self) -> SharedAstTopology:
        return self._topology

    @property
    def operands(self) -> Tuple[str, ...]:
        return self._operands

    @property
    def node_count(self) -> int:
        return self._topology.node_count

    @property
    def root(self) -> "BoundAstNode":
        return BoundAstNode(self, self._topology.root_index)

    @property
    def is_materialized(self) -> bool:
        return False

    def shares_topology_with(self, other: "BoundAst") -> bool:
        return self._topology is other._topology

    def prefix(self) -> str:
        """Return prefix notation without allocating an ``AstNode`` tree."""
        nodes = self._topology.nodes
        operands = self._operands

        def rec(index: int) -> str:
            record = nodes[index]
            if record.kind == _TOPOLOGY_OPERAND:
                return operands[int(record.value)]
            if record.kind == _TOPOLOGY_UNARY:
                return f"({record.value} {rec(record.left)})"
            if record.kind == _TOPOLOGY_BINARY:
                return (
                    f"({record.value} "
                    f"{rec(record.left)} "
                    f"{rec(record.right)})"
                )
            raise ValueError("Malformed shared AST topology")

        return rec(self._topology.root_index)

    def pretty(self) -> str:
        """Pretty-print the bound AST without materializing ``AstNode`` objects."""
        nodes = self._topology.nodes
        operands = self._operands
        lines: List[str] = []

        def label(index: int) -> str:
            record = nodes[index]
            if record.kind == _TOPOLOGY_OPERAND:
                return operands[int(record.value)]
            return str(record.value)

        def children(index: int) -> Tuple[int, ...]:
            record = nodes[index]
            if record.kind == _TOPOLOGY_OPERAND:
                return ()
            if record.kind == _TOPOLOGY_UNARY:
                return (record.left,)
            if record.kind == _TOPOLOGY_BINARY:
                return (record.left, record.right)
            raise ValueError("Malformed shared AST topology")

        root = self._topology.root_index
        lines.append(label(root))

        def rec(index: int, prefix: str, is_tail: bool) -> None:
            lines.append(prefix + ("└── " if is_tail else "├── ") + label(index))
            child_indexes = children(index)
            for i, child in enumerate(child_indexes):
                rec(
                    child,
                    prefix + ("    " if is_tail else "│   "),
                    i == len(child_indexes) - 1,
                )

        root_children = children(root)
        for i, child in enumerate(root_children):
            rec(child, "", i == len(root_children) - 1)
        return "\n".join(lines)

    def materialize(self) -> AstNode:
        """Allocate a conventional independent tree only when explicitly asked."""
        nodes = self._topology.nodes
        operands = self._operands

        def rec(index: int) -> AstNode:
            record = nodes[index]
            if record.kind == _TOPOLOGY_OPERAND:
                return AstNode(operands[int(record.value)])
            if record.kind == _TOPOLOGY_UNARY:
                return AstNode(str(record.value), rec(record.left), None)
            if record.kind == _TOPOLOGY_BINARY:
                return AstNode(
                    str(record.value),
                    rec(record.left),
                    rec(record.right),
                )
            raise ValueError("Malformed shared AST topology")

        return rec(self._topology.root_index)


class BoundAstNode:
    """Lazy node view for navigation over a ``BoundAst``.

    Node views are created only when a caller navigates the tree.  They are not
    created during the normal reuse construction path.
    """

    __slots__ = ("_ast", "_index")

    def __init__(self, ast: BoundAst, index: int) -> None:
        self._ast = ast
        self._index = index

    @property
    def _record(self) -> TopologyRecord:
        return self._ast.topology.nodes[self._index]

    @property
    def label(self) -> str:
        record = self._record
        if record.kind == _TOPOLOGY_OPERAND:
            return self._ast.operands[int(record.value)]
        return str(record.value)

    @property
    def is_leaf(self) -> bool:
        return self._record.kind == _TOPOLOGY_OPERAND

    @property
    def left(self) -> Optional["BoundAstNode"]:
        record = self._record
        if record.left < 0:
            return None
        return BoundAstNode(self._ast, record.left)

    @property
    def right(self) -> Optional["BoundAstNode"]:
        record = self._record
        if record.right < 0:
            return None
        return BoundAstNode(self._ast, record.right)


# Backward-compatible public name.  Semantically this is now a true shared
# topology rather than a bytecode program replayed into fresh nodes.
AstTemplate = SharedAstTopology


@dataclass(frozen=True)
class StructuralTemplateEntry:
    """Cached structural state for one exact structural signature."""

    dominance_row: DominanceRow
    ast_topology: SharedAstTopology
    pattern: str

    @property
    def ast_template(self) -> SharedAstTopology:
        """Compatibility alias for code written against the previous version."""
        return self.ast_topology


@dataclass(frozen=True)
class SharedReuseResult:
    """Result of N-Table shared-topology reuse.

    ``ast`` is a ``BoundAst`` view, not a newly materialized tree.  On a cache
    hit both D and operator topology are reused directly.
    """

    table: NTable
    ast: BoundAst
    reused: bool
    contract: ContractFingerprint
    signature: str
    pattern: str
    operand_count: int

    @property
    def key(self) -> StructuralReuseKey:
        return StructuralReuseKey(self.contract, self.signature)

    @property
    def topology(self) -> SharedAstTopology:
        return self.ast.topology

    def materialize_ast(self) -> AstNode:
        return self.ast.materialize()


# Compatibility aliases used by older experiment code.
TemplateReuseResult = SharedReuseResult
ReuseBuildResult = SharedReuseResult


class StructuralTemplateRepository:
    """Repository for exact D + shared-AST-topology structural reuse.

    The human-facing rule is the omega skeleton (for example ``ω.ω|ω``), while
    the hot path uses a collision-safe canonical signature as a dictionary key.
    This avoids scanning all regular expressions: lookup is expected O(1).
    """

    __slots__ = ("_entries", "_size", "hits", "misses")

    def __init__(self) -> None:
        self._entries: Dict[
            ContractFingerprint, Dict[str, StructuralTemplateEntry]
        ] = {}
        self._size = 0
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return self._size

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return 0.0 if total == 0 else self.hits / total

    def lookup_signature(
        self,
        contract: ContractFingerprint,
        signature: str,
    ) -> Optional[StructuralTemplateEntry]:
        namespace = self._entries.get(contract)
        if namespace is None:
            self.misses += 1
            return None
        entry = namespace.get(signature)
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def store_signature(
        self,
        contract: ContractFingerprint,
        signature: str,
        entry: StructuralTemplateEntry,
    ) -> None:
        namespace = self._entries.setdefault(contract, {})
        existing = namespace.get(signature)
        if existing is not None:
            if existing != entry:
                raise ValueError(
                    "Conflicting structural template for the same signature"
                )
            return
        namespace[signature] = entry
        self._size += 1

    def lookup(self, key: StructuralReuseKey) -> Optional[StructuralTemplateEntry]:
        return self.lookup_signature(key.contract, key.signature)

    def store(self, key: StructuralReuseKey, entry: StructuralTemplateEntry) -> None:
        self.store_signature(key.contract, key.signature, entry)

    def clear(self) -> None:
        self._entries.clear()
        self._size = 0
        self.hits = 0
        self.misses = 0


# More precise new name; old repository name remains supported.
StructuralTopologyRepository = StructuralTemplateRepository


def make_contract_fingerprint(
    spec: OperatorSpec,
    dinit: int,
    insert_explicit_concat: bool,
) -> ContractFingerprint:
    """Create the fixed-contract part of an exact structural-reuse key."""
    operators = tuple(
        sorted(
            (
                symbol,
                op.rank,
                op.arity,
                op.fixity.value,
            )
            for symbol, op in spec.as_mapping().items()
        )
    )
    return ContractFingerprint(
        operators=operators,
        associativity="left",
        tie_breaking="leftmost-maximum",
        dinit=dinit,
        insert_explicit_concat=insert_explicit_concat,
    )
