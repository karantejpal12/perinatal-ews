"""MCP server: lets AI assistants (Claude Desktop, Claude Code and other MCP clients) query the published results.

    pip install "perinatal-ews[agent]"
    perinatal-ews mcp [--results path-or-url]

The server is read-only and runs on the user's own computer over stdio. It answers only from the published
state results (see ``perinatal_ews.agent_tools``), which contain no counts of 9 or fewer and nothing about
individuals. Setup: docs/mcp_server.md.
"""
from __future__ import annotations

from . import agent_tools as T

INSTRUCTIONS = (
    "perinatal-ews: early-warning results for maternal and newborn health indicators in US states, from CDC "
    "provisional natality data. Take every rate, count, ratio and probability from a tool result and cite the "
    "period and retrieval date. A flag is a statistical signal for follow-up, not proof of a real change or its "
    "cause; changes can come from how births are recorded. Do not give clinical or individual advice. If the "
    "tools do not have the answer, say so."
)


def build_server(source: str | None = None):
    """Create the MCP server; results are loaded once from `source` (path or URL; default: published results)."""
    try:
        from mcp.server.mcpserver import MCPServer as Server          # mcp >= 2
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as Server          # mcp 1.x
        except ImportError as e:
            raise SystemExit('The MCP server needs the "mcp" package: pip install "perinatal-ews[agent]"') from e

    results = T.load_results(source)
    server = Server("perinatal-ews", instructions=INSTRUCTIONS)

    def _call(fn, *args, **kwargs):
        try:
            return fn(results, *args, **kwargs)
        except T.ToolError as e:
            return {"error": str(e)}

    @server.tool()
    def data_status() -> dict:
        """How current the results are (period, latest month, retrieval date, sources) and how many states are flagged."""
        return _call(T.data_status)

    @server.tool()
    def list_state_flags(indicator: str | None = None, level: str = "flagged") -> dict:
        """States flagged this year so far. indicator: e.g. 'preterm_birth' or 'Late or no prenatal care' (all if
        omitted). level: 'flagged' (alert or watch), 'alert' or 'watch'. Includes the chance the full year is flagged."""
        return _call(T.list_state_flags, indicator, level)

    @server.tool()
    def get_state(state: str) -> dict:
        """All four indicators for one state (two-letter code or name): this year so far, the last full year and
        the full-year outlook."""
        return _call(T.get_state, state)

    @server.tool()
    def explain_state_flag(state: str, indicator: str) -> dict:
        """What one state's result for one indicator means, how certain it is, the full-year outlook and its track
        record, reliable results by mother's race, and suggested follow-up checks."""
        return _call(T.explain_state_flag, state, indicator)

    @server.tool()
    def outlook_track_record() -> dict:
        """How well the full-year outlook performed when tested on past years."""
        return _call(T.outlook_track_record)

    return server


def main(source: str | None = None) -> None:
    build_server(source).run()
