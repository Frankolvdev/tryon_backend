import { NextRequest, NextResponse } from "next/server";

import { forwardAdminRequest } from "@/lib/server/admin-route-proxy";

type RouteContext = {
  params: Promise<{ segments?: string[] }>;
};

async function backendPath(
  request: NextRequest,
  context: RouteContext,
): Promise<string> {
  const { segments = [] } = await context.params;
  const suffix = segments.length
    ? `/${segments.map(encodeURIComponent).join("/")}`
    : "";

  return `/api/v1/admin/runtime-builder${suffix}${request.nextUrl.search}`;
}

async function proxy(
  request: NextRequest,
  context: RouteContext,
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
): Promise<NextResponse> {
  return forwardAdminRequest({
    backendPath: await backendPath(request, context),
    method,
    request,
  });
}

export function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "GET");
}

export function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "POST");
}

export function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "PUT");
}

export function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "PATCH");
}

export function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "DELETE");
}
