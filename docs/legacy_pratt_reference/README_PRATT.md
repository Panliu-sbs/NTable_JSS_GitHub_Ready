# Contract-aligned Pratt baseline

This project adds a direct Pratt / precedence-climbing parser for comparison with N-Table.

## Design goal

The Pratt baseline uses the **same operator specification and tokenizer** as N-Table.  In particular:

- `W`: larger rank means stronger binding;
- arity and fixity come from the same `OperatorSpec`;
- binary infix operators are left-associative by default, matching the current paper instantiation;
- longest-match tokenization, multi-character operands, explicit concatenation insertion, and parentheses are shared with N-Table;
- Pratt directly constructs an operator AST and does **not** construct an N-Table dominance row.

This makes it suitable for the paper's contract-aligned Pratt baseline.

## Quick use with W

```python
from ntable import PrattParser

W = {
    "|": 0,
    "||": 1,
    "[]": 1,
    ".": 2,
    "*": 3,
}

parser = PrattParser.from_w(W)
ast = parser.parse("a.b.(c||d|e*)")
print(ast.prefix())
```

For the operators in the default N-Table contract, `from_w()` automatically reuses the default arity/fixity declarations. For a new operator symbol, provide `arity=` and `fixity=` explicitly.

## Use exactly the same OperatorSpec as N-Table

This is the preferred form for fair experiments:

```python
from ntable import NTableBuilder, PrattParser

nt = NTableBuilder()
pratt = PrattParser(nt.spec)

ast = pratt.parse("a.b.(c||d|e*)")
```

Both implementations now receive the same ranks, arity declarations, fixity declarations, normalization options, and operand tokenization rules.

## Excluding tokenization from timing

For structural-construction timing, normalize once and provide the same tokens to each algorithm:

```python
tokens = pratt.normalize("a.b.(c||d|e*)")
pratt_ast = pratt.parse_tokens(tokens)
```

The same token tuple can be passed to `NTableBuilder.build_tokens(tokens)`.

## Custom arity/fixity

```python
from ntable import PrattParser

W = {"+": 0, "!": 2}
A = {"+": 2, "!": 1}
F = {"+": "infix", "!": "postfix"}

parser = PrattParser.from_w(W, arity=A, fixity=F)
```

## Associativity

All binary operators default to left associativity.  To declare right associativity for a particular operator:

```python
parser = PrattParser.from_w(
    {"^": 3},
    arity={"^": 2},
    fixity={"^": "infix"},
    associativity={"^": "right"},
)
```

## Tests

Run:

```bash
python -m unittest discover -s tests -v
```

The Pratt tests check:

- agreement with N-Table on representative expressions under the same contract;
- left associativity;
- parentheses;
- postfix closure;
- implicit concatenation;
- descriptive multi-character operands;
- custom `W` precedence;
- right associativity when explicitly requested.
