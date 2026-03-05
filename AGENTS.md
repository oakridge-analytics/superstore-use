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
