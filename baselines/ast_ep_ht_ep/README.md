# Python 3.8 reconstruction of JSS 2023 AST-EP and JSS 2025 HT-EP

This directory contains an **independent reconstruction from the two papers**, not the
original Java source code.

- `ast_ep_2023.py` — AST-EP from JSS 2023, 111798.
- `ht_ep_2025.py` — HT-EP from JSS 2025, 112354.
- `common.py` — tokenizer, AST builder, finite algebraic semantics, trace structures.
- `demo.py` — reproduces the main examples in the papers.
- `test_reconstruction.py` — regression tests against paper examples.
- `paper_reconstruction_notes.md` — source-to-code mapping and ambiguities.

## Python version

Target: **Python 3.8+**. The code uses only the Python standard library.

Run:

```bash
python -m unittest -v test_reconstruction.py
python demo.py
```

Examples:

```bash
python ast_ep_2023.py "(a|b)c(d|e*)(f||gh)" --trace
python ht_ep_2025.py "(a|(b||k)2)c(d|e)" --trace
python ht_ep_2025.py "Open.File.(New|Merge).Close" --separator .
```

## Accepted expression syntax

The implementation accepts the paper-style syntax and the normalized syntax used by
our current N-Table experiments:

- concatenation: implicit adjacency, `.` or `&`;
- choice: `|`;
- alternation/interleaving: `||`;
- concurrency/parallel: `[]`;
- Kleene closure: postfix `*`;
- exact loop count: postfix integer such as `2`;
- constraint: postfix `/{#LEN=4}`, `/{event1,event2}`, `/Γ` (the last form needs a custom predicate);
- parentheses: `(...)`.

Long software-action names are supported, e.g. `OpenJMeter.File.Template.Merge`.

## Important reproducibility choice

The 2023 paper constructs the AST with a modified Google RE2 implementation, but that
modified implementation is not specified in enough detail in the paper to reproduce it
byte-for-byte. This package therefore uses an independent deterministic AST parser with
the operator precedence documented by the 2025 paper:

1. postfix constraint / closure / repeat;
2. concatenation;
3. `||` and `[]`;
4. choice `|`.

Equal-precedence binary operators associate left-to-right. For a fair three-way
experiment (2023 AST-EP, 2025 HT-EP, N-Table), use the same normalized expression and
operator contract for every method.

## Sequence representation

Internally, a sequence is a tuple of action tokens. This avoids ambiguity for multi-word
actions. Output uses no separator by default to reproduce paper examples; set
`separator='.'` for real-software models.

## Safety against combinatorial explosion

Both classes accept `max_sequences` (default 100000). If an expression generates more,
`SequenceExplosionError` is raised instead of exhausting memory.
