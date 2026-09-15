from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from .model import AstNode
from .spec import Fixity, Operator, OperatorSpec, default_operator_spec
from .tokenizer import NormalizationOptions, Tokenizer


Associativity = str


@dataclass(frozen=True)
class PrattParseResult:
    """Result container useful for experiments and diagnostics."""

    normalized_tokens: Tuple[str, ...]
    ast: AstNode


class PrattParser:
    """Contract-aligned Pratt / precedence-climbing parser.

    The parser is designed to be a fair baseline for the N-Table implementation:

    * it uses the same ``OperatorSpec`` object as N-Table, so the operator ranks
      (W), arity declarations, and fixity declarations are identical;
    * it uses the same ``Tokenizer`` and normalization option;
    * larger rank values mean stronger binding, exactly as in N-Table;
    * binary infix operators are left-associative by default, matching the
      current paper instantiation, but per-operator right associativity can be
      supplied when needed;
    * prefix and postfix unary operators are supported when declared in the
      operator specification.

    Unlike N-Table, this parser constructs the operator AST directly and does
    not materialize a dominance row D.
    """

    __slots__ = (
        "spec",
        "tokenizer",
        "_assoc",
        "_tokens",
        "_pos",
    )

    def __init__(
        self,
        spec: Optional[OperatorSpec] = None,
        *,
        associativity: Optional[Mapping[str, Associativity]] = None,
        insert_explicit_concat: bool = True,
    ) -> None:
        self.spec = spec or default_operator_spec()
        self.tokenizer = Tokenizer(
            self.spec,
            NormalizationOptions(insert_explicit_concat=insert_explicit_concat),
        )

        assoc: Dict[str, Associativity] = {}
        supplied = dict(associativity or {})
        for symbol, op in self.spec.as_mapping().items():
            if op.arity == 2:
                value = supplied.pop(symbol, "left")
                if value not in {"left", "right"}:
                    raise ValueError(
                        f"Associativity for {symbol!r} must be 'left' or 'right', "
                        f"got {value!r}"
                    )
                assoc[symbol] = value

        if supplied:
            unknown = ", ".join(sorted(supplied))
            raise ValueError(f"Associativity supplied for unknown/non-binary operators: {unknown}")

        self._assoc = assoc
        self._tokens: Tuple[str, ...] = ()
        self._pos = 0

    @classmethod
    def from_w(
        cls,
        W: Mapping[str, int],
        *,
        arity: Optional[Mapping[str, int]] = None,
        fixity: Optional[Mapping[str, Union[Fixity, str]]] = None,
        associativity: Optional[Mapping[str, Associativity]] = None,
        insert_explicit_concat: bool = True,
    ) -> "PrattParser":
        """Construct a parser from an input operator-rank map W.

        Parameters
        ----------
        W:
            Mapping ``operator -> rank``. Larger rank means stronger binding.
        arity, fixity:
            Structural declarations required by Pratt parsing. For operators in
            ``default_operator_spec()``, omitted declarations are inherited from
            that default contract. For any new operator symbol, both arity and
            fixity must be provided explicitly.
        associativity:
            Optional per-binary-operator map, defaulting to ``left``.

        This helper makes the experimental input close to the paper notation:
        W supplies ranks, while arity/fixity/associativity supply the remaining
        reconstruction-contract information needed by any precedence parser.
        """
        if not W:
            raise ValueError("W must contain at least one operator")

        arity_map = dict(arity or {})
        fixity_map = dict(fixity or {})
        defaults = default_operator_spec()
        operators: List[Operator] = []

        for symbol, rank in W.items():
            if symbol in arity_map:
                op_arity = arity_map[symbol]
            elif symbol in defaults:
                op_arity = defaults.arity(symbol)
            else:
                raise ValueError(
                    f"Arity for custom operator {symbol!r} is required when using from_w()"
                )

            if symbol in fixity_map:
                raw_fixity = fixity_map[symbol]
                op_fixity = raw_fixity if isinstance(raw_fixity, Fixity) else Fixity(raw_fixity)
            elif symbol in defaults:
                op_fixity = defaults.fixity(symbol)
            else:
                raise ValueError(
                    f"Fixity for custom operator {symbol!r} is required when using from_w()"
                )

            operators.append(Operator(symbol, int(rank), int(op_arity), op_fixity))

        spec = OperatorSpec(operators)
        return cls(
            spec,
            associativity=associativity,
            insert_explicit_concat=insert_explicit_concat,
        )

    @property
    def associativity(self) -> Mapping[str, Associativity]:
        return dict(self._assoc)

    def normalize(self, expression: str) -> Tuple[str, ...]:
        """Normalize/tokenize using the same tokenizer used by N-Table."""
        return tuple(self.tokenizer.tokenize(expression))

    def parse(self, expression: str) -> AstNode:
        """Normalize/tokenize an expression and directly construct its AST."""
        return self.parse_tokens(self.normalize(expression))

    def parse_with_result(self, expression: str) -> PrattParseResult:
        tokens = self.normalize(expression)
        return PrattParseResult(tokens, self.parse_tokens(tokens))

    def parse_tokens(self, tokens: Sequence[str]) -> AstNode:
        """Parse an already-normalized token sequence.

        This method is useful for fair timing experiments in which N-Table and
        Pratt receive the exact same normalized token sequence and tokenization
        time is excluded from the structural-construction measurement.
        """
        self._tokens = tuple(tokens)
        self._pos = 0
        if not self._tokens:
            raise ValueError("Cannot parse an empty token sequence")

        ast = self._parse_expression(min_rank=None)
        if self._pos != len(self._tokens):
            tok = self._tokens[self._pos]
            if tok == ")":
                raise ValueError("Unmatched closing parenthesis")
            raise ValueError(
                f"Unexpected trailing token {tok!r} at normalized token index {self._pos}"
            )
        return ast

    # ------------------------------------------------------------------
    # Pratt / precedence-climbing core
    # ------------------------------------------------------------------

    def _peek(self) -> Optional[str]:
        if self._pos >= len(self._tokens):
            return None
        return self._tokens[self._pos]

    def _advance(self) -> str:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        self._pos += 1
        return tok

    def _parse_expression(self, min_rank: Optional[int]) -> AstNode:
        left = self._parse_nud()

        while True:
            tok = self._peek()
            if tok is None or tok == ")":
                break

            if tok not in self.spec:
                raise ValueError(
                    f"Expected an operator at normalized token index {self._pos}, got {tok!r}"
                )

            op = self.spec[tok]
            rank = op.rank
            if min_rank is not None and rank < min_rank:
                break

            # Postfix unary operator: consumes the completed left expression.
            if op.arity == 1 and op.fixity is Fixity.POSTFIX:
                self._advance()
                left = AstNode(tok, left, None)
                continue

            # A prefix unary operator is only valid in nud (operand) position.
            if op.arity == 1 and op.fixity is Fixity.PREFIX:
                raise ValueError(
                    f"Prefix operator {tok!r} cannot appear after an operand at token index {self._pos}"
                )

            if op.arity != 2 or op.fixity is not Fixity.INFIX:
                raise ValueError(f"Unsupported operator declaration for {tok!r}")

            self._advance()
            assoc = self._assoc[tok]

            # Larger rank = stronger binding.  For left-associative operators,
            # the RHS must bind strictly more strongly than the current rank;
            # rank+1 is valid because ranks are integer-valued in W.  For a
            # right-associative operator, equal rank is allowed on the RHS.
            rhs_min = rank + 1 if assoc == "left" else rank
            right = self._parse_expression(rhs_min)
            left = AstNode(tok, left, right)

        return left

    def _parse_nud(self) -> AstNode:
        tok = self._advance()

        if tok == "(":
            if self._peek() == ")":
                raise ValueError("Empty parenthesized subexpression")
            inner = self._parse_expression(min_rank=None)
            if self._peek() != ")":
                raise ValueError("Unbalanced parentheses: expected ')'")
            self._advance()
            return inner

        if tok == ")":
            raise ValueError("Unexpected closing parenthesis")

        if tok in self.spec:
            op = self.spec[tok]
            if op.arity == 1 and op.fixity is Fixity.PREFIX:
                # Prefix operator binds its operand according to its rank.
                operand = self._parse_expression(op.rank)
                return AstNode(tok, operand, None)
            raise ValueError(
                f"Operator {tok!r} cannot begin an operand region under its declared fixity"
            )

        # Any non-operator token is an atomic operand under the normalization
        # contract, including descriptive multi-character identifiers.
        return AstNode(tok)
