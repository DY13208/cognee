import createApiKey from "@/modules/apiKeys/createAPIKey";
import getApiKeys from "@/modules/apiKeys/getApiKeys";

const MCP_KEY_NAME = "MCP (permanent)";

/**
 * Return a permanent API key suitable for Cursor MCP HTTP headers.
 *
 * Prefers an existing key named for MCP, then any key whose cleartext is still
 * readable (HASH_API_KEY=false). Otherwise creates a new permanent key.
 * Keys never expire; revoke via the API Keys page.
 */
export default async function getOrCreateApiKey(): Promise<string> {
  const keys = await getApiKeys();
  const named = keys.find(
    (k) => k.name === MCP_KEY_NAME && k.key && !k.key.includes("*"),
  );
  if (named?.key) return named.key;

  const usable = keys.find((k) => k.key && !k.key.includes("*"));
  if (usable?.key) return usable.key;

  const created = await createApiKey({
    name: MCP_KEY_NAME,
    noRedirectOnAuth: true,
  });
  if (created.ok && created.key?.key) {
    return created.key.key;
  }
  if (!created.ok) {
    throw new Error(created.error || "Failed to create MCP API key");
  }
  throw new Error(
    "API key was created but cleartext was not returned. Disable HASH_API_KEY or recreate the key.",
  );
}
