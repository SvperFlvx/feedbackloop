# Grouping evaluation harness

Scores how well a model groups feedback into themes, against a fixed set with a
known-correct grouping. Point it at a provider, get a number, compare.

Plain `python3`, no dependencies, no install.

## Your key goes in a file, not the terminal

Copy `eval/.env.example` to `eval/.env`, open it in any text editor, paste your
key after the `=` sign, and save. The harness finds it on its own.

```
ANTHROPIC_API_KEY=sk-ant-...
```

Do this rather than typing `export` at a prompt. A key pasted into a terminal
ends up in shell history and in scrollback, and leaks the moment you paste that
scrollback somewhere to ask about an error. `.env` is gitignored.

## Run it

```bash
# offline baseline — no key needed
python3 eval/harness/run.py --provider mock --model screens-baseline

# a real candidate
python3 eval/harness/run.py --provider anthropic --model <model> --repeat 3

# compare everything you have run
python3 eval/harness/run.py --compare eval/results/*.json
```

Providers: `mock`, `openai`, `anthropic`, `google`, `groq`. Anything speaking the
OpenAI chat-completions shape works through the `openai` adapter by changing
`base_url` in `providers.py` — one line, no new code.

## The number to beat: 0.568

The `mock` provider doesn't call anything. It groups items by which screen they
came from, which is a strategy you could implement in an afternoon with a
`GROUP BY`. It scores **V-measure 0.568**.

That is the floor. A model that doesn't clearly beat 0.568 is not worth paying
for, because grouping by screen is free. Treat it as the first question you ask
of any candidate rather than a curiosity.

## The reference grouping was re-cut, and you should distrust it

On 21 November 2026 the gold grouping in `dataset/items.json` was rebuilt. The
original seven themes were feature areas wearing theme names: "Checkout feels
confusing" held 18 items covering three unrelated problems — not knowing the
price, not knowing whether an action landed, and losing your place — and was
named after a screen plus a feeling. The ten themes there now are user intents,
which is the settled definition: *a theme is something a person was trying to do
that the product made hard*, and intents cross screens.

**Read this before trusting a score.** The re-cut was made after reading one
model's output, which disagreed with the old grouping and turned out to be right.
The new grouping was drawn from the items rather than copied, and in the
checkout and payment region it still lands close to where that model landed —
partly because the items fall that way, and partly because whoever re-cut it had
already seen the answer. So the reference is not independent of the first
candidate scored against it, and that candidate's score is flattered by an
unknown amount.

Two consequences. A score above roughly 0.9 from the model that prompted the
re-cut should be read as agreement, not as quality. And every number recorded
before this date is void — including the old 0.573 floor and the 0.828 that
settled the provider. Re-run anything you want to quote.

Haiku 5.5 scores **0.884 mean, spread 0.025, coverage 1.000** against the re-cut
fixture, at 11 to 13 themes. That is the number to beat, and it carries the
caveat above: it is higher than the 0.828 it scored against the original fixture
partly because the fixture now agrees with it.

The honest fix is a reference drawn from real feedback a real owner grouped. One
design partner's build replaces all of this reasoning with evidence.

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

Every adapter asks for temperature 0, and newer models refuse the parameter
outright. The harness notices, drops it, and says so. The consequence is worth
stating plainly: on those models we cannot hold the output still, so a single
run tells you nothing about stability and `--repeat` stops being optional. A
candidate that scores well once and reshuffles on the next run is disqualified
by the two decisions above, however good the number looked.

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

**The reference grouping is one opinion**, and it has already been wrong once —
see the re-cut above. It is the grouping the views were designed around, not a
ground truth. A model that scores 0.8 against it might be grouping in a
defensible way that differs, and that disagreement is worth more attention than
the score: run `inspect_run.py` and read where it splits before concluding the
candidate is the thing at fault.

**Names are not scored.** Nothing here can tell you whether "Cost clarity" reads
better than "Pricing problems", and that wording is a large part of what an owner
is paying for. Each theme now carries two: a short `name` that has to fit a
matrix column header, and a first-person `statement` for the detail view. Neither
is measured. `inspect_run.py` prints them so you can judge them yourself.

## Files

```
eval/
  make_dataset.py        how items.json was born. Refuses to overwrite it
  dataset/items.json     the 94 items and the gold grouping. The source of truth
  harness/metrics.py     scoring, with a self-test: python3 eval/harness/metrics.py
  harness/prompt.py      the prompt, shared by every provider so the test is fair
  harness/providers.py   adapters, one per provider
  .env                   your keys. Gitignored, never printed, never committed
  harness/run.py         the runner
  harness/inspect_run.py theme names, and which reference themes they split
  results/               one JSON per run, with scores and raw output
```

Changing `prompt.py` invalidates earlier scores. Re-run every candidate, not
just the new one.
