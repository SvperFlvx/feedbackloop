// Group a project's capture notes into themes, and store the run whole.
//
// WHAT IS PRODUCTION HERE AND WHAT IS NOT
//
// The prompt, the one-call-over-the-whole-set shape, and this
// function-plus-secret pattern are the parts meant to outlive the pilot.
// Reading capture_note and writing capture_run are not: the product groups
// over item/theme/theme_item per build, which needs accounts the pilot
// deliberately does not have. When real submissions exist, the reader and the
// writer change and the middle stays.
//
// ONE NOTE IS ONE ITEM HERE. Splitting a rambling recording into several items
// is a real step that is deliberately not built yet: the first eight
// recordings get split by hand, so we find out what real speech actually
// contains before writing a prompt that guesses. Until then a long note
// holding three complaints will be grouped as one thing, and that is a known
// limitation of these runs rather than a property of the model.
//
// THE PROMPT IS A COPY. It is frozen, and its source of truth is
// eval/harness/prompt.py so the harness and the product score the same thing.
// Every run stores the hash of the prompt it used, so a copy that has drifted
// is visible in the data rather than silently producing incomparable runs.

const PROMPT_SHA = "0a535fa84933fe04";

const SYSTEM = "You group product feedback into themes.\n\nA theme is something a person was trying to do, or trying to know, that the\nproduct made hard. Several different people hit the same wall in their own\nwords. It is not a feature area, not a screen, and not a defect category.\n\nThemes cross screens, and that is the point rather than a problem. If people\ncannot tell whether their action worked, that shows up in the cart, at checkout\nand on the payment screen, and it is one theme with three places it appears \u2014\nnot three themes.\n\nRules:\n- Every item must be assigned to exactly one theme. Never drop an item.\n- A theme needs at least three items from three different people. Fewer than\n  that is one person's opinion, and its reach is too small for anyone to act on.\n- One theme is one thing an owner could decide to address. Not one engineering\n  task: slow loading and stuttering scrolling are different work and the same\n  finding.\n- If two candidate themes would be described in the same sentence, they are one\n  theme. When you are unsure, choose the larger theme.\n- An owner reads these ranked and acts on the top few. Much past a dozen themes\n  is a list rather than a finding, and splitting a hundred items nineteen ways\n  leaves every theme too small to be worth a row.\n- Never name a theme after a screen, a feature or a defect category. A name like\n  \"Checkout problems\" is both a screen and a category and is wrong twice.\n- A theme that holds everything about one area of the app is a container, not a\n  theme. Split a container by what people were trying to do \u2014 never by which\n  screen they were on, and never by which fix it would take.\n- The summary states what people said. It must not assert why, or what to build.\n\nEach theme carries two names:\n- \"name\": a short label, at most three words, that fits a table column header.\n  A noun phrase: \"Cost clarity\", \"Action confirmation\", \"Card entry friction\".\n- \"statement\": one sentence in the user's own voice, saying what they wanted to\n  be able to do: \"Knowing what I'll pay before I commit\".\n\nReturn JSON only, with this exact shape:\n{\"themes\": [{\"name\": \"...\", \"statement\": \"...\", \"summary\": \"...\",\n             \"item_ids\": [\"i001\", \"i002\"]}]}\n";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type, authorization, x-run-secret",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function fail(status: number, message: string) {
  return new Response(JSON.stringify({ error: message }), {
    status, headers: { ...cors, "content-type": "application/json" },
  });
}

