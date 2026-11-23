// Server-side proxy: the browser never sees INTERNAL_TOKEN.
const MAX_QUESTION_LEN = 500;
const MODES = ["live", "replay"] as const;

export async function POST(request: Request): Promise<Response> {
  const token = process.env.INTERNAL_TOKEN;
  const base = process.env.AI_SERVICE_URL ?? "http://127.0.0.1:8000";
  if (!token) {
    return Response.json({ detail: "server not configured" }, { status: 500 });
  }

  let body: { question?: unknown; mode?: unknown; scenario?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "invalid json" }, { status: 400 });
  }

  const { question, mode, scenario } = body;
  if (
    typeof question !== "string" ||
    question.trim().length === 0 ||
    question.length > MAX_QUESTION_LEN ||
    !MODES.includes(mode as (typeof MODES)[number]) ||
    (scenario !== undefined && typeof scenario !== "string")
  ) {
    return Response.json({ detail: "invalid request" }, { status: 422 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Internal-Token": token },
      body: JSON.stringify({ question, mode, scenario }),
      signal: request.signal,
    });
  } catch {
    return Response.json({ detail: "ai service unreachable" }, { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    // Do not forward upstream details (they may echo internals).
    return Response.json({ detail: "ai service error" }, { status: upstream.status === 422 ? 422 : 502 });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}