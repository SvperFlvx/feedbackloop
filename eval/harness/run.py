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
import os
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


KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY")


def load_env_file():
    """Read keys from a .env file so they never have to be typed into a shell.

    Pasting a key at a prompt is a reliable way to leak it: it lands in shell
    history, in scrollback, and in anything you paste the terminal into. A file
    you edit once and never open again is both safer and less annoying.

    The file WINS over whatever is already in the environment. That is the
    opposite of the usual convention, and deliberate: a key exported into a
    shell session hours ago is invisible, outlives the reason it was set, and
    survives being revoked. The file is the thing you just edited on purpose,
    so it is the thing that should take effect. Nothing here runs in CI.

    Looked for next to the harness, beside it, and in the current directory.
    """
    for candidate in (ROOT / ".env", ROOT.parent / ".env", pathlib.Path(".env")):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value:
                os.environ[key] = value
                os.environ["_SRC_" + key] = str(candidate)
        return candidate
    return None


def report_key_source():
    """Say where each key came from, and show enough of it to tell two apart.

    A silent key is the thing that wasted an afternoon: a revoked key in the
    shell and a good key in the file look identical from the outside, and the
    only symptom is a 401 that says nothing about which one was sent. Four
    characters is enough to tell them apart and not enough to use.
    """
    for var in KEY_VARS:
        value = os.environ.get(var)
        if not value:
            continue
        source = os.environ.get("_SRC_" + var, "the shell environment")
        print(f"{var}: ...{value[-4:]}  (from {source})")


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


class ParseFailure(Exception):
    """A reply that arrived but could not be read, carrying the reply itself.

    Throwing away the text and printing "no JSON object in response" leaves
    nobody able to tell a truncated reply from a refusal from a model that
    wrapped its answer in an apology. The reply is the evidence; keep it.
    """

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def attempt_run(provider: str, model: str, items, number: int,
                tries: int = 2) -> tuple[dict[str, str], str, float]:
    """Run once, and once more if the provider failed rather than answered.

    A provider error is about the call, not about the grouping, so retrying is
    free of any effect on the score. A ParseFailure is not retried: the model
    answered, and the answer is the finding.
    """
    for attempt in range(1, tries + 1):
        try:
            return run_once(provider, model, items)
        except providers.ProviderError as e:
            if attempt == tries:
                raise
            print(f"  run {number} attempt {attempt}: {e}", file=sys.stderr)
            print(f"  retrying run {number}", file=sys.stderr)
    raise AssertionError("unreachable")


def run_once(provider: str, model: str, items) -> tuple[dict[str, str], str, float]:
    payload = strip_gold(items)
    started = time.time()
    raw = providers.call(provider, model, prompt.SYSTEM, prompt.user_message(payload))
    elapsed = time.time() - started
    try:
        return parse_themes(raw), raw, elapsed
    except (ValueError, json.JSONDecodeError) as e:
        raise ParseFailure(str(e), raw) from None


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

    load_env_file()
    if args.provider != "mock":
        report_key_source()

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
    out_dir = ROOT / "results"
    stamp = time.strftime("%Y%m%d-%H%M%S")

    for n in range(args.repeat):
        try:
            pred, raw, elapsed = attempt_run(args.provider, args.model, items, n + 1)
        except ParseFailure as e:
            out_dir.mkdir(exist_ok=True)
            dump = out_dir / f"unparsed-{stamp}-run{n + 1}.txt"
            dump.write_text(e.raw)
            print(f"run {n + 1} returned a reply that could not be read: {e}",
                  file=sys.stderr)
            print(f"  {len(e.raw)} characters saved to {dump}", file=sys.stderr)
            print(f"  first 300: {e.raw[:300]!r}", file=sys.stderr)
            return 1
        except providers.ProviderError as e:
            print(f"run {n + 1} failed: {e}", file=sys.stderr)
            if not runs:
                return 1
            # Runs already in hand cost real minutes. A later blip should not
            # discard them; it should narrow what the summary claims.
            print(f"  keeping the {len(runs)} run(s) that succeeded. "
                  f"Spread over fewer runs says less about stability.",
                  file=sys.stderr)
            break
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

    out_dir.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", f"{args.provider}-{args.model}").strip("-")
    out = out_dir / f"{safe}-{stamp}.json"
    out.write_text(json.dumps({
        "provider": args.provider, "model": args.model,
        "repeats_asked": args.repeat, "repeats_completed": len(runs),
        "runs": runs, "summary": summary, "raw_responses": raws,
    }, indent=2) + "\n")

    print(f'\nmean V-measure {summary["v_measure"]["mean"]:.3f}', end="")
    if len(runs) > 1:
        print(f' (spread {summary["v_measure"]["stdev"]:.3f} across {len(runs)} runs)')
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
