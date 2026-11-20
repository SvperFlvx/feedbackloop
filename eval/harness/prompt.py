"""The grouping prompt, shared across every provider.

Keeping one prompt for all candidates is what makes the comparison fair: a
difference in score is then a difference in the model, not in how hard someone
tried on its prompt. If you change this, re-run every provider, not just the
new one — old scores are not comparable to new ones.

The prompt encodes product decisions that are already settled, so a model that
ignores them scores badly on purpose:
  - themes are a reading, not a measurement, so the summary must not assert
    causes the feedback does not support
  - a theme needs more than one person behind it, or it is one person's opinion
  - every item must be placed; silently dropping feedback is the worst failure
"""

SYSTEM = """You group product feedback into themes.

A theme is a recurring expectation that several different people expressed, in
their own words, about the same underlying thing. It is not a category, not a
screen, and not a feature request list.

Rules:
- Every item must be assigned to exactly one theme. Never drop an item.
- A theme must contain items from at least two different people.
- Prefer fewer, larger themes over many small ones. If two candidate themes
  would be described in the same sentence, they are one theme.
- Do not create a theme that just restates a screen name.
- Name a theme as the expectation behind it, in the users' register, not as a
  defect category. "Payment confidence" rather than "Payment bugs".
- The summary states what people said. It must not assert why, or what to build.

Return JSON only, with this exact shape:
{"themes": [{"name": "...", "summary": "...", "item_ids": ["i001", "i002"]}]}
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
