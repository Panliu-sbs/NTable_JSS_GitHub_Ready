from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .spec import Fixity, OperatorSpec


@dataclass(frozen=True)
class NormalizationOptions:
    insert_explicit_concat: bool = True


@dataclass(frozen=True)
class ReuseTokenization:
    """One normalization result containing all hot-path reuse data.

    grouped_tokens:
        Normalized sequence S0 with grouping parentheses retained.
    flat_tokens:
        Current expression's S with grouping parentheses omitted.
    operands:
        Operand occurrences from S in left-to-right order. These bind directly
        to the cached AST-template slots on a reuse hit.
    structural_signature:
        Collision-safe canonical encoding of Skel(S0).
    """

    grouped_tokens: Tuple[str, ...]
    flat_tokens: Tuple[str, ...]
    operands: Tuple[str, ...]
    structural_signature: str


class Tokenizer:
    """Longest-match tokenizer with template-reuse-aware normalization."""

    __slots__ = ("spec", "options")

    _OPERAND_MARKER = "A;"
    _LPAREN_MARKER = "L;"
    _RPAREN_MARKER = "R;"

    def __init__(
        self,
        spec: OperatorSpec,
        options: Optional[NormalizationOptions] = None,
    ) -> None:
        self.spec = spec
        self.options = options or NormalizationOptions()

    def tokenize(self, expression: str) -> List[str]:
        return list(self.tokenize_for_reuse(expression).grouped_tokens)

    def tokenize_for_reuse(self, expression: str) -> ReuseTokenization:
        """Normalize and simultaneously obtain S0, S, operands, and signature."""
        raw = self._lex(expression)
        return self._normalize_and_encode(raw)

    def encode_normalized_tokens(
        self, tokens: Tuple[str, ...]
    ) -> ReuseTokenization:
        self._validate_parentheses(list(tokens))
        grouped = tuple(tokens)
        flat: List[str] = []
        operands: List[str] = []
        signature_parts: List[str] = []
        for tok in grouped:
            self._append_flat_operands_and_signature(
                tok, flat, operands, signature_parts
            )
        return ReuseTokenization(
            grouped_tokens=grouped,
            flat_tokens=tuple(flat),
            operands=tuple(operands),
            structural_signature="".join(signature_parts),
        )

    def decode_signature(self, signature: str) -> Tuple[str, ...]:
        """Decode the canonical signature into the paper-style omega skeleton."""
        out: List[str] = []
        i = 0
        n = len(signature)
        while i < n:
            if signature.startswith(self._OPERAND_MARKER, i):
                out.append("ω")
                i += len(self._OPERAND_MARKER)
                continue
            if signature.startswith(self._LPAREN_MARKER, i):
                out.append("(")
                i += len(self._LPAREN_MARKER)
                continue
            if signature.startswith(self._RPAREN_MARKER, i):
                out.append(")")
                i += len(self._RPAREN_MARKER)
                continue
            if signature[i] != "O":
                raise ValueError("Malformed structural signature")

            j = i + 1
            while j < n and signature[j].isdigit():
                j += 1
            if j == i + 1 or j >= n or signature[j] != ":":
                raise ValueError("Malformed operator marker in structural signature")
            length = int(signature[i + 1 : j])
            start = j + 1
            end = start + length
            if end >= n or signature[end] != ";":
                raise ValueError("Malformed length-prefixed operator marker")
            out.append(signature[start:end])
            i = end + 1
        return tuple(out)

    def structural_pattern(self, expression: str) -> str:
        """Human-readable token-level structural rule, e.g. `ω.ω|(ω*)`."""
        return "".join(self.decode_signature(
            self.tokenize_for_reuse(expression).structural_signature
        ))

    # ------------------------------------------------------------------
    # Lexing
    # ------------------------------------------------------------------

    def _lex(self, expression: str) -> List[str]:
        s = "".join(expression.split())
        if not s:
            raise ValueError("Expression is empty")

        tokens: List[str] = []
        i = 0
        ops = self.spec.symbols_longest_first

        while i < len(s):
            ch = s[i]

            if ch in "()":
                tokens.append(ch)
                i += 1
                continue

            matched = None
            for op in ops:
                if s.startswith(op, i):
                    matched = op
                    break
            if matched is not None:
                tokens.append(matched)
                i += len(matched)
                continue

            if ch == "$":
                j = i + 1
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                tokens.append(s[i:j])
                i = j
                continue

            j = i + 1
            while j < len(s):
                if s[j] in "()":
                    break
                if any(s.startswith(op, j) for op in ops):
                    break
                if s[j] == "$":
                    break
                j += 1
            token = s[i:j]
            if not token:
                raise ValueError(f"Cannot tokenize near offset {i}: {s[i:i+12]!r}")
            tokens.append(token)
            i = j

        return tokens

    # ------------------------------------------------------------------
    # Normalization + reuse encoding
    # ------------------------------------------------------------------

    def _normalize_and_encode(self, raw: List[str]) -> ReuseTokenization:
        grouped: List[str] = []
        flat: List[str] = []
        operands: List[str] = []
        signature_parts: List[str] = []
        depth = 0

        prev: Optional[str] = None
        for cur in raw:
            if (
                prev is not None
                and self.options.insert_explicit_concat
                and self._can_end_operand(prev)
                and self._can_start_operand(cur)
            ):
                grouped.append(".")
                flat.append(".")
                signature_parts.append(self._operator_marker("."))

            grouped.append(cur)

            if cur == "(":
                depth += 1
                signature_parts.append(self._LPAREN_MARKER)
            elif cur == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced parentheses")
                signature_parts.append(self._RPAREN_MARKER)
            else:
                flat.append(cur)
                if cur in self.spec:
                    signature_parts.append(self._operator_marker(cur))
                else:
                    operands.append(cur)
                    signature_parts.append(self._OPERAND_MARKER)

            prev = cur

        if depth != 0:
            raise ValueError("Unbalanced parentheses")

        return ReuseTokenization(
            grouped_tokens=tuple(grouped),
            flat_tokens=tuple(flat),
            operands=tuple(operands),
            structural_signature="".join(signature_parts),
        )

    def _append_flat_operands_and_signature(
        self,
        tok: str,
        flat: List[str],
        operands: List[str],
        signature_parts: List[str],
    ) -> None:
        if tok == "(":
            signature_parts.append(self._LPAREN_MARKER)
        elif tok == ")":
            signature_parts.append(self._RPAREN_MARKER)
        else:
            flat.append(tok)
            if tok in self.spec:
                signature_parts.append(self._operator_marker(tok))
            else:
                operands.append(tok)
                signature_parts.append(self._OPERAND_MARKER)

    @staticmethod
    def _operator_marker(op: str) -> str:
        return f"O{len(op)}:{op};"

    def _can_end_operand(self, tok: str) -> bool:
        if tok == ")":
            return True
        if tok in self.spec:
            op = self.spec[tok]
            return op.arity == 1 and op.fixity is Fixity.POSTFIX
        return tok != "("

    def _can_start_operand(self, tok: str) -> bool:
        if tok == "(":
            return True
        if tok in self.spec:
            op = self.spec[tok]
            return op.arity == 1 and op.fixity is Fixity.PREFIX
        return tok != ")"

    @staticmethod
    def _validate_parentheses(tokens: List[str]) -> None:
        depth = 0
        for tok in tokens:
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced parentheses")
        if depth:
            raise ValueError("Unbalanced parentheses")
