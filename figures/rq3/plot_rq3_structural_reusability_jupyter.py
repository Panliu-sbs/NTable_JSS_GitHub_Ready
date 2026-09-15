# ============================================================
# RQ3: Structural Reusability — Jupyter plotting code
# Compatible with Jupyter Notebook / JupyterLab / Spyder / IPython
#
# Input:
#   shared_topology_incremental_summary.csv
#
# Outputs:
#   Figure_RQ3_Cumulative_Runtime.png/.pdf
#   Figure_RQ3_Batch_Runtime.png/.pdf
#   Figure_RQ3_Reuse_Hit_Rate.png/.pdf
# ============================================================

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


# ------------------------------------------------------------
# 1. Locate the CSV file
# ------------------------------------------------------------

# If needed, replace this with an absolute Windows path, for example:
# CSV_PATH = Path(r"C:\Users\Go\Desktop\shared_topology_incremental_summary.csv")
CSV_PATH = Path("shared_topology_incremental_summary.csv")

# Convenient fallback when the CSV is in a subfolder.
if not CSV_PATH.exists():
    fallback = Path("shared_topology_incremental_results") / "shared_topology_incremental_summary.csv"
    if fallback.exists():
        CSV_PATH = fallback

if not CSV_PATH.exists():
    raise FileNotFoundError(
        "Cannot find shared_topology_incremental_summary.csv.\n"
        "Please place the CSV in the same folder as this notebook, or edit CSV_PATH."
    )

print("Using CSV:", CSV_PATH.resolve())


# ------------------------------------------------------------
# 2. Load and validate the experimental data
# ------------------------------------------------------------

df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

required_columns = [
    "cumulative_input_count",
    "batch_reuse_hit_rate_pct",
    "ntable_fresh_batch_median_ms",
    "ntable_fresh_cumulative_median_ms",
    "ntable_shared_reuse_batch_median_ms",
    "ntable_shared_reuse_cumulative_median_ms",
    "pratt_batch_median_ms",
    "pratt_cumulative_median_ms",
]

missing = [c for c in required_columns if c not in df.columns]
if missing:
    raise ValueError("Missing required columns: " + ", ".join(missing))

df = df.sort_values("cumulative_input_count").reset_index(drop=True)

x = df["cumulative_input_count"]

print("\nLoaded rows:", len(df))
print("Workload sizes:", x.tolist())


# ------------------------------------------------------------
# 3. Output directory
# ------------------------------------------------------------

OUTPUT_DIR = Path("rq3_figures")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 600


# ------------------------------------------------------------
# 4. Figure 1 — Cumulative runtime
#
# This is the recommended MAIN figure for RQ3.
# It shows the cold phase, break-even, and the final advantage of
# N-Table Shared-Reuse over direct Pratt.
# ------------------------------------------------------------

fig, ax = plt.subplots(figsize=(8.6, 5.2))

ax.plot(
    x,
    df["ntable_fresh_cumulative_median_ms"],
    marker="o",
    label="N-Table Fresh",
)
ax.plot(
    x,
    df["ntable_shared_reuse_cumulative_median_ms"],
    marker="o",
    label="N-Table Shared-Reuse",
)
ax.plot(
    x,
    df["pratt_cumulative_median_ms"],
    marker="o",
    label="Pratt",
)

ax.set_xlabel("Number of processed input expressions")
ax.set_ylabel("Cumulative median runtime (ms)")
ax.set_xticks(x.tolist())
ax.tick_params(axis="x", rotation=45)
ax.set_ylim(bottom=0)
ax.grid(True, alpha=0.25)
ax.legend()

# Mark the first cumulative point at which Shared-Reuse is faster than Pratt.
faster_mask = (
    df["ntable_shared_reuse_cumulative_median_ms"]
    <
    df["pratt_cumulative_median_ms"]
)

if faster_mask.any():
    first_idx = faster_mask.idxmax()
    break_even_x = int(df.loc[first_idx, "cumulative_input_count"])
    break_even_y = float(df.loc[first_idx, "ntable_shared_reuse_cumulative_median_ms"])

    ax.axvline(break_even_x, alpha=0.45)
    ax.annotate(
        f"Break-even ≈ {break_even_x}",
        xy=(break_even_x, break_even_y),
        xytext=(break_even_x + 180, break_even_y + 12),
        arrowprops={"arrowstyle": "->"},
    )

