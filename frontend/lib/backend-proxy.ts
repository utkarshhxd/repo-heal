import { NextRequest } from "next/server";

const DEFAULT_BACKEND_URL = "http://localhost:8000";

function getBackendUrl() {
  return (process.env.BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/$/, "");
}

function copyRequestHeaders(request: NextRequest) {
  const headers = new Headers(request.headers);

  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  headers.set("x-forwarded-host", request.headers.get("host") ?? request.nextUrl.host);
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  headers.set("x-forwarded-for", request.headers.get("cf-connecting-ip") ?? request.ip ?? "127.0.0.1");

  return headers;
}

export async function proxyToBackend(request: NextRequest, path: string[]) {
  const upstreamUrl = new URL(`${getBackendUrl()}/${path.join("/")}`);
  upstreamUrl.search = request.nextUrl.search;

  const headers = copyRequestHeaders(request);
  const body =
    request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();

  const upstreamResponse = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
    redirect: "manual",
    cache: "no-store",
  });

  const responseHeaders = new Headers(upstreamResponse.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });
}
