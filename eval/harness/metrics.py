"""Scoring for a candidate grouping against the reference grouping.

No dependencies, so this runs anywhere. Every metric below is implemented from
its definition and checked against known values in self_test().

Why these metrics: the product has two distinct failure modes, and a single
accuracy number hides both of them.

  Homogeneity answers "did it put unrelated things in the same theme?"
  A low score means a theme is a dumping ground, which is the failure that
  makes an owner distrust the whole view.

  Completeness answers "did it split one real theme across several?"
  A low score means the same complaint appears three times at 20% each
  instead of once at 60%, which breaks the reach metric.

Both matter and they trade off, so V-measure (their harmonic mean) is the
headline, with the two components always reported beside it.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict


def _contingency(pred: dict[str, str], gold: dict[str, str]):
    """pred/gold map item id -> cluster label. Returns table, row sums, col sums, n."""
    ids = [i for i in gold if i in pred]
    table: dict[tuple[str, str], int] = Counter()
    for i in ids:
        table[(pred[i], gold[i])] += 1
    rows: dict[str, int] = Counter()
    cols: dict[str, int] = Counter()
    for (p, g), c in table.items():
        rows[p] += c
        cols[g] += c
    return table, rows, cols, len(ids)


def _comb2(x: int) -> float:
    return x * (x - 1) / 2.0


def adjusted_rand_index(pred: dict[str, str], gold: dict[str, str]) -> float:
    """1.0 = identical grouping, ~0.0 = no better than chance, can go negative."""
    table, rows, cols, n = _contingency(pred, gold)
    if n < 2:
        return 1.0
    index = sum(_comb2(c) for c in table.values())
    exp_rows = sum(_comb2(c) for c in rows.values())
    exp_cols = sum(_comb2(c) for c in cols.values())
    expected = exp_rows * exp_cols / _comb2(n)
    maximum = 0.5 * (exp_rows + exp_cols)
    if maximum == expected:
        return 1.0
    return (index - expected) / (maximum - expected)


def _entropy(counts, n: int) -> float:
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / n
            h -= p * math.log(p)
    return h


def homogeneity_completeness_v(pred: dict[str, str], gold: dict[str, str]):
    """Returns (homogeneity, completeness, v_measure), each 0..1."""
    table, rows, cols, n = _contingency(pred, gold)
    if n == 0:
        return 1.0, 1.0, 1.0

    h_gold = _entropy(cols.values(), n)
    h_pred = _entropy(rows.values(), n)

    # H(gold | pred)
    h_gold_given_pred = 0.0
    for (p, g), c in table.items():
        h_gold_given_pred -= (c / n) * math.log(c / rows[p])

    # H(pred | gold)
    h_pred_given_gold = 0.0
    for (p, g), c in table.items():
        h_pred_given_gold -= (c / n) * math.log(c / cols[g])

    homogeneity = 1.0 if h_gold == 0 else 1.0 - h_gold_given_pred / h_gold
    completeness = 1.0 if h_pred == 0 else 1.0 - h_pred_given_gold / h_pred

    if homogeneity + completeness == 0:
        v = 0.0
    else:
        v = 2 * homogeneity * completeness / (homogeneity + completeness)
    return homogeneity, completeness, v


def type_accuracy(pred_types: dict[str, str], gold_types: dict[str, str]):
    """Overall accuracy plus per-class, because praise is rare and easy to miss."""
    ids = [i for i in gold_types if i in pred_types]
    if not ids:
        return 0.0, {}
    correct = sum(1 for i in ids if pred_types[i] == gold_types[i])
    per_class: dict[str, dict] = defaultdict(lambda: {"n": 0, "right": 0})
    for i in ids:
        bucket = per_class[gold_types[i]]
        bucket["n"] += 1
        if pred_types[i] == gold_types[i]:
            bucket["right"] += 1
    for v in per_class.values():
        v["accuracy"] = round(v["right"] / v["n"], 3)
    return correct / len(ids), dict(per_class)


def coverage(pred: dict[str, str], gold: dict[str, str]) -> float:
    """Fraction of items the model actually placed. A model that silently drops
    items can score well on everything else while losing feedback."""
    if not gold:
        return 1.0
    return sum(1 for i in gold if i in pred) / len(gold)


def score(pred_themes, gold_themes, pred_types=None, gold_types=None) -> dict:
    h, c, v = homogeneity_completeness_v(pred_themes, gold_themes)
    out = {
        "v_measure": round(v, 4),
        "homogeneity": round(h, 4),
        "completeness": round(c, 4),
        "adjusted_rand": round(adjusted_rand_index(pred_themes, gold_themes), 4),
        "coverage": round(coverage(pred_themes, gold_themes), 4),
        "themes_predicted": len(set(pred_themes.values())),
        "themes_reference": len(set(gold_themes.values())),
    }
    if pred_types and gold_types:
        acc, per_class = type_accuracy(pred_types, gold_types)
        out["type_accuracy"] = round(acc, 4)
        out["type_per_class"] = per_class
    return out


def self_test():
    """Checked against values that are known by construction."""
    gold = {"a": "X", "b": "X", "c": "Y", "d": "Y"}

    # identical grouping, different labels
    perfect = {"a": "1", "b": "1", "c": "2", "d": "2"}
    s = score(perfect, gold)
    assert s["v_measure"] == 1.0, s
    assert s["adjusted_rand"] == 1.0, s

    # everything in one bucket: completeness perfect, homogeneity zero
    lumped = {k: "all" for k in gold}
    h, c, v = homogeneity_completeness_v(lumped, gold)
    assert abs(h - 0.0) < 1e-9, h
    assert abs(c - 1.0) < 1e-9, c

    # every item its own theme: homogeneity perfect, completeness penalised.
    # Four singleton clusters over two true classes gives exactly 0.5 — knowing
    # the class halves the uncertainty about which cluster an item is in.
    split = {k: k for k in gold}
    h, c, v = homogeneity_completeness_v(split, gold)
    assert abs(h - 1.0) < 1e-9, h
    assert abs(c - 0.5) < 1e-9, c

    # A grouping that cuts straight across the true classes is worse than chance.
    # Two clusters each holding one item from each class gives ARI = -0.5.
    mixed = {"a": "1", "b": "2", "c": "1", "d": "2"}
    assert abs(adjusted_rand_index(mixed, gold) + 0.5) < 1e-9, adjusted_rand_index(mixed, gold)

    # coverage notices dropped items
    partial = {"a": "1", "b": "1", "c": "2"}
    assert abs(coverage(partial, gold) - 0.75) < 1e-9

    # type accuracy, including per class
    acc, per_class = type_accuracy(
        {"a": "bug", "b": "bug", "c": "praise", "d": "bug"},
        {"a": "bug", "b": "question", "c": "praise", "d": "bug"},
    )
    assert abs(acc - 0.75) < 1e-9, acc
    assert per_class["bug"]["accuracy"] == 1.0
    assert per_class["question"]["accuracy"] == 0.0

    print("metrics self-test passed")


if __name__ == "__main__":
    self_test()
