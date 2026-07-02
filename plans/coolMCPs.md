mcp-servers-nix
Playwright MCP
For app/frontend testing. It lets the agent open a browser, click through flows, inspect pages, and verify UI behavior. For your “straight-up apps” work, this is still useful if the app has a web UI, Electron/Tauri shell, local dashboard, or docs/demo page.

9. Fetch MCP
Simple but useful. Lets the agent fetch web content and convert it into a more LLM-friendly form. The MCP reference repo lists Fetch as web content fetching and conversion for efficient LLM usage.

12. Docker MCP or container-management MCP
Useful if you want agents to inspect compose files, logs, and container state. Keep it read-mostly unless you trust the workflow.