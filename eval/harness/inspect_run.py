"""Print the theme names a run produced, and where their items really came from.

The scores say whether a candidate grouped well. They cannot say whether it
grouped the *right things* or named them like something an owner would say, and
both of those are a large part of what the paid layer sells.

This answers the one question the headline number hides: when a model produces
more themes than the reference has, is it splitting one real theme in half, or
has it found a distinction the reference missed? The first is the model's error
and deflates reach. The second means the reference grouping is the thing that
needs fixing, which matters more, because the views were designed around it.

  python3 eval/harness/inspect_run.py                  # the newest result
  python3 eval/harness/inspect_run.py <file.json>       # a specific one
  python3 eval/harness/inspect_run.py <file.json> --run 2
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent


def newest_result() -> pathlib.Path:
    files = sorted((ROOT / "results").glob("*.json"))
    if not files:
        raise SystemExit("no result files in eval/results — run the harness first")
    return files[-1]


def parse_themes(raw: str) -> list[dict]:
    """Pull the themes out of one raw model response.

    Models wrap JSON in prose or code fences often enough that insisting on
    clean output would make this tool fail on runs that scored fine.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.split("\n", 1)[1] if text.lstrip().startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise SystemExit("could not find JSON in the raw response")
    return json.loads(text[start:end + 1]).get("themes", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="a file in eval/results (default: newest)")
    ap.add_argument("--run", type=int, default=1, help="which repeat to read, from 1")
    args = ap.parse_args()

    path = pathlib.Path(args.path) if args.path else newest_result()
    data = json.loads(path.read_text())
    raws = data.get("raw_responses") or []
    if not 1 <= args.run <= len(raws):
        raise SystemExit(f"--run must be between 1 and {len(raws)}")

    items = json.loads((ROOT / "dataset" / "items.json").read_text())
    gold = {it["id"]: it["gold_theme"] for it in items}
    gold_sizes = collections.Counter(gold.values())

    themes = parse_themes(raws[args.run - 1])
    print(f"{path.name} — run {args.run} of {len(raws)}")
    print(f"{data.get('provider')} {data.get('model')} · "
          f"{len(themes)} themes produced, {len(gold_sizes)} in the reference\n")

    # Which predicted themes drew from each reference theme: a reference theme
    # claimed by several predictions is one that got split, and splitting is
    # what deflates a theme's reach.
    claimed: dict[str, list[str]] = collections.defaultdict(list)

    for theme in themes:
        ids = [i for i in theme.get("item_ids", []) if i in gold]
        sources = collections.Counter(gold[i] for i in ids)
        print(f"  {theme.get('name', '(unnamed)')}  [{len(ids)} items]")
        for source, count in sources.most_common():
            share = count / gold_sizes[source]
            note = "  <- all of it" if share == 1.0 else f"  <- {share:.0%} of it"
            print(f"      {count:>3} from \"{source}\"{note}")
            claimed[source].append(theme.get("name", "(unnamed)"))
        print()

    split = {g: names for g, names in claimed.items() if len(names) > 1}
    if split:
        print("Reference themes split across several predicted themes:")
        for source, names in sorted(split.items(), key=lambda kv: -len(kv[1])):
            print(f'  "{source}" -> {", ".join(names)}')
        print("\nEach of these reports its reach as several small numbers instead")
        print("of one real one. Read them and decide which split is wrong: the")
        print("model's, or the reference grouping's.")
    else:
        print("No reference theme was split. Any extra themes are the model")
        print("finding distinctions the reference does not make.")

    missing = [i for i in gold if not any(
        i in t.get("item_ids", []) for t in themes)]
    if missing:
        print(f"\n{len(missing)} items were not placed in any theme: "
              f"{', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
