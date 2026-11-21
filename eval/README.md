# Grouping evaluation harness

Scores how well a model groups feedback into themes, against a fixed set with a
known-correct grouping. Point it at a provider, get a number, compare.

Plain `python3`, no dependencies, no install.

## Run it

```bash
# offline baseline — no API key needed
python3 eval/harness/run.py --provider mock --model screens-baseline

# a real candidate
export OPENAI_API_KEY=...
python3 eval/harness/run.py --provider openai --model <model> --repeat 3

# compare everything you have run
python3 eval/harness/run.py --compare eval/results/*.json
```

Providers: `mock`, `openai`, `anthropic`, `google`, `groq`. Anything speaking the
OpenAI chat-completions shape works through the `openai` adapter by changing
`base_url` in `providers.py` — one line, no new code.

## The number to beat: 0.573

The `mock` provider doesn't call anything. It groups items by which screen they
came from, which is a strategy you could implement in an afternoon with a
`GROUP BY`. It scores **V-measure 0.573**.

That is the floor. A model that doesn't clearly beat 0.573 is not worth paying
for, because grouping by screen is free. Treat it as the first question you ask
of any candidate rather than a curiosity.

## What the scores mean

| Metric | Question it answers | What a low score looks like to an owner |
| --- | --- | --- |
| **Homogeneity** | Did it put unrelated things in one theme? | A theme that is a dumping ground. Owner stops trusting the view |
| **Completeness** | Did it split one real theme across several? | The same complaint appears three times at 20% instead of once at 60% |
| **V-measure** | Both at once (harmonic mean) | The headline. Always read it beside the two components |
| **Adjusted Rand** | Agreement with the reference, corrected for chance | 0 means no better than random; it can go negative |
| **Coverage** | Did every item get placed? | Below 1.0 means feedback was silently dropped — the worst failure here |
| **themes** | How many it produced | Reference is 7. Fifteen means it is categorising, not grouping |

Homogeneity and completeness trade off against each other. One theme containing
everything scores perfect completeness and zero homogeneity; one theme per item
does the reverse. V-measure is what stops either from looking good.

## Stability matters as much as accuracy

`--repeat 3` runs the same input several times and reports the spread.

This is not a nicety for this product. Two settled decisions depend on themes
being stable between runs: a theme keeps its colour across builds, and the
hollow-dot encoding says a theme has gone quiet. If a model reshuffles its
themes every time it runs, both break — an owner sees colours move and themes
appear to vanish when nothing changed. A spread above 0.05 gets a warning.

## A rule about the data

**Real customer feedback never goes in `dataset/items.json`.**

The first time grouping fails on a real project, the obvious fix is to drop
that customer's items into the evaluation set so you can test against reality.
Don't. That would put confidential feedback about an unreleased product into a
git repository, permanently, where every future contributor can read it.

Reproduce the *shape* of the failure with invented items instead — two themes
that should have merged, a note containing three separate complaints, whatever
went wrong. The harness tests mechanics, and a synthetic reconstruction tests
them just as well.

## What this cannot tell you

**The data is invented.** The 94 items match the counts in the Figma prototype
so the numbers line up with the comps, but nobody really said any of it. Real
feedback is messier: half-sentences, two complaints in one breath, references to
things said on a call. Replace `dataset/items.json` with real items as soon as
you have them — the harness only reads that file.

**The reference grouping is one opinion.** It is the grouping we designed the
views around, not a ground truth. A model that scores 0.8 against it might be
grouping in a defensible way that differs. Read the themes before concluding a
candidate is wrong.

**Names are not scored.** Nothing here can tell you whether "Payment confidence"
reads better than "Payment issues", and that wording is a large part of what an
owner is paying for. Every run saves the raw output next to the scores so you
can read the names yourself.

## Files

```
eval/
  make_dataset.py        regenerates dataset/items.json
  dataset/items.json     the 94 items. Edit or replace freely
  harness/metrics.py     scoring, with a self-test: python3 eval/harness/metrics.py
  harness/prompt.py      the prompt, shared by every provider so the test is fair
  harness/providers.py   adapters. Keys from env, never written to disk
  harness/run.py         the runner
  results/               one JSON per run, with scores and raw output
```

Changing `prompt.py` invalidates earlier scores. Re-run every candidate, not
just the new one.
