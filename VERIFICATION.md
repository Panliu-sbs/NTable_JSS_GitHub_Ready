# Verification performed before packaging

The consolidated reviewer package was checked in the current environment before archiving.

## Core N-Table / Shared-Reuse tests

Command:

```bash
cd core_rq3
python -m unittest discover -s tests -v
```

Result: **12/12 tests passed**.

## AST-EP / HT-EP reconstruction tests

Command:

```bash
cd baselines/ast_ep_ht_ep
python test_reconstruction.py
```

Result: **6/6 tests passed**.

## RQ3 figure reproduction

Command:

```bash
cd figures/rq3
python plot_rq3_structural_reusability_jupyter.py
```

The archived summary CSV reproduced the manuscript headline values:

- N-Table Fresh cumulative median: 156.369 ms
- N-Table Shared-Reuse cumulative median: 85.630 ms
- Pratt cumulative median: 91.182 ms
- Shared-Reuse reduction vs Fresh: 45.24%
- Shared-Reuse improvement vs Pratt: 6.09%
- approximate cumulative break-even: 1,200 inputs

Non-interactive matplotlib backends may print harmless `FigureCanvasAgg` warnings when the
script calls `plt.show()`; the figure files are still written successfully.