async function db(path: string, init: RequestInit = {}) {
  const url = Deno.env.get("SUPABASE_URL")!;
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const res = await fetch(`${url}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: key, Authorization: `Bearer ${key}`,
      "content-type": "application/json", ...(init.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`database said ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return fail(405, "POST only");

  // Owner-side work, not capture. A capture token must not reach it, so this
  // is a separate secret that only whoever runs a grouping holds.
  const want = Deno.env.get("GROUP_RUN_SECRET");
  if (!want) return fail(503, "grouping is not configured: GROUP_RUN_SECRET is not set on this function");
  if (req.headers.get("x-run-secret") !== want) return fail(403, "wrong or missing x-run-secret");

  const key = Deno.env.get("ANTHROPIC_API_KEY");
  if (!key) return fail(503, "grouping is not configured: ANTHROPIC_API_KEY is not set on this function");

  let body: Record<string, unknown>;
  try { body = await req.json(); } catch { return fail(400, "expected a JSON body"); }

  const project = String(body.project ?? "");
  const label = String(body.label ?? "baseline");
  const model = String(body.model ?? "claude-haiku-5-5");
  // A grain hint is appended to the frozen prompt and recorded with the run,
  // so a deliberate coarse/fine experiment can never be mistaken for baseline.
  const grain = body.grain ? String(body.grain) : null;
  if (!project) return fail(400, "which project? pass project");

  const notes = await (await db(
    `capture_note?select=id,screen_name,transcript,typed,capture_person_id,` +
    `capture_person!inner(label,project_id,affiliation)&` +
    `capture_person.project_id=eq.${project}&order=created_at`)).json();

  if (!Array.isArray(notes) || notes.length === 0) return fail(404, "no notes on that project yet");

  const usable = notes.filter((n: any) => (n.transcript || "").trim().length > 0);
  if (usable.length === 0) return fail(409, "there are notes but none has a transcript yet");

  const lines = usable.map((n: any, i: number) => {
    const id = `i${String(i + 1).padStart(3, "0")}`;
    return { id, note: n.id, line:
      `${id} | screen: ${n.screen_name} | from: ${n.capture_person.label} | "${String(n.transcript).trim()}"` };
  });

  const user =
    `Here are ${lines.length} pieces of feedback on a mobile app.\n\n` +
    lines.map(l => l.line).join("\n") +
    `\n\nGroup them into themes. Return JSON only.`;

  const system = grain ? `${SYSTEM}\n${grain}` : SYSTEM;

  const started = Date.now();
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model, max_tokens: 16000, system, messages: [{ role: "user", content: user }] }),
  });
  if (!res.ok) {
    console.error("grouping upstream failed", res.status, await res.text());
    return fail(502, `grouping failed upstream (${res.status})`);
  }
  const out = await res.json();
  const text = (out.content || []).filter((b: any) => b.type !== "thinking")
    .map((b: any) => b.text || "").join("").trim();
  const seconds = (Date.now() - started) / 1000;

  let themes: any[];
  try {
    const start = text.indexOf("{"), end = text.lastIndexOf("}");
    if (start < 0) throw new Error("no JSON in the reply");
    themes = JSON.parse(text.slice(start, end + 1)).themes || [];
  } catch (e) {
    console.error("grouping reply could not be read", text.slice(0, 600));
    return fail(502, `the model's reply could not be read: ${e instanceof Error ? e.message : "unknown"}`);
  }

  // The model sees i001-style ids, never database ids. Map back here so the
  // stored run points at real notes without the model ever handling them.
  const byShort = new Map(lines.map(l => [l.id, l.note]));
  const placed = new Set<string>();
  const resolved = themes.map((t: any) => {
    const ids = (t.item_ids || []).map((s: string) => byShort.get(s)).filter(Boolean);
    ids.forEach((i: string) => placed.add(i));
    return { ...t, note_ids: ids, item_ids: undefined };
  });
  const dropped = lines.filter(l => !placed.has(l.note)).map(l => l.id);

  const saved = await (await db("capture_run?select=id", {
    method: "POST",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify({
      project_id: project, label, model, grain_hint: grain,
      prompt_sha: PROMPT_SHA, note_count: lines.length,
      theme_count: resolved.length, seconds: seconds.toFixed(2),
      themes: { themes: resolved, dropped },
    }),
  })).json();

  return new Response(JSON.stringify({
    run: saved?.[0]?.id, label, model, grain_hint: grain,
    notes: lines.length, themes: resolved.length, seconds: Number(seconds.toFixed(1)),
    dropped: dropped.length,            // never zero quietly: dropping feedback is the worst failure
    names: resolved.map((t: any) => t.name),
  }), { headers: { ...cors, "content-type": "application/json" } });
});
