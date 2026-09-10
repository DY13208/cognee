/** Maps wizard English titles to integrations catalogue keys. */
export const STEP_TITLE_KEYS: Record<string, string> = {
  "Set your API credentials": "credentialsTitle",
  "Install uv (provides uvx)": "installUvTitle",
  "Install the Cognee plugin": "installPlugin",
  "Upload something to Cognee": "uploadSomething",
  "Recall it from Cognee": "recallFromCognee",
  "You're all set": "allSet",
  "Create the workspace AGENTS.md": "createAgentsMd",
  "Test the connection": "testConnection",
  "Open the MCP config file": "openMcpConfig",
  "Add the Cognee server to the config": "addCogneeServer",
  "Restart and test": "restartAndTest",
  "Open Cursor's MCP config": "openCursorMcp",
  "Add the Cognee server to mcp.json": "addToMcpJson",
  "Enable it and test": "enableAndTest",
  "Configure Hermes Agent": "configureHermes",
  "Install the Cognee extension": "installExtension",
  "Run Cognee: Set Up": "runCogneeSetup",
  "Use the core commands": "useCoreCommands",
  "Open your Gemini config file": "openGeminiConfig",
  "Add the Cognee server and save": "addGeminiServer",
  "Open Gemini and confirm it connected": "confirmGemini",
  "Configure Cline": "configureCline",
  "Query the REST API": "queryRestApi",
  "Or install the Cognee skill": "installCogneeSkill",
  "Install the Cognee skill": "installSkill",
  "Install the Cognee community node": "installCommunityNode",
  "Create the Cognee API credential": "createApiCredential",
  "Configure the plugin": "configurePlugin",
  "Add Cognee tools to your app": "addDifyTools",
};

export const STEP_LABEL_KEYS: Record<string, string> = {
  "Option A · Your existing memory": "optionExistingMemory",
  "Option B · Try it with a sample": "optionSample",
  Homebrew: "installUvHomebrew",
  "Install script": "installUvScript",
  Endpoint: "endpoint",
  "API key": "apiKeyLabel",
  "1 · Start Gemini (in your terminal)": "startGemini",
  "2 · Confirm cognee is listed": "confirmCogneeListed",
  "3 · Ask": "ask",
};

export function translateStepText(text: string, t: (key: string) => string): string {
  const key = STEP_TITLE_KEYS[text] ?? STEP_LABEL_KEYS[text];
  return key ? t(key) : text;
}