fig.tight_layout()

fig.savefig(
    OUTPUT_DIR / "Figure_RQ3_Cumulative_Runtime.png",
    dpi=DPI,
    bbox_inches="tight",
)
fig.savefig(
    OUTPUT_DIR / "Figure_RQ3_Cumulative_Runtime.pdf",
    bbox_inches="tight",
)

plt.show()


# ------------------------------------------------------------
# 5. Figure 2 — Runtime of each incremental 200-expression batch
#
# This figure shows the warm-repository behavior more directly.
# ------------------------------------------------------------

fig, ax = plt.subplots(figsize=(8.6, 5.2))

ax.plot(
    x,
    df["ntable_fresh_batch_median_ms"],
    marker="o",
    label="N-Table Fresh",
)
ax.plot(
    x,
    df["ntable_shared_reuse_batch_median_ms"],
    marker="o",
    label="N-Table Shared-Reuse",
)
ax.plot(
    x,
    df["pratt_batch_median_ms"],
    marker="o",
    label="Pratt",
)

ax.set_xlabel("Number of processed input expressions")
ax.set_ylabel("Median runtime per incremental batch (ms)")
ax.set_xticks(x.tolist())
ax.tick_params(axis="x", rotation=45)
ax.set_ylim(bottom=0)
ax.grid(True, alpha=0.25)
ax.legend()

fig.tight_layout()

fig.savefig(
    OUTPUT_DIR / "Figure_RQ3_Batch_Runtime.png",
    dpi=DPI,
    bbox_inches="tight",
)
fig.savefig(
    OUTPUT_DIR / "Figure_RQ3_Batch_Runtime.pdf",
    bbox_inches="tight",
)

plt.show()


# ------------------------------------------------------------
# 6. Figure 3 — Repository learning / reuse-hit rate
#
# This explains WHY the Shared-Reuse runtime improves:
# the repository rapidly learns the repeated structural patterns.
# ------------------------------------------------------------

fig, ax = plt.subplots(figsize=(8.6, 4.8))

ax.plot(
    x,
    df["batch_reuse_hit_rate_pct"],
    marker="o",
    label="Reuse hit rate",
)

ax.set_xlabel("Number of processed input expressions")
ax.set_ylabel("Reuse hit rate (%)")
ax.set_xticks(x.tolist())
ax.tick_params(axis="x", rotation=45)
ax.set_ylim(0, 105)
ax.grid(True, alpha=0.25)
ax.legend()

fig.tight_layout()

fig.savefig(
    OUTPUT_DIR / "Figure_RQ3_Reuse_Hit_Rate.png",
    dpi=DPI,
    bbox_inches="tight",
)
fig.savefig(
    OUTPUT_DIR / "Figure_RQ3_Reuse_Hit_Rate.pdf",
    bbox_inches="tight",
)

plt.show()


# ------------------------------------------------------------
# 7. Print the headline RQ3 results
# ------------------------------------------------------------

last = df.iloc[-1]

fresh_3000 = float(last["ntable_fresh_cumulative_median_ms"])
reuse_3000 = float(last["ntable_shared_reuse_cumulative_median_ms"])
pratt_3000 = float(last["pratt_cumulative_median_ms"])

reduction_vs_fresh = 100.0 * (1.0 - reuse_3000 / fresh_3000)
improvement_vs_pratt = 100.0 * (1.0 - reuse_3000 / pratt_3000)

print("\n=== RQ3 headline results ===")
print(f"N-Table Fresh cumulative median:        {fresh_3000:.3f} ms")
print(f"N-Table Shared-Reuse cumulative median: {reuse_3000:.3f} ms")
print(f"Pratt cumulative median:                {pratt_3000:.3f} ms")
print(f"Reuse reduction vs Fresh:               {reduction_vs_fresh:.2f}%")
print(f"Reuse improvement vs Pratt:             {improvement_vs_pratt:.2f}%")

if faster_mask.any():
    print(f"Cumulative break-even point:            about {break_even_x} inputs")

print("\nFigures saved in:", OUTPUT_DIR.resolve())
