from __future__ import annotations

import argparse
import csv
import gc
import platform
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from ntable import NTableBuilder, PrattParser, StructuralTemplateRepository

DEFAULT_ENDPOINTS = list(range(200, 3001, 200))


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Sequence[Dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(values: Sequence[float]) -> Dict[str, float]:
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Incremental 3000-expression comparison of N-Table Fresh, "
            "N-Table Shared-Topology Reuse, and direct Pratt."
        )
    )
    parser.add_argument("--input", type=Path, default=Path("generated_3000_structurally_similar_expressions.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("shared_topology_incremental_results"))
    parser.add_argument("--shuffle-seed", type=int, default=20260914)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--endpoints", default=",".join(map(str, DEFAULT_ENDPOINTS)))
    args, _unknown = parser.parse_known_args(argv)

    endpoints = [int(x.strip()) for x in args.endpoints.split(",") if x.strip()]
    rows = load_rows(args.input)
    if len(rows) != 3000:
        raise ValueError(f"Expected 3000 rows, found {len(rows)}")
    if not rows or "generated_expression" not in rows[0]:
        raise ValueError("Input CSV must contain generated_expression")

    ordered = list(rows)
    random.Random(args.shuffle_seed).shuffle(ordered)

    builder = NTableBuilder()
    pratt = PrattParser(builder.spec)

    # Validate support and correctness by source structural family.
    by_seed: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_seed[row.get("seed_no", "")].append(row)

    supported_seeds = set()
    unsupported_reason: Dict[str, str] = {}
    correctness_rows: List[Dict[str, str]] = []

    for seed_no in sorted(by_seed, key=lambda x: int(x) if x.isdigit() else x):
        family = by_seed[seed_no]
        try:
            expr1 = family[0]["generated_expression"]
            fresh_table1 = builder.build(expr1)
            fresh_ast1 = builder.build_ast(expr1).prefix()
            repo = StructuralTemplateRepository()
            reuse1 = builder.build_with_reuse(expr1, repo)
            pratt1 = pratt.parse(expr1).prefix()

            if reuse1.reused:
                raise ValueError("First expression unexpectedly reused")
            if reuse1.table.values != fresh_table1.values:
                raise ValueError("Cold reuse D differs from fresh D")
            if not (reuse1.ast.prefix() == fresh_ast1 == pratt1):
                raise ValueError("Cold AST mismatch")
            if reuse1.ast.is_materialized:
                raise ValueError("Shared reuse unexpectedly materialized AST")

            if len(family) > 1:
                expr2 = family[1]["generated_expression"]
                fresh_table2 = builder.build(expr2)
                fresh_ast2 = builder.build_ast(expr2).prefix()
                reuse2 = builder.build_with_reuse(expr2, repo)
                pratt2 = pratt.parse(expr2).prefix()
                if not reuse2.reused:
                    raise ValueError("Second same-family expression did not reuse")
                if reuse2.table.values != fresh_table2.values:
                    raise ValueError("Hot reuse D differs from fresh D")
                if not (reuse2.ast.prefix() == fresh_ast2 == pratt2):
                    raise ValueError("Hot AST mismatch")
                if reuse2.ast.is_materialized:
                    raise ValueError("Hot reuse unexpectedly materialized AST")
                if reuse1.ast.topology is not reuse2.ast.topology:
                    raise ValueError("Hot reuse did not share topology object")

            supported_seeds.add(seed_no)
            correctness_rows.append({
                "seed_no": seed_no,
                "supported": "1",
                "D_shared_reuse_equals_D_fresh": "1",
                "AST_shared_reuse_equals_AST_fresh": "1",
                "AST_pratt_equals_AST_fresh": "1",
                "hot_path_non_materialized": "1",
                "topology_shared_on_hot_hit": "1" if len(family) > 1 else "",
                "error": "",
            })
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            unsupported_reason[seed_no] = reason
            correctness_rows.append({
                "seed_no": seed_no,
                "supported": "0",
                "D_shared_reuse_equals_D_fresh": "",
                "AST_shared_reuse_equals_AST_fresh": "",
                "AST_pratt_equals_AST_fresh": "",
                "hot_path_non_materialized": "",
                "topology_shared_on_hot_hit": "",
                "error": reason,
            })

    by_position: Dict[int, Dict[str, str]] = {}
    excluded_rows: List[Dict[str, str]] = []
    for position, row in enumerate(ordered, start=1):
        seed_no = row.get("seed_no", "")
        if seed_no in supported_seeds:
            item = dict(row)
            item["order_index"] = str(position)
            item["signature"] = builder.structural_signature(row["generated_expression"])
            by_position[position] = item
        else:
            excluded_rows.append({
                "order_index": position,
                "generated_id": row.get("generated_id", ""),
                "seed_no": seed_no,
                "variant_index": row.get("variant_index", ""),
                "generated_expression": row["generated_expression"],
                "error_type": "UnsupportedStructuralFamily",
                "error_message": unsupported_reason.get(seed_no, "unsupported seed"),
            })

    # Build persistent-repository batch plan.
    batches: List[Dict[str, object]] = []
    prev = 0
    seen_signatures = set()
    cum_valid = 0
    cum_hits = 0
    cum_misses = 0

    for endpoint in endpoints:
        items = [by_position[i] for i in range(prev + 1, endpoint + 1) if i in by_position]
        batch_hits = 0
        batch_misses = 0
        for item in items:
            sig = item["signature"]
            if sig in seen_signatures:
                batch_hits += 1
            else:
                batch_misses += 1
                seen_signatures.add(sig)

        cum_valid += len(items)
        cum_hits += batch_hits
        cum_misses += batch_misses
        batches.append({
            "batch_index": len(batches) + 1,
            "input_start": prev + 1,
            "input_end": endpoint,
            "nominal_input_count": endpoint - prev,
            "items": items,
            "batch_comparable_count": len(items),
            "batch_excluded_count": (endpoint - prev) - len(items),
            "batch_new_structural_keys": batch_misses,
            "batch_reuse_hits": batch_hits,
            "batch_reuse_hit_rate_pct": 100.0 * batch_hits / len(items) if items else 0.0,
            "repository_size_after_batch": len(seen_signatures),
            "cumulative_input_count": endpoint,
            "cumulative_comparable_count": cum_valid,
            "cumulative_excluded_count": endpoint - cum_valid,
            "cumulative_reuse_hits": cum_hits,
            "cumulative_reuse_misses": cum_misses,
            "cumulative_reuse_hit_rate_pct": 100.0 * cum_hits / cum_valid if cum_valid else 0.0,
        })
        prev = endpoint

    def run_fresh(items: Sequence[Dict[str, str]]) -> None:
        build_ast = builder.build_ast
        sink = None
        for item in items:
            sink = build_ast(item["generated_expression"])
        if sink is None and items:
            raise AssertionError

    def run_pratt(items: Sequence[Dict[str, str]]) -> None:
        parse = pratt.parse
        sink = None
        for item in items:
            sink = parse(item["generated_expression"])
        if sink is None and items:
            raise AssertionError

    def run_shared(items: Sequence[Dict[str, str]], repo: StructuralTemplateRepository) -> None:
        build_reuse = builder.build_with_reuse
        sink = None
        for item in items:
            sink = build_reuse(item["generated_expression"], repo).ast
        if sink is None and items:
            raise AssertionError

    algorithms = ["NTable_Fresh", "NTable_SharedReuse", "Pratt"]

    # Warm-up full sequential runs. Reuse repo persists across all 15 batches.
    for warm in range(args.warmup):
        warm_repo = StructuralTemplateRepository()
        for batch_idx, batch in enumerate(batches):
            items = batch["items"]
            order = algorithms[(warm + batch_idx) % 3:] + algorithms[:(warm + batch_idx) % 3]
            for alg in order:
                if alg == "NTable_Fresh":
                    run_fresh(items)  # type: ignore[arg-type]
                elif alg == "NTable_SharedReuse":
                    run_shared(items, warm_repo)  # type: ignore[arg-type]
                else:
                    run_pratt(items)  # type: ignore[arg-type]

    raw_times: Dict[str, List[List[float]]] = {
        alg: [[0.0] * len(batches) for _ in range(args.repetitions)]
        for alg in algorithms
    }
    raw_rows: List[Dict[str, object]] = []

    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for rep in range(1, args.repetitions + 1):
            repo = StructuralTemplateRepository()
            for batch_idx, batch in enumerate(batches):
                items = batch["items"]
                rotation = (rep - 1 + batch_idx) % 3
                order = algorithms[rotation:] + algorithms[:rotation]
                before_hits = repo.hits
                before_misses = repo.misses
                before_size = len(repo)

                for alg in order:
                    t0 = time.perf_counter_ns()
                    if alg == "NTable_Fresh":
                        run_fresh(items)  # type: ignore[arg-type]
                    elif alg == "NTable_SharedReuse":
                        run_shared(items, repo)  # type: ignore[arg-type]
                    else:
                        run_pratt(items)  # type: ignore[arg-type]
                    elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
                    raw_times[alg][rep - 1][batch_idx] = elapsed_ms
                    raw_rows.append({
                        "repetition": rep,
                        "batch_index": batch["batch_index"],
                        "input_start": batch["input_start"],
                        "input_end": batch["input_end"],
                        "cumulative_input_count": batch["cumulative_input_count"],
                        "batch_comparable_count": batch["batch_comparable_count"],
                        "cumulative_comparable_count": batch["cumulative_comparable_count"],
                        "algorithm": alg,
                        "batch_runtime_ms": elapsed_ms,
                    })

                if repo.hits - before_hits != batch["batch_reuse_hits"]:
                    raise AssertionError("Reuse-hit count mismatch")
                if repo.misses - before_misses != batch["batch_new_structural_keys"]:
                    raise AssertionError("Reuse-miss count mismatch")
                if len(repo) - before_size != batch["batch_new_structural_keys"]:
                    raise AssertionError("Repository-growth mismatch")
    finally:
        if gc_was_enabled:
            gc.enable()

    summary_rows: List[Dict[str, object]] = []
    for batch_idx, batch in enumerate(batches):
        row: Dict[str, object] = {k: v for k, v in batch.items() if k != "items"}
        row["measured_repetitions"] = args.repetitions
        batch_stats: Dict[str, Dict[str, float]] = {}
        cum_stats: Dict[str, Dict[str, float]] = {}

        for alg in algorithms:
            batch_values = [raw_times[alg][r][batch_idx] for r in range(args.repetitions)]
            cum_values = [sum(raw_times[alg][r][:batch_idx + 1]) for r in range(args.repetitions)]
            batch_stats[alg] = summarize(batch_values)
            cum_stats[alg] = summarize(cum_values)

        prefixes = {
            "NTable_Fresh": "ntable_fresh",
            "NTable_SharedReuse": "ntable_shared_reuse",
            "Pratt": "pratt",
        }
        for alg, prefix in prefixes.items():
            for metric in ("median", "mean", "stdev", "min", "max"):
                row[f"{prefix}_batch_{metric}_ms"] = batch_stats[alg][metric]
                row[f"{prefix}_cumulative_{metric}_ms"] = cum_stats[alg][metric]
            bc = int(batch["batch_comparable_count"])
            cc = int(batch["cumulative_comparable_count"])
            row[f"{prefix}_batch_median_us_per_expression"] = 1000.0 * batch_stats[alg]["median"] / bc if bc else 0.0
            row[f"{prefix}_cumulative_median_us_per_expression"] = 1000.0 * cum_stats[alg]["median"] / cc if cc else 0.0

        bf = batch_stats["NTable_Fresh"]["median"]
        br = batch_stats["NTable_SharedReuse"]["median"]
        bp = batch_stats["Pratt"]["median"]
        cf = cum_stats["NTable_Fresh"]["median"]
        cr = cum_stats["NTable_SharedReuse"]["median"]
        cp = cum_stats["Pratt"]["median"]
        row.update({
            "shared_reuse_batch_reduction_vs_fresh_pct": (1.0 - br / bf) * 100.0,
            "fresh_over_shared_reuse_batch_speedup_x": bf / br,
            "shared_reuse_vs_pratt_batch_ratio_x": br / bp,
            "shared_reuse_batch_faster_than_pratt": "1" if br < bp else "0",
            "shared_reuse_batch_speedup_over_pratt_x": bp / br,
            "shared_reuse_batch_diff_vs_pratt_pct": (br / bp - 1.0) * 100.0,
            "shared_reuse_cumulative_reduction_vs_fresh_pct": (1.0 - cr / cf) * 100.0,
            "fresh_over_shared_reuse_cumulative_speedup_x": cf / cr,
            "shared_reuse_vs_pratt_cumulative_ratio_x": cr / cp,
            "shared_reuse_cumulative_faster_than_pratt": "1" if cr < cp else "0",
            "shared_reuse_cumulative_speedup_over_pratt_x": cp / cr,
            "shared_reuse_cumulative_diff_vs_pratt_pct": (cr / cp - 1.0) * 100.0,
        })
        summary_rows.append(row)
        print(
            f"N={int(batch['cumulative_input_count']):4d} "
            f"valid={int(batch['batch_comparable_count']):3d} "
            f"hit={float(batch['batch_reuse_hit_rate_pct']):5.1f}% "
            f"repo={int(batch['repository_size_after_batch']):3d} | "
            f"batch ms F={bf:7.3f} R={br:7.3f} P={bp:7.3f} | "
            f"cum R/P={cr:8.3f}/{cp:8.3f}",
            flush=True,
        )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "shared_topology_incremental_summary.csv", summary_rows, list(summary_rows[0].keys()))
    write_csv(out / "shared_topology_incremental_raw.csv", raw_rows, list(raw_rows[0].keys()))
    write_csv(out / "shared_topology_correctness.csv", correctness_rows, list(correctness_rows[0].keys()))
    write_csv(out / "shared_topology_excluded.csv", excluded_rows, [
        "order_index", "generated_id", "seed_no", "variant_index", "generated_expression", "error_type", "error_message"
    ])

    metadata_rows = [
        {"key": "input_rows", "value": len(rows)},
        {"key": "shuffle_seed", "value": args.shuffle_seed},
        {"key": "endpoints", "value": ";".join(map(str, endpoints))},
        {"key": "batch_size_nominal", "value": 200},
        {"key": "warmup_full_sequential_passes", "value": args.warmup},
        {"key": "measured_full_sequential_repetitions", "value": args.repetitions},
        {"key": "python_version", "value": sys.version.replace("\n", " ")},
        {"key": "platform", "value": platform.platform()},
        {"key": "repository_lifecycle", "value": "Persistent within each full repetition: R0 -> R200 -> ... -> R3000; reset only between independent repetitions"},
        {"key": "timing_scope", "value": "Expression string to usable AST representation; normalization/tokenization included. Fresh N-Table and Pratt return materialized AstNode trees. Shared reuse returns BoundAst(shared immutable topology, operands) and does not materialize on hot path."},
        {"key": "NTable_Fresh", "value": "build_ast(expression): fresh D + MRC + materialized AstNode tree"},
        {"key": "NTable_SharedReuse", "value": "build_with_reuse(expression, persistent_repo).ast: hash signature; hot hit reuses D and immutable topology; returns constant-size BoundAst"},
        {"key": "Pratt", "value": "PrattParser.parse(expression): direct materialized AstNode construction under same OperatorSpec and tokenizer contract"},
        {"key": "comparable_total_at_3000", "value": cum_valid},
        {"key": "excluded_total_at_3000", "value": len(excluded_rows)},
        {"key": "final_repository_unique_structures", "value": len(seen_signatures)},
        {"key": "correctness_checks", "value": "D reuse == fresh; BoundAst prefix == Fresh prefix == Pratt prefix; hot hits share topology object and remain non-materialized"},
    ]
    write_csv(out / "shared_topology_metadata.csv", metadata_rows, ["key", "value"])

    manuscript_fields = [
        "cumulative_input_count", "cumulative_comparable_count", "batch_comparable_count",
        "repository_size_after_batch", "batch_reuse_hit_rate_pct", "cumulative_reuse_hit_rate_pct",
        "ntable_fresh_batch_median_ms", "ntable_shared_reuse_batch_median_ms", "pratt_batch_median_ms",
        "ntable_fresh_batch_median_us_per_expression", "ntable_shared_reuse_batch_median_us_per_expression", "pratt_batch_median_us_per_expression",
        "shared_reuse_batch_reduction_vs_fresh_pct", "shared_reuse_batch_diff_vs_pratt_pct", "shared_reuse_batch_faster_than_pratt",
        "ntable_fresh_cumulative_median_ms", "ntable_shared_reuse_cumulative_median_ms", "pratt_cumulative_median_ms",
        "shared_reuse_cumulative_reduction_vs_fresh_pct", "shared_reuse_cumulative_diff_vs_pratt_pct", "shared_reuse_cumulative_faster_than_pratt",
    ]
    manuscript_rows = [{f: r[f] for f in manuscript_fields} for r in summary_rows]
    write_csv(out / "shared_topology_manuscript_table.csv", manuscript_rows, manuscript_fields)

    print(f"\nResults: {out.resolve()}")
    print(f"Supported seeds: {len(supported_seeds)}/{len(by_seed)}")
    print(f"Comparable at N=3000: {cum_valid}/3000")
    print(f"Final repo size: {len(seen_signatures)}")


if __name__ == "__main__":
    main()
