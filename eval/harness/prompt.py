"""The grouping prompt, shared across every provider.

Keeping one prompt for all candidates is what makes the comparison fair: a
difference in score is then a difference in the model, not in how hard someone
tried on its prompt. If you change this, re-run every provider, not just the
new one — old scores are not comparable to new ones.

The prompt encodes product decisions that are already settled, so a model that
ignores them scores badly on purpose:
  - a theme is a user intent, not a feature area and not a screen. Intents cross
    screens, and a theme that lights up on five screens is the stronger finding
  - themes are a reading, not a measurement, so the summary must not assert
    causes the feedback does not support
  - a theme needs more than one person behind it, or it is one person's opinion
  - every item must be placed; silently dropping feedback is the worst failure
  - a theme carries a short label for the views and a sentence for the detail
    view, because the label has to fit a matrix column header
"""

SYSTEM = """You group product feedback into themes.

A theme is something a person was trying to do, or trying to know, that the
product made hard. Several different people hit the same wall in their own
words. It is not a feature area, not a screen, and not a defect category.

Themes cross screens, and that is the point rather than a problem. If people
cannot tell whether their action worked, that shows up in the cart, at checkout
and on the payment screen, and it is one theme with three places it appears —
not three themes.

Rules:
- Every item must be assigned to exactly one theme. Never drop an item.
- A theme needs at least three items from three different people. Fewer than
  that is one person's opinion, and its reach is too small for anyone to act on.
- One theme is one thing an owner could decide to address. Not one engineering
  task: slow loading and stuttering scrolling are different work and the same
  finding.
- If two candidate themes would be described in the same sentence, they are one
  theme. When you are unsure, choose the larger theme.
- An owner reads these ranked and acts on the top few. Much past a dozen themes
  is a list rather than a finding, and splitting a hundred items nineteen ways
  leaves every theme too small to be worth a row.
- Never name a theme after a screen, a feature or a defect category. A name like
  "Checkout problems" is both a screen and a category and is wrong twice.
- A theme that holds everything about one area of the app is a container, not a
  theme. Split a container by what people were trying to do — never by which
  screen they were on, and never by which fix it would take.
- The summary states what people said. It must not assert why, or what to build.

Each theme carries two names:
- "name": a short label, at most three words, that fits a table column header.
  A noun phrase: "Cost clarity", "Action confirmation", "Card entry friction".
- "statement": one sentence in the user's own voice, saying what they wanted to
  be able to do: "Knowing what I'll pay before I commit".

Return JSON only, with this exact shape:
{"themes": [{"name": "...", "statement": "...", "summary": "...",
             "item_ids": ["i001", "i002"]}]}
"""


def user_message(items: list[dict]) -> str:
    """items are the public fields only — gold_theme and gold_type are stripped
    by the runner before anything reaches a model."""
    lines = []
    for it in items:
        lines.append(
            f'{it["id"]} | screen: {it["screen"]} | build: {it["build"]} | '
            f'from: {it["author"]} | "{it["text"]}"'
        )
    body = "\n".join(lines)
    return (
        f"Here are {len(items)} pieces of feedback on a mobile app.\n\n"
        f"{body}\n\n"
        "Group them into themes. Return JSON only."
    )


TYPE_SYSTEM = """You label a single piece of product feedback with one type.

bug          something is broken or behaves wrongly
question     the person does not understand something or is unsure
improvement  a request, suggestion, or a wish for something different
praise       the person says something works well

Return JSON only: {"type": "bug"}
"""


def type_user_message(item: dict) -> str:
    return f'Screen: {item["screen"]}\nFeedback: "{item["text"]}"\n\nReturn JSON only.'
