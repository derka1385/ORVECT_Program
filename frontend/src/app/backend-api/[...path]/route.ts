const upstream = (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");

export const dynamic = "force-dynamic";
export const maxDuration = 120;

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const target = `${upstream}/${path.map(encodeURIComponent).join("/")}${incoming.search}`;
  const headers = new Headers(request.headers);
  for (const name of ["connection", "content-length", "host", "transfer-encoding"]) headers.delete(name);

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };
  if (request.method !== "GET" && request.method !== "HEAD") init.body = await request.arrayBuffer();

  try {
    const response = await fetch(target, init);
    const responseHeaders = new Headers(response.headers);
    for (const name of ["connection", "content-length", "transfer-encoding"]) responseHeaders.delete(name);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "Backend temporairement indisponible." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
