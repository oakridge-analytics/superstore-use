# superstore-use

Speed up your PC Express grocery shopping with an llm voice agent.

https://dbandrews--pc-express-voice-serve.modal.run/

Two ways to shop:

- **Voice App** — Talk to an AI assistant that searches products, adds to cart, and suggests recipes via voice. Uses OpenAI Realtime API with WebRTC.
- **Browser Agent** — Type grocery requests into a chat UI and an LLM agent automates browsers in parallel to navigate the store website and add items to your cart. Robust to PC ExpressAPI changes. Done as a technical learning exercise.

## Voice App

WebRTC voice shopping UI. Speak naturally to search products, get recipe suggestions, and manage your cart in real time.

**Capabilities:**
- Store finder and selection based on geocoded location
- Product search with real-time inventory filtering
- Cart management (add/remove items with quantities) by voice
- Recipe mode — describe what you want to cook and the assistant builds a shopping list

**Tech stack:** OpenAI Realtime API (`gpt-realtime-mini`), FastAPI on Modal, Mapbox geocoding, PC Express API

### Deploy

```bash
cd voice-app && npm run build
uv run modal deploy voice-app/modal_app.py
```

**Required Modal secrets:**
| Secret | Keys | Note |
|--------|------|------|
| `pc-express-voice-openai` | `OPENAI_API_KEY` ||
| `mapbox-api-key` | `MAPBOX_API_KEY` ||
| `pc-express-voice-app-token` | `VOICE_APP_TOKEN` | Token for authentication to backend, can be generated as desired |

## Browser Agent

Chat-based web UI where you type grocery requests and an LLM-driven agent automates a real Chromium browser (via Playwright) to shop on the Superstore website.

**Tech stack:** browser-use + LangGraph + Playwright, deployed on Modal with xvfb for headful rendering

### Deploy

```bash
uv run modal deploy browser-use-app/app.py
```

Access the web UI at the URL shown in deploy output with your auth token:
```
https://your-workspace--your-app-name-web.modal.run?token=YOUR_WEB_AUTH_TOKEN
```

**Required Modal secrets:**
| Secret | Keys |
|--------|------|
| `groq-secret` | `GROQ_API_KEY` |
| `superstore` | `SUPERSTORE_USER`, `SUPERSTORE_PASSWORD` |
| `web-auth` | `WEB_AUTH_TOKEN` |
| `oxy-proxy` (optional) | `PROXY_SERVER`, `PROXY_USERNAME`, `PROXY_PASSWORD` |

## Repo Structure

```
voice-app/
  modal_app.py          # Voice app backend (FastAPI on Modal)
  public/               # Frontend (app.ts, index.html, WebGL orb)
config.toml             # Config for browser agent application
browser-use-app/
  app.py                # Browser agent (Modal + LangGraph)
  templates/            # Chat web UI
  static/               # CSS & JavaScript
src/
  core/                 # Shared utilities (browser, config, agent)
  local/                # Local CLI (login, shop)
  eval/                 # Evaluation harness
  prompts/              # AI prompt templates
conf/                   # Hydra configs for evals (llm/, browser/, prompt/, judge/)
```

## Local Development

### Setup

```bash
uv sync
uvx playwright install chromium --with-deps --no-shell
```

### Voice app

```bash
cd voice-app && npm ci && npm run build
```

### Browser agent local CLI

```bash
# Save login session (stores profile in superstore-profile/)
uv run -m src.local.cli login

# Interactive shopping
uv run -m src.local.cli shop
```

### Evaluation Harness

Test browser agents with different LLMs, prompts, and configurations. Each run uses an isolated browser profile (no login required) and verifies results via LLM-based cart judgment.

**What it does:**
1. Creates a fresh temporary browser profile for each run
2. Adds each requested item to cart (separate browser per item)
3. Verifies cart contents after all items are added
4. Uses LLM judge to evaluate if items match requests (semantic matching + quantity check)
5. Outputs results with timing metrics and success rates

**Run evaluations:**

```bash
# Run with default config
uv run -m src.eval.cli

# Custom items
uv run -m src.eval.cli 'items=[bread,eggs,butter]'

# Use different LLM
uv run -m src.eval.cli llm=llama_70b

# Visible browser (for debugging)
uv run -m src.eval.cli browser=headed

# Sweep across LLMs
uv run -m src.eval.cli --multirun llm=gpt4,llama_70b

# Parallel sweep
uv run -m src.eval.cli --multirun hydra/launcher=joblib llm=gpt41,llama_70b

# List available LLMs
uv run -m src.eval.cli list-models

# List recent runs
uv run -m src.eval.cli list-runs

# Browse temp profile from previous run (inspect cart state)
uv run -m src.eval.cli browse /tmp/eval-profile-abc123/profile
```

**Configuration** is Hydra-based in `conf/`:
- `conf/llm/` — LLM configs (gpt4, llama_70b, etc.)
- `conf/browser/` — Browser configs (headless, headed)
- `conf/prompt/` — Prompt templates
- `conf/judge/` — Judge configs for cart evaluation

## Environment Variables

For local development, create a `.env` file:

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq LLM access (browser agent) |
| `OPENROUTER_API_KEY` | OpenRouter models (optional) |
| `OPENAI_API_KEY` | OpenAI models / eval judge (optional) |
| `SUPERSTORE_USER` | Superstore login email |
| `SUPERSTORE_PASSWORD` | Superstore login password |
