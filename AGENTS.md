## Overview

AI-powered grocery shopping — voice agent + browser automation. See [README.md](README.md) for full details.

ALWAYS use `uv` to run Python. See `.env.example` for required env vars.

## Directory Layout

```
voice-app/
  modal_app.py              # Voice backend (FastAPI on Modal)
  public/app.ts             # Frontend (WebRTC, WebGL orb, audio)
  public/index.html         # Markup + CSS
browser-use-app/
  app.py                    # Browser agent (Modal + LangGraph)
  templates/                # Chat web UI
  static/                   # CSS & JS
mcp-server/
  modal_app.py              # PC Express MCP (FastMCP on Modal). NOT in CI yet.
src/
  core/                     # Shared: browser.py, config.py, agent.py, success.py
  local/cli.py              # Local CLI
  eval/                     # Eval harness: harness.py, config.py, cart_checker.py
  prompts/                  # Prompt templates (login.md, add_item.md, etc.)
conf/                       # Hydra configs
  config.yaml               # Base config
  llm/                      # LLM configs — `uv run -m src.eval.cli list-models`
  browser/                  # headless.yaml, headed.yaml, stealth.yaml
  prompt/                   # default.yaml, concise.yaml
  judge/                    # Cart eval judge configs
  experiment/               # Preset experiment configs
agent_docs/modal.md         # Modal deployment guidelines
config.toml                 # Config for browser agent
.github/workflows/          # CI/CD: auto-deploy on push to main (path-filtered)
```

## Commands

```bash
# Setup
uv sync && uvx playwright install chromium --with-deps --no-shell

# Voice app
cd voice-app && npm ci && npm run build
uv run modal deploy voice-app/modal_app.py

# Browser agent
uv run modal deploy browser-use-app/app.py
uv run modal serve browser-use-app/app.py      # Dev with hot-reload
uv run modal app logs superstore-agent          # Stream logs

# MCP server (manual deploy — not in CI)
uv run modal deploy mcp-server/modal_app.py

# Local CLI (browser agent)
uv run -m src.local.cli login                   # Save browser profile
uv run -m src.local.cli shop                    # Interactive shopping

# Eval harness
uv run -m src.eval.cli                          # Default config
uv run -m src.eval.cli llm=llama_70b            # Override LLM
uv run -m src.eval.cli browser=headed           # Visible browser
uv run -m src.eval.cli --multirun llm=gpt41,llama_70b  # Compare models
uv run -m src.eval.cli list-models              # Available LLMs
uv run -m src.eval.cli list-runs                # Recent runs
```

## PC Express cart contract (read before touching mcp-server or voice-app cart code)

The `POST /pcx-bff/api/v1/carts/{cart_id}` `quantity` field is **not** a uniform "number of units". Its meaning is dictated by `pricingUnits` on the product, which has THREE types — never two:

| `pricingUnits.type`               | `unit` | What `quantity` means in the cart POST                       |
|-----------------------------------|--------|--------------------------------------------------------------|
| `SOLD_BY_EACH`                    | `ea`   | Number of packages (e.g. count=3 for 3 bags)                 |
| `SOLD_BY_WEIGHT`                  | `g`    | Literal grams (e.g. 500 = 0.5 kg, NOT 50 kg)                 |
| `SOLD_BY_EACH_PRICED_BY_WEIGHT`   | `ea`   | Number of pieces (e.g. 6 for 6 loose apples), price computed at pickup from weighed total |

Per-cart-line caps come from `pricingUnits.maxOrderQuantity` and **vary per product** (e.g. loose brussels: 999 g; loose apples: 24 ea; bags: 24–25). Surface this to the LLM up front — the API's "exceeds maximum" error doesn't include the limit.

**Do NOT route on the product code suffix.** `_KG` does not mean "weighed bulk" — loose apples are coded `_KG` but are SOLD_BY_EACH_PRICED_BY_WEIGHT. The only reliable signal is `pricingUnits.type`. Any `code.endswith("_KG")` heuristic in cart code is a bug waiting to happen.

To verify any cart-quantity assumption against ground truth, replay what the website does: drive the product page in Playwright (`uv run python` with `playwright`) and intercept the `/carts/{id}` POST body. The website is the source of truth for valid payload shapes.
