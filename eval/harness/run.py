"""Run a provider against the fixed set and score what comes back.

  python3 eval/harness/run.py --provider mock --model none
  python3 eval/harness/run.py --provider openai --model gpt-5.6-luna --repeat 3
  python3 eval/harness/run.py --compare results/*.json

Scores are written to eval/results/ so runs can be compared later. Raw model
output is saved alongside them, because the numbers tell you which candidate
grouped better and only the output tells you whether the theme names are any
good — that part still needs your eyes.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import metrics          # noqa: E402
import prompt           # noqa: E402
import providers        # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent
PUBLIC_FIELDS = ("id", "text", "screen", "build", "author")


def load_env_file():
    """Read keys from a .env file so they never have to be typed into a shell.

    Pasting a key at a prompt is a reliable way to leak it: it lands in shell
    history, in scrollback, and in anything you paste the terminal into. A file
    you edit once and never open again is both safer and less annoying.

    Looked for next to the harness, beside it, and in the current directory.
    Existing environment variables always win, so CI is unaffected.
    """
    seen = []
    for candidate in (ROOT / ".env", ROOT.parent / ".env", pathlib.Path(".env")):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value
                seen.append(key)
        return candidate, seen
    return None, seen


def load_items():
    return json.loads((ROOT / "dataset" / "items.json").read_text())


def strip_gold(items):
    """Nothing with 'gold' in the name ever reaches a model."""
    return [{k: it[k] for k in PUBLIC_FIELDS} for it in items]


def parse_themes(raw: str) -> dict[str, str]:
    """Returns item id -> theme name. Tolerates a model wrapping JSON in prose
    or a code fence, because that is a formatting slip rather than a grouping
    failure and should not be scored as one."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        brace = text.find("{")
        if brace == -1:
            raise ValueError("no JSON object in response")
        text = text[brace:text.rfind("}") + 1]

    data = json.loads(text)
    out: dict[str, str] = {}
    for theme in data.get("themes", []):
        name = theme.get("name", "unnamed")
        for item_id in theme.get("item_ids", []):
            out[item_id] = name
    if not out:
        raise ValueError("response contained no item assignments")
    return out


def run_once(provider: str, model: str, items) -> tuple[dict[str, str], str, float]:
    payload = strip_gold(items)
    started = time.time()
    raw = providers.call(provider, model, prompt.SYSTEM, prompt.user_message(payload))
    elapsed = time.time() - started
    return parse_themes(raw), raw, elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock")
    ap.add_argument("--model", default="none")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run N times and report spread. Stability matters as "
                         "much as accuracy: themes that reshuffle between runs "
                         "break persistence and the colour-per-theme rule.")
    ap.add_argument("--compare", nargs="*", help="score files to tabulate instead of running")
    args = ap.parse_args()

    env_file, loaded = load_env_file()
    if env_file and loaded:
        print(f"read {', '.join(loaded)} from {env_file}")

    if args.compare:
        rows = []
        for path in args.compare:
            d = json.loads(pathlib.Path(path).read_text())
            rows.append((f'{d["provider"]}/{d["model"]}', d["summary"]))
        print(f'{"candidate":34} {"V":>7} {"homog":>7} {"compl":>7} {"ARI":>7} {"cover":>7} {"themes":>7}')
        print("-" * 82)
        for label, s in sorted(rows, key=lambda r: -r[1]["v_measure"]["mean"]):
            print(f'{label:34} {s["v_measure"]["mean"]:7.3f} {s["homogeneity"]["mean"]:7.3f} '
                  f'{s["completeness"]["mean"]:7.3f} {s["adjusted_rand"]["mean"]:7.3f} '
                  f'{s["coverage"]["mean"]:7.3f} {s["themes_predicted"]["mean"]:7.1f}')
        return 0

    items = load_items()
    gold = {it["id"]: it["gold_theme"] for it in items}
    runs, raws = [], []

    for n in range(args.repeat):
        try:
            pred, raw, elapsed = run_once(args.provider, args.model, items)
        except (providers.ProviderError, ValueError, json.JSONDecodeError) as e:
            print(f"run {n + 1} failed: {e}", file=sys.stderr)
            return 1
        s = metrics.score(pred, gold)
        s["seconds"] = round(elapsed, 1)
        runs.append(s)
        raws.append(raw)
        print(f'run {n + 1}: V={s["v_measure"]:.3f}  homogeneity={s["homogeneity"]:.3f}  '
              f'completeness={s["completeness"]:.3f}  coverage={s["coverage"]:.3f}  '
              f'themes={s["themes_predicted"]}  {s["seconds"]}s')

    summary = {}
    for key in ("v_measure", "homogeneity", "completeness", "adjusted_rand",
                "coverage", "themes_predicted", "seconds"):
        vals = [r[key] for r in runs]
        summary[key] = {
            "mean": round(statistics.fmean(vals), 4),
            "stdev": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
        }

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", f"{args.provider}-{args.model}").strip("-")
    out = out_dir / f"{safe}-{stamp}.json"
    out.write_text(json.dumps({
        "provider": args.provider, "model": args.model, "repeats": args.repeat,
        "runs": runs, "summary": summary, "raw_responses": raws,
    }, indent=2) + "\n")

    print(f'\nmean V-measure {summary["v_measure"]["mean"]:.3f}', end="")
    if args.repeat > 1:
        print(f' (spread {summary["v_measure"]["stdev"]:.3f} across {args.repeat} runs)')
        if summary["v_measure"]["stdev"] > 0.05:
            print("  warning: unstable. Themes would visibly reshuffle between builds.")
    else:
        print("  — use --repeat 3 to see whether it is stable")
    print(f"saved to {out}")
    print("\nRead the theme names in that file. The score cannot tell you "
          "whether they are worded like something an owner would say.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
