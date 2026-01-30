# Copyright (c) 2026 Nicky
# SPDX-License-Identifier: MIT

"""MCP server entrypoint.

Exposes Overleaf git integration tools via Dedalus MCP framework.
"""

import os

from dedalus_mcp import MCPServer
from dedalus_mcp.server import TransportSecuritySettings

from tools import tools


def create_server() -> MCPServer:
    """Create MCP server with current env config."""
    as_url = os.getenv("DEDALUS_AS_URL", "https://as.dedaluslabs.ai")
    return MCPServer(
        name="overleaf-mcp",
        http_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        streamable_http_stateless=True,
        authorization_server=as_url,
    )


async def main() -> None:
    """Start MCP server."""
    server = create_server()
    for tool_func in tools:
        server.collect(tool_func)
    await server.serve(port=8080)
