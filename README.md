# N-Table: Reviewer Replication Package

This repository accompanies the manuscript:

> **N-Table: A Numeric Structural Representation for Deterministic AST Construction and Structural Reuse in Extended Expressions**

The repository provides the runnable N-Table implementation, the shared-topology reuse mechanism used in RQ3, the contract-aligned Pratt baseline, archived RQ3 data and results, figure-reproduction materials, and independent paper-based reconstructions of AST-EP and HT-EP.

The repository is organized around the manuscript's current **shared-topology reuse** design. The obsolete D-only reuse experiment is intentionally excluded from the authoritative experiment path to avoid version ambiguity.

---

## Reviewer Quick Start

The following commands are sufficient to verify the main runnable artifacts.

### 1. Run the N-Table / shared-topology tests

From the repository root:

```bash
cd core_rq3
PYTHONPATH=src python -m unittest discover -s tests -v
```

Expected result:

```text
Ran 12 tests
OK
```

The tests cover dominance-row construction, structural signatures, shared-topology identity, operand binding, explicit AST materialization, lazy navigation, repository hit accounting, and differential checks for numeric assignment.

### 2. Re-run the RQ3 experiment

From `core_rq3/`:

```bash
python experiments/run_shared_topology_incremental_3000.py \
  --input ../data/rq3/generated_3000_structurally_similar_expressions.csv \
  --output-dir ../reproduced_results/rq3
```

The experiment uses the manuscript protocol:

- 3,000 generated expressions;
- fixed random seed `20260914`;
- incremental batches of 200 expressions;
- a persistent structural repository across batches;
- one warm-up full execution;
- ten measured repetitions;
- median runtime reporting.

It compares three workflows:

1. **Fresh N-Table** — constructs the dominance row and an independent materialized AST for each expression;
2. **N-Table Shared-Reuse** — reuses the stored dominance row and immutable operator topology and returns a bound representation `BoundAst = <topology, operands>`;
3. **Direct Pratt** — parses each expression independently and constructs an independent materialized AST.

On a reuse hit, Shared-Reuse does not repeat dominance assignment, max-root recursion, or allocation of another copy of the stored operator topology.

### 3. Reproduce the RQ3 figures

Install the plotting dependencies from the repository root:

```bash
python -m pip install -r figures/rq3/requirements.txt
```

Then run:

```bash
cd figures/rq3
python plot_rq3_structural_reusability_jupyter.py
```

Alternatively, open:

```text
figures/rq3/RQ3_Structural_Reusability_Figures.ipynb
```

The plotting materials use the archived manuscript summary data and reproduce the cumulative-runtime, batch-runtime, and reuse-hit-rate figures.

### 4. Run the AST-EP / HT-EP reconstruction checks

From the repository root:

```bash
cd baselines/ast_ep_ht_ep
python test_reconstruction.py
```

Expected result:

```text
Ran 6 tests
OK
```

These implementations are **independent paper-based reconstructions**, not the original historical source code. See `baselines/ast_ep_ht_ep/paper_reconstruction_notes.md` for the assumptions and implementation decisions used in the reconstructions.

---

## Repository Structure

```text
.
├── README.md
├── REVIEWER_QUICKSTART.txt
├── MANIFEST.md
├── VERIFICATION.md
├── CHECKSUMS.sha256
├── verify_package.py
│
├── core_rq3/
│   ├── src/ntable/
│   ├── tests/
│   ├── experiments/
│   ├── examples/
│   ├── benchmarks/
│   ├── README.md
│   └── pyproject.toml
│
├── data/
│   └── rq3/
│       └── generated_3000_structurally_similar_expressions.csv
│
├── results/
│   └── rq3/
│       ├── shared_topology_incremental_raw.csv
│       ├── shared_topology_incremental_summary.csv
│       ├── shared_topology_correctness.csv
│       ├── shared_topology_excluded.csv
│       ├── shared_topology_metadata.csv
│       └── shared_topology_manuscript_table.csv
│
├── figures/
│   └── rq3/
│       ├── RQ3_Structural_Reusability_Figures.ipynb
│       ├── plot_rq3_structural_reusability_jupyter.py
│       ├── requirements.txt
│       └── generated_figures/
│
├── baselines/
│   └── ast_ep_ht_ep/
│       ├── ast_ep_2023.py
│       ├── ht_ep_2025.py
│       ├── common.py
│       ├── test_reconstruction.py
│       ├── paper_reconstruction_notes.md
│       └── README.md
│
└── docs/
    └── legacy_pratt_reference/
```

---

## Manuscript-to-Artifact Mapping

| Manuscript item | Repository location |
|---|---|
| N-Table construction and AST realization | `core_rq3/src/ntable/builder.py` |
| Shared-topology reuse / Algorithm 4 implementation | `core_rq3/src/ntable/reuse.py` |
| Contract-aligned Pratt baseline | `core_rq3/src/ntable/pratt.py` |
| Tokenization and normalization support | `core_rq3/src/ntable/tokenizer.py` |
| AST representation | `core_rq3/src/ntable/ast.py` |
| Reconstruction-contract specification | `core_rq3/src/ntable/spec.py` |
| RQ3 generated workload | `data/rq3/generated_3000_structurally_similar_expressions.csv` |
| RQ3 experiment runner | `core_rq3/experiments/run_shared_topology_incremental_3000.py` |
| RQ3 raw timing measurements | `results/rq3/shared_topology_incremental_raw.csv` |
| RQ3 batch/cumulative summary | `results/rq3/shared_topology_incremental_summary.csv` |
| RQ3 correctness checks | `results/rq3/shared_topology_correctness.csv` |
| RQ3 excluded inputs | `results/rq3/shared_topology_excluded.csv` |
| RQ3 experiment metadata | `results/rq3/shared_topology_metadata.csv` |
| Manuscript-facing RQ3 table | `results/rq3/shared_topology_manuscript_table.csv` |
| RQ3 figure reproduction | `figures/rq3/` |
| AST-EP / HT-EP reconstructed baselines | `baselines/ast_ep_ht_ep/` |

