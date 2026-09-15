# -*- coding: utf-8 -*-
"""Shared infrastructure for reconstructed JSS 2023 AST-EP and JSS 2025 HT-EP.

Python compatibility target: Python 3.8+ (standard library only).

This module intentionally separates:
1) expression tokenization / structural parsing, and
2) finite algebraic semantics used to materialize test sequences.

The papers define algorithms around algebraic-operation sets rather than one fixed
implementation.  The finite language operations below are a practical executable
instantiation of the equations used in the two papers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple, Union
import re

SequenceTuple = Tuple[str, ...]
Language = Set[SequenceTuple]


class ExpressionError(ValueError):
    pass


class UnsupportedOperatorError(ExpressionError):
    pass


class SequenceExplosionError(RuntimeError):
    pass


# Internal concatenation symbol. Both '.' and '&' in input normalize to this.
CONCAT = "."
CHOICE = "|"
INTERLEAVE = "||"
PARALLEL = "[]"
STAR = "*"


@dataclass(frozen=True)
class ConstraintSpec:
    raw: str


@dataclass
class Value:
    """A reduced subexpression.

    `language` is a finite set of event sequences. The empty tuple is epsilon.
    `top_choice_arity` preserves the syntactic top-level choice arity needed by
    the 2023 closure heuristic (Eq. 18).
    """

    language: Language
    text: str
    top_choice_arity: Optional[int] = None

    def copy(self) -> "Value":
        return Value(set(self.language), self.text, self.top_choice_arity)


@dataclass
class TraceStep:
    step: int
    algorithm: str
    scope: str
    operator: str
    rule: str
    before: str
    after: str
    result_count: int


@dataclass
class ASTNode:
    token: str
    left: Optional["ASTNode"] = None
    right: Optional["ASTNode"] = None

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    @property
    def arity(self) -> int:
        if self.is_leaf:
            return 0
        if self.right is None:
            return 1
        return 2


@dataclass
class HierarchyNode:
    tokens: List[Union[str, Value]]
    depth: int = 0
    child_spans: List[Tuple[int, int]] = field(default_factory=list)
    children: List["HierarchyNode"] = field(default_factory=list)
    result: Optional[Value] = None

    def expression_text(self) -> str:
        return tokens_to_text(self.tokens)


# ---------- Tokenization ----------

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:-]*")
_NUMBER_RE = re.compile(r"\d+")


def tokenize(expression: str) -> List[str]:
    """Tokenize the normalized expression dialect used by the baselines.

    Supported input surface:
      - operands: identifiers (including long action names), 0, 1
      - parentheses: ( )
      - binary: |, ||, [], . or & (concat)
      - postfix: *, integer repeat, /{...}, /Gamma, /Γ

    Whitespace is ignored. Implicit concatenation is not inserted here because
    the 2025 layer table is defined over symbols in the original expression.
    """
    s = expression.strip()
    tokens: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if s.startswith("||", i):
            tokens.append(INTERLEAVE)
            i += 2
            continue
        if s.startswith("[]", i):
            tokens.append(PARALLEL)
            i += 2
            continue
        if ch in "().&|*":
            tokens.append(CONCAT if ch == "&" else ch)
            i += 1
            continue
        if ch == "/":
            # Postfix constraint. Preserve as one token.
            if i + 1 < len(s) and s[i + 1] == "{":
                j = i + 2
                brace_depth = 1
                while j < len(s) and brace_depth:
                    if s[j] == "{":
                        brace_depth += 1
                    elif s[j] == "}":
                        brace_depth -= 1
                    j += 1
                if brace_depth != 0:
                    raise ExpressionError("Unclosed constraint starting at position %d" % i)
                tokens.append(s[i:j])
                i = j
                continue
            # /Γ or /Gamma or /identifier
            m = _IDENTIFIER_RE.match(s, i + 1)
            if m:
                tokens.append("/" + m.group(0))
                i = m.end()
                continue
            if i + 1 < len(s) and s[i + 1] == "Γ":
                tokens.append("/Γ")
                i += 2
                continue
            raise ExpressionError("Invalid constraint token at position %d" % i)
        m = _IDENTIFIER_RE.match(s, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
            continue
        m = _NUMBER_RE.match(s, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
            continue
        if ch == "Γ":
            tokens.append(ch)
            i += 1
            continue
        raise ExpressionError("Unsupported character %r at position %d" % (ch, i))
    if not tokens:
        raise ExpressionError("Expression is empty")

    # Legacy paper notation omits concatenation and commonly uses one lowercase
    # letter per alphabet symbol (e.g. "gh" means g followed by h).  In our
    # current software models, multi-character actions are separated explicitly
    # with '.' or '&'.  Auto-split lowercase runs only in the legacy no-explicit-
    # concat form so that the paper examples are reproduced without sacrificing
    # long action names in normalized experiments.
    if "." not in s and "&" not in s:
        expanded: List[str] = []
        for tok in tokens:
            if re.fullmatch(r"[a-z]+", tok or "") and len(tok) > 1:
                expanded.extend(list(tok))
            else:
                expanded.append(tok)
        tokens = expanded
    return tokens


def is_constraint_token(token: object) -> bool:
    return isinstance(token, str) and token.startswith("/")


def is_integer_token(token: object) -> bool:
    return isinstance(token, str) and token.isdigit() and token not in ("0", "1")


def is_postfix(token: object) -> bool:
    return token == STAR or is_constraint_token(token) or is_integer_token(token)


def is_binary_operator(token: object) -> bool:
    return token in (CONCAT, CHOICE, INTERLEAVE, PARALLEL)


def is_operand_token(token: object) -> bool:
    if isinstance(token, Value):
        return True
    if not isinstance(token, str):
        return False
    if token in ("(", ")", CONCAT, CHOICE, INTERLEAVE, PARALLEL, STAR):
        return False
    if is_constraint_token(token) or is_integer_token(token):
        return False
    return True


def _can_end_primary(token: object) -> bool:
    return is_operand_token(token) or token == ")" or is_postfix(token)


def _can_start_primary(token: object) -> bool:
    return is_operand_token(token) or token == "("


def insert_implicit_concat(tokens: Sequence[Union[str, Value]]) -> List[Union[str, Value]]:
    """Insert explicit concatenation between adjacent primary expressions."""
    out: List[Union[str, Value]] = []
    for idx, tok in enumerate(tokens):
        if idx > 0:
            prev = tokens[idx - 1]
            # Numeric 0/1 are operands when they appear as standalone tokens.
            # Integers >1 immediately following a primary are postfix repeats,
            # so they must not cause concatenation insertion.
            if _can_end_primary(prev) and _can_start_primary(tok):
                out.append(CONCAT)
        out.append(tok)
    return out


def tokens_to_text(tokens: Sequence[Union[str, Value]]) -> str:
    parts: List[str] = []
    for tok in tokens:
        if isinstance(tok, Value):
            parts.append(tok.text)
        else:
            parts.append(str(tok))
    return "".join(parts)


# ---------- Parenthesis / structural helpers ----------

def matching_parentheses(tokens: Sequence[Union[str, Value]]) -> Tuple[Dict[int, int], Dict[int, int]]:
    stack: List[int] = []
    open_to_close: Dict[int, int] = {}
    close_to_open: Dict[int, int] = {}
    for i, tok in enumerate(tokens):
        if tok == "(":
            stack.append(i)
        elif tok == ")":
            if not stack:
                raise ExpressionError("Unmatched ')' at token %d" % i)
            op = stack.pop()
            open_to_close[op] = i
            close_to_open[i] = op
    if stack:
        raise ExpressionError("Unmatched '(' at token %d" % stack[-1])
    return open_to_close, close_to_open


# ---------- Finite language semantics ----------

def _epsilon() -> Language:
    return {tuple()}


def atom_value(token: str) -> Value:
    if token == "0":
        return Value(set(), "0")
    if token == "1":
        return Value(_epsilon(), "1")
    return Value({(token,)}, token)


def _guard_size(language: Language, max_sequences: int) -> Language:
    if len(language) > max_sequences:
        raise SequenceExplosionError(
            "Generated %d sequences, exceeding max_sequences=%d" %
            (len(language), max_sequences)
        )
    return language


def choice_value(a: Value, b: Value, max_sequences: int) -> Value:
    lang = set(a.language)
    lang.update(b.language)
    left_arity = a.top_choice_arity if a.top_choice_arity is not None else 1
    right_arity = b.top_choice_arity if b.top_choice_arity is not None else 1
    return Value(_guard_size(lang, max_sequences), "(%s|%s)" % (a.text, b.text), left_arity + right_arity)


def concat_value(a: Value, b: Value, max_sequences: int) -> Value:
    if not a.language or not b.language:
        return Value(set(), "(%s.%s)" % (a.text, b.text))
    lang: Language = set()
    for x in a.language:
        for y in b.language:
            lang.add(x + y)
            if len(lang) > max_sequences:
                _guard_size(lang, max_sequences)
    return Value(lang, "(%s.%s)" % (a.text, b.text))


def _shuffle_two(a: SequenceTuple, b: SequenceTuple) -> Set[SequenceTuple]:
    memo: Dict[Tuple[int, int], Set[SequenceTuple]] = {}

    def rec(i: int, j: int) -> Set[SequenceTuple]:
        key = (i, j)
        if key in memo:
            return memo[key]
        if i == len(a):
            ans = {b[j:]}
        elif j == len(b):
            ans = {a[i:]}
        else:
            ans: Set[SequenceTuple] = set()
            for tail in rec(i + 1, j):
                ans.add((a[i],) + tail)
            for tail in rec(i, j + 1):
                ans.add((b[j],) + tail)
        memo[key] = ans
        return ans

    return rec(0, 0)


def interleave_value(a: Value, b: Value, max_sequences: int) -> Value:
    if not a.language or not b.language:
        return Value(set(), "(%s||%s)" % (a.text, b.text))
    lang: Language = set()
    for x in a.language:
        for y in b.language:
            lang.update(_shuffle_two(x, y))
            if len(lang) > max_sequences:
                _guard_size(lang, max_sequences)
    return Value(lang, "(%s||%s)" % (a.text, b.text))


def parallel_value(a: Value, b: Value, max_sequences: int) -> Value:
    """Finite executable form of the 2025 concurrency equations.

    Main rule: a[]b = a | b(a||b), with special identities 0[]a=a and
    1[]a=1|a. The language-level implementation follows those equations.
    """
    if not a.language:  # 0 [] a = a
        return b.copy()
    if a.language == _epsilon():  # 1 [] a = 1 | a
        return choice_value(a, b, max_sequences)
    shuffled = interleave_value(a, b, max_sequences)
    right_then_shuffle = concat_value(b, shuffled, max_sequences)
    result = choice_value(a, right_then_shuffle, max_sequences)
    result.text = "(%s[]%s)" % (a.text, b.text)
    return result


def repeat_value(a: Value, count: int, max_sequences: int) -> Value:
    if count < 0:
        raise ExpressionError("Negative repetition is not supported")
    result = Value(_epsilon(), "1")
    for _ in range(count):
        result = concat_value(result, a, max_sequences)
    result.text = "(%s)%d" % (a.text, count)
    return result


def bounded_star_value(a: Value, max_repeat: int, max_sequences: int) -> Value:
    lang: Language = set(_epsilon())
    power = Value(_epsilon(), "1")
    for _ in range(1, max_repeat + 1):
        power = concat_value(power, a, max_sequences)
        lang.update(power.language)
        _guard_size(lang, max_sequences)
    return Value(lang, "(%s)*" % a.text)


def positive_closure_value(a: Value, max_repeat: int, max_sequences: int) -> Value:
    star = bounded_star_value(a, max_repeat, max_sequences)
    result = concat_value(a, star, max_sequences)
    result.text = "(%s)+" % a.text
    return result


def parse_constraint(token: str) -> ConstraintSpec:
    return ConstraintSpec(token)


def apply_constraint_default(a: Value, token: str, max_sequences: int) -> Value:
    """Default executable interpretation of /Gamma-style constraints.

    The papers leave the concrete satisfaction relation domain-dependent.
    This default supports the commonly shown length constraint /{#LEN=n},
    /{1}, and simple required-event constraints /{a,b,...}.
    Users can inject another constraint callback in AlgebraEngine.
    """
    raw = token[1:]
    if raw.startswith("{") and raw.endswith("}"):
        body = raw[1:-1].strip()
    else:
        body = raw.strip()

    m = re.fullmatch(r"#?LEN\s*=\s*(\d+)", body, flags=re.IGNORECASE)
    if m:
        target = int(m.group(1))
        lang = {seq for seq in a.language if len(seq) == target}
        return Value(lang, "%s%s" % (a.text, token))

    if body in ("", "Γ", "Gamma"):
        # No concrete semantics are available from the expression alone.
        raise UnsupportedOperatorError(
            "Constraint %s has no executable satisfaction predicate. "
            "Use /{#LEN=n}, /{event,...}, or provide constraint_handler." % token
        )
    if body == "1":
        return Value(set(a.language), "%s%s" % (a.text, token), a.top_choice_arity)

    required = [x.strip() for x in re.split(r"[,;]", body) if x.strip()]
    lang = {seq for seq in a.language if all(req in seq for req in required)}
    return Value(lang, "%s%s" % (a.text, token))


ConstraintHandler = Callable[[Value, str, int], Value]


class AlgebraEngine(object):
    """Shared finite semantic engine for paper-defined operators."""

    def __init__(self, max_sequences: int = 100000,
                 constraint_handler: Optional[ConstraintHandler] = None):
        self.max_sequences = max_sequences
        self.constraint_handler = constraint_handler or apply_constraint_default

    def binary(self, op: str, left: Value, right: Value) -> Tuple[Value, str]:
        if op == CONCAT:
            return concat_value(left, right, self.max_sequences), "concatenation"
        if op == CHOICE:
            return choice_value(left, right, self.max_sequences), "choice"
        if op == INTERLEAVE:
            return interleave_value(left, right, self.max_sequences), "alternation/interleaving"
        if op == PARALLEL:
            return parallel_value(left, right, self.max_sequences), "concurrency/parallel"
        raise UnsupportedOperatorError("Unsupported binary operator: %s" % op)

    def postfix(self, op: str, operand: Value, star_bound: int) -> Tuple[Value, str]:
        if op == STAR:
            return bounded_star_value(operand, star_bound, self.max_sequences), "bounded Kleene closure"
        if is_integer_token(op):
            return repeat_value(operand, int(op), self.max_sequences), "numeric repetition"
        if is_constraint_token(op):
            return self.constraint_handler(operand, op, self.max_sequences), "constraint"
        raise UnsupportedOperatorError("Unsupported postfix operator: %s" % op)


# ---------- AST construction (executable replacement for unavailable modified RE2) ----------

class _Parser(object):
    def __init__(self, tokens: Sequence[str]):
        self.tokens = [str(x) for x in insert_implicit_concat(tokens)]
        self.pos = 0

    def peek(self) -> Optional[str]:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def take(self, expected: Optional[str] = None) -> str:
        tok = self.peek()
        if tok is None:
            raise ExpressionError("Unexpected end of expression")
        if expected is not None and tok != expected:
            raise ExpressionError("Expected %r, got %r" % (expected, tok))
        self.pos += 1
        return tok

    def parse(self) -> ASTNode:
        node = self.parse_choice()
        if self.peek() is not None:
            raise ExpressionError("Unexpected token %r" % self.peek())
        return node

    def parse_choice(self) -> ASTNode:
        node = self.parse_parallel()
        while self.peek() == CHOICE:
            op = self.take()
            rhs = self.parse_parallel()
            node = ASTNode(op, node, rhs)
        return node

    def parse_parallel(self) -> ASTNode:
        node = self.parse_concat()
        while self.peek() in (INTERLEAVE, PARALLEL):
            op = self.take()
            rhs = self.parse_concat()
            node = ASTNode(op, node, rhs)
        return node

    def parse_concat(self) -> ASTNode:
        node = self.parse_postfix()
        while self.peek() == CONCAT:
            op = self.take()
            rhs = self.parse_postfix()
            node = ASTNode(op, node, rhs)
        return node

    def parse_postfix(self) -> ASTNode:
        node = self.parse_primary()
        while True:
            tok = self.peek()
            if tok == STAR or is_integer_token(tok) or is_constraint_token(tok):
                op = self.take()
                node = ASTNode(op, node, None)
            else:
                break
        return node

    def parse_primary(self) -> ASTNode:
        tok = self.peek()
        if tok == "(":
            self.take("(")
            node = self.parse_choice()
            self.take(")")
            return node
        if tok is None or tok == ")" or is_binary_operator(tok) or is_postfix(tok):
            raise ExpressionError("Expected operand, got %r" % tok)
        self.take()
        return ASTNode(tok)


def build_ast(expression: str) -> ASTNode:
    return _Parser(tokenize(expression)).parse()


def postorder_tokens(root: ASTNode) -> List[str]:
    out: List[str] = []

    def visit(node: ASTNode) -> None:
        if node.left is not None:
            visit(node.left)
        if node.right is not None:
            visit(node.right)
        out.append(node.token)

    visit(root)
    return out


def ast_node_count(root: ASTNode) -> int:
    return 1 + (ast_node_count(root.left) if root.left else 0) + (ast_node_count(root.right) if root.right else 0)


def ast_height(root: ASTNode) -> int:
    if root is None:
        return 0
    return 1 + max(ast_height(root.left) if root.left else 0,
                   ast_height(root.right) if root.right else 0)


def language_to_strings(language: Language, separator: str = "") -> List[str]:
    """Stable string view of a language. Epsilon is rendered as '1'."""
    result: List[str] = []
    for seq in language:
        if not seq:
            result.append("1")
        else:
            result.append(separator.join(seq))
    return sorted(result, key=lambda x: (len(x), x))
