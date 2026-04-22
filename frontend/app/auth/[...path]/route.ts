import { NextRequest } from "next/server";

import { proxyToBackend } from "../../../lib/backend-proxy";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: {
    path: string[];
  };
};

async function handle(request: NextRequest, context: RouteContext) {
  return proxyToBackend(request, ["auth", ...context.params.path]);
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE, handle as OPTIONS };
