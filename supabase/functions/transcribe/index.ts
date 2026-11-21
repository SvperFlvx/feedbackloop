// Transcribe one recording, and nothing else.
//
// WHY THIS EXISTS AT ALL
// The capture page is a published web page, so anything in it is readable by
// anyone who opens it. A transcription API key therefore cannot live there.
// This function holds the key and is the only thing that talks to OpenAI.
//
// It is deliberately narrow. It does not write to the database, does not read
// anything, and does not accept a URL to fetch. It takes audio bytes and a
// capture token, checks the token through the same database function the page
// uses, and returns text. If this function is abused, the worst outcome is
// someone else's audio being transcribed on our account — which is why the
// token check is here rather than left to the page.
//
// WHAT IT NEVER DOES
// - store audio or transcripts (that is capture_submit's job, from the page)
// - accept a request without a valid, unexpired, unrevoked capture token
// - return provider error bodies to the caller, which can echo request content

import { createClient } from "jsr:@supabase/supabase-js@2";

const MAX_BYTES = 2_000_000;        // ~4 minutes of phone speech
const MODEL = "whisper-1";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function fail(status: number, message: string) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { ...cors, "content-type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return fail(405, "POST only");

  const key = Deno.env.get("OPENAI_API_KEY");
  if (!key) {
    // Loud and specific: this is the one setup step a human has to do, and a
    // vague failure here would be mistaken for a bug in the page.
    return fail(503, "transcription is not configured: OPENAI_API_KEY is not set on this function");
  }

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return fail(400, "expected multipart form data with 'audio' and 'token'");
  }

  const token = String(form.get("token") ?? "");
  const audio = form.get("audio");
  if (!token) return fail(400, "missing token");
  if (!(audio instanceof File)) return fail(400, "missing audio");
  if (audio.size === 0) return fail(400, "that recording is empty");
  if (audio.size > MAX_BYTES) return fail(413, "that recording is too long");

  // The token is checked against the database, not trusted from the page. The
  // anon key is enough: capture_open is the same SECURITY DEFINER function the
  // page calls, and it raises on a bad, expired or revoked token.
  const db = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
  );
  const { error: tokenError } = await db.rpc("capture_open", { p_token: token });
  if (tokenError) return fail(403, tokenError.message || "invalid link");

  const upstream = new FormData();
  upstream.append("file", audio, audio.name || "note.webm");
  upstream.append("model", MODEL);
  upstream.append("response_format", "json");

  let res: Response;
  try {
    res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}` },
      body: upstream,
    });
  } catch (e) {
    return fail(502, `could not reach the transcription service: ${e instanceof Error ? e.message : "unknown"}`);
  }

  if (!res.ok) {
    // The status is useful to the page; the body is not safe to echo, since a
    // provider error can quote the request back.
    console.error("transcription upstream failed", res.status, await res.text());
    return fail(502, `transcription failed upstream (${res.status})`);
  }

  const out = await res.json().catch(() => null);
  const text = typeof out?.text === "string" ? out.text.trim() : "";
  if (!text) {
    // Silence is a real outcome, not an error: the person may have recorded a
    // quiet room. The page says so rather than showing an empty box.
    return new Response(JSON.stringify({ text: "", empty: true }), {
      headers: { ...cors, "content-type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ text }), {
    headers: { ...cors, "content-type": "application/json" },
  });
});
