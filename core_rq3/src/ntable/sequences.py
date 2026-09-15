from __future__ import annotations

from typing import Callable, Dict, Iterable, Iterator, List, Sequence, Tuple

from .model import AstNode


SequenceT = Tuple[str, ...]
BinaryHandler = Callable[[List[SequenceT], List[SequenceT], int], List[SequenceT]]
UnaryHandler = Callable[[List[SequenceT], int], List[SequenceT]]


class UnsupportedOperatorError(ValueError):
    pass


def _dedupe_limited(items: Iterable[SequenceT], limit: int) -> List[SequenceT]:
    seen: Dict[SequenceT, None] = {}
    for item in items:
        if item not in seen:
            seen[item] = None
            if len(seen) >= limit:
                break
    return list(seen)


def _concat(
    left: List[SequenceT], right: List[SequenceT], limit: int
) -> List[SequenceT]:
    def gen() -> Iterator[SequenceT]:
        for a in left:
            for b in right:
                yield a + b
    return _dedupe_limited(gen(), limit)


def _choice(
    left: List[SequenceT], right: List[SequenceT], limit: int
) -> List[SequenceT]:
    return _dedupe_limited((*left, *right), limit)


def _interleave_one(a: SequenceT, b: SequenceT, limit: int) -> List[SequenceT]:
    # Memoized suffix DP. Left-first expansion gives deterministic order:
    # for (c) || (d), c.d is emitted before d.c.
    memo: Dict[Tuple[int, int], List[SequenceT]] = {}

    def rec(i: int, j: int) -> List[SequenceT]:
        key = (i, j)
        cached = memo.get(key)
        if cached is not None:
            return cached
        if i == len(a):
            ans = [b[j:]]
        elif j == len(b):
            ans = [a[i:]]
        else:
            vals: List[SequenceT] = []
            for suffix in rec(i + 1, j):
                vals.append((a[i],) + suffix)
                if len(vals) >= limit:
                    break
            if len(vals) < limit:
                for suffix in rec(i, j + 1):
                    vals.append((b[j],) + suffix)
                    if len(vals) >= 2 * limit:
                        break
            ans = _dedupe_limited(vals, limit)
        memo[key] = ans
        return ans

    return rec(0, 0)


def _interleave(
    left: List[SequenceT], right: List[SequenceT], limit: int
) -> List[SequenceT]:
    out: Dict[SequenceT, None] = {}
    for a in left:
        for b in right:
            for seq in _interleave_one(a, b, limit - len(out)):
                out.setdefault(seq, None)
                if len(out) >= limit:
                    return list(out)
    return list(out)


class SequenceGenerator:
    """
    Bounded sequence-language evaluator over the reconstructed AST.

    Built-ins:
      .   concatenation
      |   choice
      ||  order-preserving interleaving
      *   bounded Kleene closure

    Other extended operators require an explicitly registered handler.
    """

    __slots__ = (
        "max_star_repeats",
        "limit",
        "_binary_handlers",
        "_unary_handlers",
    )

    def __init__(
        self,
        *,
        max_star_repeats: int = 1,
        limit: int = 10_000,
    ) -> None:
        if max_star_repeats < 0:
            raise ValueError("max_star_repeats must be >= 0")
        if limit <= 0:
            raise ValueError("limit must be > 0")
        self.max_star_repeats = max_star_repeats
        self.limit = limit
        self._binary_handlers: Dict[str, BinaryHandler] = {
            ".": _concat,
            "|": _choice,
            "||": _interleave,
        }
        self._unary_handlers: Dict[str, UnaryHandler] = {}

    def register_binary(self, operator: str, handler: BinaryHandler) -> None:
        self._binary_handlers[operator] = handler

    def register_unary(self, operator: str, handler: UnaryHandler) -> None:
        self._unary_handlers[operator] = handler

    def generate(self, root: AstNode) -> List[SequenceT]:
        return self._eval(root)

    def generate_strings(self, root: AstNode, sep: str = ".") -> List[str]:
        return [sep.join(seq) if seq else "ε" for seq in self.generate(root)]

    def _eval(self, node: AstNode) -> List[SequenceT]:
        if node.is_leaf:
            return [(node.label,)]

        if node.label == "*":
            if node.left is None or node.right is not None:
                raise ValueError("Malformed unary '*' node")
            base = self._eval(node.left)
            result: List[SequenceT] = [()]
            power: List[SequenceT] = [()]
            for _ in range(self.max_star_repeats):
                power = _concat(power, base, self.limit)
                result = _dedupe_limited((*result, *power), self.limit)
                if len(result) >= self.limit:
                    break
            return result

        if node.right is None:
            if node.left is None:
                raise ValueError(f"Malformed unary node {node.label!r}")
            handler = self._unary_handlers.get(node.label)
            if handler is None:
                raise UnsupportedOperatorError(
                    f"No sequence-generation semantics registered for unary "
                    f"operator {node.label!r}"
                )
            return handler(self._eval(node.left), self.limit)

        if node.left is None:
            raise ValueError(f"Malformed binary node {node.label!r}")

        handler = self._binary_handlers.get(node.label)
        if handler is None:
            raise UnsupportedOperatorError(
                f"No sequence-generation semantics registered for binary "
                f"operator {node.label!r}"
            )
        return handler(self._eval(node.left), self._eval(node.right), self.limit)
