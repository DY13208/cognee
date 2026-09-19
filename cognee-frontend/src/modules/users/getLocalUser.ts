"use server";

import CogneeUser from "./CogneeUser";
import { cookies } from "next/headers";
import { getServerBackendUrl } from "@/modules/config/serverRuntimeConfig";

export default async function getLocalUser(): Promise<CogneeUser | null> {
  try {
    const response = await fetch(`${getServerBackendUrl()}/api/v1/auth/codebuddy/me`, {
      headers: { cookie: (await cookies()).toString() },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}
