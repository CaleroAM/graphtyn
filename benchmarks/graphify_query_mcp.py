#!/usr/bin/env python3
"""One-tool MCP adapter for fair Graphify query benchmarks.

Some model gateways omit Graphify's MCP when all ten tools are advertised.
This adapter exposes only ``query_graph`` while delegating the graph loading and
query response to the installed Graphify package.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from graphify.serve import _query_graph_text, _read_graph
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


def build_server(graph_path: Path) -> Server:
    graph = None

    async def list_tools(_ctx, _params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[types.Tool(
            name="query_graph",
            description="Search the Graphify knowledge graph and return relevant nodes and edges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs"},
                    "depth": {"type": "integer", "default": 3},
                    "token_budget": {"type": "integer", "default": 2000},
                    "context_filter": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question"],
            },
        )])

    async def call_tool(_ctx, params) -> types.CallToolResult:
        nonlocal graph
        if graph is None:
            graph = _read_graph(str(graph_path))
        args = dict(params.arguments or {})
        text = _query_graph_text(
            graph,
            args["question"],
            mode=args.get("mode", "bfs"),
            depth=min(int(args.get("depth", 3)), 6),
            token_budget=int(args.get("token_budget", 2000)),
            context_filters=args.get("context_filter"),
            graph_path=str(graph_path.resolve()),
        )
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])

    return Server("graphify-query-benchmark", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True, type=Path)
    args = parser.parse_args()
    server = build_server(args.graph)
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
