import { NextRequest } from "next/server";

const BACKEND = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const body = await req.json();

  // Forward the bearer token (if any) so the backend's optional auth passes.
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const auth = req.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const upstream = await fetch(`${BACKEND}/api/enhance-prompt`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    const err = await upstream.json().catch(() => ({ detail: upstream.statusText }));
    return new Response(JSON.stringify(err), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
