"""`call(tool, **args) -> dict` wrappers so one policy runs locally or against a served environment."""
import asyncio
import json

from mcp import ClientSession
# ponytail: deprecated name kept because it exists in every mcp>=1.20; newer SDKs call it streamable_http_client.
from mcp.client.streamable_http import streamablehttp_client


def local_call(env):
    return env.call


def http_call(url):
    """Sync call over MCP streamable HTTP. Returns the env's {"ok", "t", ...} dict; protocol-level
    rejections (schema validation) come back as ok=False with the server's message."""
    last_t = [0]

    async def once(tool, args):
        # ponytail: one short-lived session per call (the server is stateless); fine for <=150 calls.
        async with streamablehttp_client(url) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await s.call_tool(tool, args)

    def call(tool, **args):
        res = asyncio.run(once(tool, args))
        text = "".join(c.text for c in res.content if getattr(c, "text", None) is not None)
        if res.isError:
            return {"ok": False, "t": last_t[0], "error": text}
        out = json.loads(text)
        last_t[0] = out["t"]
        return out
    return call
