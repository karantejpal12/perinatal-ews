# Using perinatal-ews from your AI assistant (MCP server)

`perinatal-ews mcp` lets an AI assistant that supports the Model Context Protocol (MCP), such as Claude Desktop or Claude Code, answer questions from the published state results. Health department staff can ask, in their own words:

- "Which states are flagged for late or no prenatal care this year?"
- "Explain Wisconsin's prenatal care alert. How likely is the full year to be flagged, and what should we check first?"
- "How current are these data?"

The browser-based **Ask AI** tab in the explorer ([ai_assistant.md](ai_assistant.md)) covers the 2024 county results. The MCP server covers this year's monthly state results and the full-year outlook, and works in whichever assistant your organisation already uses.

## Setup

```bash
pip install "perinatal-ews[agent] @ git+https://github.com/karantejpal12/perinatal-ews"
perinatal-ews mcp            # starts the server on stdio; your assistant launches it for you
```

Claude Desktop: add this to `claude_desktop_config.json` (Settings → Developer → Edit config) and restart:

```json
{
  "mcpServers": {
    "perinatal-ews": { "command": "perinatal-ews", "args": ["mcp"] }
  }
}
```

Claude Code: `claude mcp add perinatal-ews -- perinatal-ews mcp`.

By default the server reads the repository copy of `results/latest/latest.json` if you run it from a clone, and otherwise downloads the published file once at start-up. `--results PATH_OR_URL` points it at another copy, for example an agency's own run.

## Tools

| Tool | Returns |
|---|---|
| `data_status` | Period covered, latest month available and whether it was used, retrieval date, sources, number of flags |
| `list_state_flags` | Flagged states, optionally for one indicator and level, with the ratio to expected and the chance the full year is flagged |
| `get_state` | All four indicators for one state: this year so far, the last full year and the full-year outlook |
| `explain_state_flag` | What one result means, how the expected rate is set, the outlook and its track record, reliable results by mother's race, what the flag does not mean, and suggested follow-up checks |
| `outlook_track_record` | How the full-year outlook performed on past years |

## Guardrails

- **Read-only and local.** The server runs on your computer, reads one published file and changes nothing. It sends nothing anywhere except the single download of the published file.
- **Numbers come from the data.** Every rate, count, ratio and probability is copied from the published results; the server computes no new estimates. Each answer includes the period, retrieval date and source, and the server instructs the assistant to cite them and to say when the data do not have an answer.
- **No small counts, nothing about individuals.** The published results suppress counts of 9 or fewer, and results by mother's race are returned only where they are based on at least 20 events.
- **Reporting-quality caveat.** Gestational hypertension results carry a `reporting_caveat` (the birth-certificate item caught only 20–50% of cases in national validation studies), and the assistant is asked to state it with the result; see the [methodology](methodology.md), Limitations.
- **Errors, not guesses.** An unknown state or indicator returns an error listing the valid choices.
- **Framing.** Flags are described as statistical signals for follow-up that can reflect recording changes; the assistant is asked not to give clinical or individual advice.

The assistant's wording is still produced by a language model; confirm important figures in the explorer's state view.

## Testing

`pytest tests/test_agent_tools.py` checks the tools against the published file (flag counts, values, reliable-only race results, errors for unknown input) and, if the `mcp` package is installed, that the server lists and runs every tool.
