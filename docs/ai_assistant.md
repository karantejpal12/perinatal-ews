# AI assistant: "Ask perinatal-ews" (v0.4)

The explorer includes an AI assistant that answers questions about the published results in plain language, for example *"Which Georgia counties got worse on prenatal care, and is it state-wide?"* or *"Which counties look stable now but are likely to be flagged next year?"*. Health department staff can get an answer without reading CSV files or the bulletin.

## How it works

The assistant is a large language model (Anthropic Claude, Sonnet 5.5 by default, Haiku 5.5 optional) used as an **agent with tools**. It never sees the raw data or the internet. Instead, it calls six data tools that read the same published results as the explorer and the bulletin (`results/2024/explorer.json`):

| Tool | Returns |
|---|---|
| `search_counties` | Counties matching a name and/or state, with FIPS codes |
| `get_county` | Everything for one county: 2024 status and rates by indicator, payer subgroups, rates by year, next-year risk and its main factors, comparison with similar counties, county context and need-and-access status, plus a plain-language brief |
| `list_counties` | County-indicator results for a filter (flagged, alert, subgroup flag, high next-year risk, stable but high risk, need and access, higher than similar counties), optionally by state and indicator |
| `state_summary` | One state: flags by indicator, state-wide patterns, need-and-access counties, flagged counties, plus a brief |
| `national_summary` | National totals, state-wide patterns, forecast validation metrics, model fit and data sources |
| `method_info` | How detection, the forecast, the similar-county comparison and the need-and-access list work, and their limitations |

The model decides which tools to call, the browser runs them, and the results go back to the model, for up to eight rounds. Each lookup is shown to the reader above the answer.

## Guardrails

- **Grounding.** The system instructions require every rate, count, risk or ranking to come from a tool result, and require the model to say when the data do not have an answer.
- **Figure check.** After each answer, every figure in it is checked against all the tool results from that conversation turn. A figure counts as matched only if it equals a value in the results after rounding to the same number of decimals, either as given or as a percentage. Figures that cannot be matched are listed under the answer so the reader knows to check them. Years and small whole numbers are skipped.
- **Framing.** Flags are presented as statistical signals for follow-up, state-wide clusters are flagged as possible recording changes, county context is described as describing places, not people, and causal claims and clinical or individual advice are declined.
- **Privacy.** The site has no server. The reader's Anthropic API key goes only from their browser to `api.anthropic.com`, and is kept for the browser tab unless they choose to remember it on their device. Questions and answers are not stored by perinatal-ews. The published data contain no counts of 9 or fewer (NCHS rule) and nothing about individuals.

## Without an API key

Each county page and the state view open with a **plain-language summary written by fixed rules** directly from the data (no AI model). The same briefs are available in the Ask AI tab. They cover flags, payer-group flags, state-wide patterns, next-year risk, the similar-county comparison and need and access.

## Testing

`node --test tests/js/ews-tools.test.js` checks that:

- every tool runs on the published data;
- briefs contain only figures that are in the data;
- state counts agree between tools;
- the figure check catches invented numbers and numbers that only nearly match;
- unknown counties return an error instead of a guess.

The full assistant loop (tool call, tool result, final answer, figure check) was tested in an automated browser against a simulated model response that included one invented figure; the figure check flagged it.

## Limitations

- Answers come from a language model and can still be wrong in wording or emphasis even when every figure matches; important figures should be confirmed on the county pages.
- The figure check confirms that a number exists in the looked-up data, not that it is attached to the right county or indicator.
- The assistant covers only the published results (578 counties with 100,000+ residents, 2016–2024). It cannot analyse a user's own uploaded data; use "Run on your data" for that.
- Using it requires an Anthropic API key and is billed to the key holder by Anthropic.
