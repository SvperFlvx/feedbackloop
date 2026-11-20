"""Provider adapters. Standard library only, so this runs with plain python3.

Each adapter takes a system prompt and a user message and returns raw text.
Adding a provider means adding one function and one line in REGISTRY — the
point is that swapping providers stays an afternoon's work, not a migration.

Keys come from the environment and are never written to disk or into results:
  OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY

The openai_compatible adapter covers anything speaking that API shape (OpenAI,
Groq, Together, OpenRouter, a local server), so most candidates need no code.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: int = 180) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise ProviderError(f"{e.code} from {url}: {detail}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"could not reach {url}: {e.reason}") from None


def _need(var: str) -> str:
    key = os.environ.get(var)
    if not key:
        raise ProviderError(f"{var} is not set")
    return key


def openai_compatible(model: str, system: str, user: str, *,
                      base_url: str = "https://api.openai.com/v1",
                      key_var: str = "OPENAI_API_KEY") -> str:
    data = _post(
        f"{base_url}/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        {"Authorization": f"Bearer {_need(key_var)}",
         "Content-Type": "application/json"},
    )
    return data["choices"][0]["message"]["content"]


def anthropic(model: str, system: str, user: str) -> str:
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {
            "model": model,
            "max_tokens": 8000,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        {"x-api-key": _need("ANTHROPIC_API_KEY"),
         "anthropic-version": "2023-06-01",
         "Content-Type": "application/json"},
    )
    return "".join(b.get("text", "") for b in data.get("content", []))


def google(model: str, system: str, user: str) -> str:
    key = _need("GOOGLE_API_KEY")
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        },
        {"Content-Type": "application/json"},
    )
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise ProviderError(f"unexpected response shape: {json.dumps(data)[:300]}") from None


def groq(model: str, system: str, user: str) -> str:
    return openai_compatible(model, system, user,
                             base_url="https://api.groq.com/openai/v1",
                             key_var="GROQ_API_KEY")


def mock(model: str, system: str, user: str) -> str:
    """Offline adapter. Groups by the screen named on each line, which is a
    deliberately mediocre strategy — it gives the scoring something real to
    chew on without a network call, and sets a floor any candidate must beat."""
    import re
    by_screen: dict[str, list[str]] = {}
    for line in user.splitlines():
        m = re.match(r"^(i\d+) \| screen: ([^|]+) \|", line.strip())
        if m:
            by_screen.setdefault(m.group(2).strip(), []).append(m.group(1))
    themes = [{"name": f"{s} feedback", "summary": f"Items reported on {s}.",
               "item_ids": ids} for s, ids in by_screen.items()]
    return json.dumps({"themes": themes})


REGISTRY = {
    "mock":       lambda m, s, u: mock(m, s, u),
    "openai":     lambda m, s, u: openai_compatible(m, s, u),
    "anthropic":  lambda m, s, u: anthropic(m, s, u),
    "google":     lambda m, s, u: google(m, s, u),
    "groq":       lambda m, s, u: groq(m, s, u),
}


def call(provider: str, model: str, system: str, user: str) -> str:
    if provider not in REGISTRY:
        raise ProviderError(f"unknown provider '{provider}'. known: {', '.join(REGISTRY)}")
    return REGISTRY[provider](model, system, user)
