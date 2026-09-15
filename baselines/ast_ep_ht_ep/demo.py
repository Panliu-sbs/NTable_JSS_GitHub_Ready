# -*- coding: utf-8 -*-
from ast_ep_2023 import ASTEP2023
from ht_ep_2025 import HTEP2025, format_hierarchy


def show(title, result):
    print("=" * 78)
    print(title)
    print("operations:", result.operation_count)
    print("sequences:", len(result.sequences))
    print(result.sequences)


def main():
    # JSS 2023, Section 6 / Table 2: expected 30 sequences.
    ex2023 = "(a|b)c(d|e*)(f||gh)"
    r2023 = ASTEP2023().run(ex2023)
    show("AST-EP 2023: " + ex2023, r2023)
    print("postorder:", r2023.postorder)
    print("AST nodes=%d height=%d" % (r2023.ast_nodes, r2023.ast_height))

    # JSS 2025, Section 4 example: expected 10 sequences and Table-2 depths.
    ex2025 = "(a|(b||k)2)c(d|e)"
    r2025 = HTEP2025().run(ex2025)
    show("HT-EP 2025: " + ex2025, r2025)
    print("final layer depths:", r2025.layer_table.final_depths)
    print("hierarchy tree:\n" + format_hierarchy(r2025.tree))
    print("tree nodes=%d height=%d" % (r2025.tree_nodes, r2025.tree_height))

    # JSS 2025, Fig. 5(e): expected 15 sequences.
    ex_closure = "c(a|b)*"
    r_closure = HTEP2025().run(ex_closure)
    show("HT-EP 2025 closure: " + ex_closure, r_closure)


if __name__ == "__main__":
    main()