---

## RQ3 Representation and Reuse Semantics

For a normalized token sequence `S0`, the implementation obtains:

- `S`: the parenthesis-free token sequence used by N-Table;
- `V`: the operand vector in left-to-right order;
- `sigma`: a collision-safe structural signature corresponding to the operator/grouping skeleton.

Conceptually, the reuse key is:

```text
K = <C, dinit, sigma>
```

and the repository stores:

```text
R[K] = <D, Pi>
```

where:

- `D` is the resolved dominance row;
- `Pi` is an immutable operand-independent operator topology.

A reuse hit returns the bound representation:

```text
Tb(e) = <Pi, V>
```

The topology is shared across structurally equivalent expressions, while `V` contains the operands of the current expression. If a downstream consumer requires a fully independent conventional AST, the bound representation can be explicitly materialized, which incurs an additional linear allocation/traversal cost.

---

## Archived Manuscript Results

The archived RQ3 result files reproduce the manuscript-reported endpoint values for the 3,000-input workload:

| Workflow | Cumulative median runtime |
|---|---:|
| Fresh N-Table | 156.369 ms |
| Shared-Reuse | 85.630 ms |
| Direct Pratt | 91.182 ms |

Corresponding manuscript observations include:

- **45.24% lower cumulative runtime** for Shared-Reuse relative to Fresh N-Table;
- **6.09% lower cumulative runtime** for Shared-Reuse relative to direct Pratt at the 3,000-input endpoint;
- approximately **600 inputs** for the beginning of the persistent per-batch advantage over direct Pratt;
- approximately **1,200 inputs** for the cumulative break-even point;
- 100% reuse-hit rate in all later batches from the 800-input point onward.

These values are the archived measurements reported with the manuscript.

---

## Runtime Reproducibility

Correctness counts, supported/excluded cases, structural signatures, repository behavior, and reuse-hit behavior should reproduce deterministically under the same code and input data.

Absolute wall-clock timing is environment-dependent. Re-running the experiments on a different machine, VM load, Python build, or operating-system scheduling state may produce different absolute runtimes and therefore slightly different percentage reductions. The archived CSV files under `results/rq3/` contain the measurements reported in the manuscript.

The manuscript runtime experiments were executed in the following environment:

- five virtual CPUs of an AMD EPYC 9V74 processor;
- 5.8 GB memory;
- 64-bit Linux under KVM;
- Python 3.13.5.

The core package declares Python 3.8+ compatibility. The reviewer verification reported for this artifact was performed with the packaged test suites; plotting additionally requires `pandas` and `matplotlib`.

---

## Verification

The consolidated artifact was checked before release.

Verified test suites:

```text
N-Table / Shared-Topology tests: 12/12 passed
AST-EP / HT-EP reconstruction tests: 6/6 passed
```

Package-integrity metadata is provided in:

```text
CHECKSUMS.sha256
```

A local verification helper is also provided:

```bash
python verify_package.py
```

See `VERIFICATION.md` for additional notes.

---

## Scope of This Artifact

This repository is the authoritative artifact for the manuscript's current **shared-topology RQ3 implementation**. An older D-only reuse experiment is deliberately excluded from the primary implementation and experiment paths because it no longer corresponds to the method evaluated in the manuscript.

The current repository provides complete runnable materials for the N-Table core, shared-topology RQ3 experiment, RQ3 figure reproduction, Pratt comparison used in RQ3, and the AST-EP / HT-EP reconstruction checks.

**Important:** before describing this repository as a complete full-paper replication package, the repository should also include any manuscript-specific RQ1/RQ2 benchmark tables/raw outputs and RQ4 real-software model inputs/results that are intended to be independently reproduced by reviewers. If those materials are maintained separately, the final repository should link them explicitly from this README.

---

## Release and Versioning

For peer review, use a versioned GitHub Release corresponding exactly to the submitted manuscript, for example:

```text
v1.0-jss-submission
```

The release should include a ZIP snapshot of the repository. Reviewers should use the versioned release rather than the moving `main` branch when reproducing the submitted results.

If the manuscript is under double-blind review, ensure that the public repository, Git history, commit metadata, file metadata, and release information comply with the journal's anonymity requirements before sharing the link with reviewers.

---

## Citation

If this artifact is reused after publication, please cite the accompanying paper.

For GitHub, it is recommended to add a `CITATION.cff` file so that the repository exposes a **Cite this repository** action. The paper DOI can be added after publication.

---

## License

A repository intended for public reuse should include an explicit software license, for example MIT, BSD-3-Clause, or Apache-2.0, subject to any third-party code or data restrictions.

If code and experimental data have different licensing conditions, document them separately and identify any third-party materials that are redistributed only for replication purposes.

---

## Contact / Issues During Review

For anonymous peer review, use the communication mechanism permitted by the submission system rather than adding author-identifying contact information here.

After publication, this section may be replaced with the permanent project URL, author contact information, paper DOI, and archival artifact DOI.
