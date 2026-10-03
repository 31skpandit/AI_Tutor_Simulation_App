# AI Teaching Studio

An AI teaching assistant that runs on your laptop. You upload your textbook chapters, and it turns them into
lessons with accurate chemistry visuals, interactive simulations and animated videos. It also includes an
AI tutor that answers students' questions from the textbook.

- **Full plan:** [docs/AI_Teaching_Studio_Project_Blueprint_v1.2.docx](docs/AI_Teaching_Studio_Project_Blueprint_v1.2.docx)
  (architecture, workflows, model strategy, security rules, phase plan). Diagrams are in [docs/diagrams/](docs/diagrams/).
- **Current status:** Phase 0 (foundation) complete. The last check, a live OpenAI test, waits for your API key (step 4).

---

## 1. One-time setup

These tools are already installed on this laptop:
uv 0.12.11 · Python 3.12.14 (managed by uv) · Git 2.51 · Ollama 0.34.4 · FFmpeg 9.0.2 · MiKTeX 25.12.

Open a terminal **in this project folder** and run:

| # | Step | Command |
|---|---|---|
| 1 | Get the local AI models | `ollama pull qwen3:4b-instruct`  ·  `ollama pull qwen3-vl:4b`  ·  `ollama pull qwen3-embedding:0.6b` |
| 2 | Install packages **only from the lockfile** (checks every SHA-256 hash) | `uv sync --locked` |
| 3 | Create your settings file (it holds no secrets) | `copy .env.example .env` |
| 4 | Store your OpenAI key in Windows Credential Manager (input is hidden) | `uv run python -m app.core.secrets set openai` |
| 5 | Run the security checks (all lines should show `OK`) | `uv run python -m app.core.startup_checks` |
| 6 | Check that every configured model exists, and compare prices | `uv run python -m app.tools.verify_models` |

> Before step 4, create a separate Project in the OpenAI dashboard (e.g. "ai-teaching-studio"), give it its
> own restricted API key, and set a **monthly budget limit** on it. Never paste keys into `.env` or any file.

## 2. Daily use

1. Make sure the **Ollama** app is running (look for its tray icon).
2. Start the studio: `uv run streamlit run ui/Home.py`
3. Your browser opens **http://localhost:8501**. The app only accepts connections from this laptop.
4. Stop it with `Ctrl + C` in the terminal.

| Page | What it does now |
|---|---|
| Home | Security checks, local models, stored keys, this month's spend |
| AI Tutor | Phase 0 test chat (local model is free; OpenAI is paid). Answers come from the textbook from Phase 1 |
| Settings & Cost | Budget, API keys, model routing, *Verify models*, log of every AI call with its cost |
| Teach Mode / Lesson Studio / Syllabus Library | Placeholders, built in Phases 1–2 |

## 3. Changing models or the budget

- **Models:** edit [config/models.yaml](config/models.yaml). Each task has a `primary` model and `fallbacks`.
  Every paid model needs a price. Then click **Reload configuration** on the *Settings & Cost* page.
- **Budget:** set `ATS_MONTHLY_BUDGET_USD` in `.env` (default **$5/month**). Once the cap is reached, paid models
  are skipped and the free local model answers instead. Premium models (e.g. `gpt-5.2`) are never used without your approval.

## 4. Security rules (blueprint §14). Always follow these

- ✅ Install with `uv sync --locked` only. ❌ Never `pip install …` into this project.
- ✅ Keep API keys in Credential Manager (step 4). ❌ Never in `.env`, code, chat or screenshots.
- ✅ LiteLLM stays pinned to a clean version ≥ 1.83.0 (now **1.102.1**). 1.82.7 / 1.82.8 were malicious.
- ✅ The app refuses AI calls to hosts not listed in `allowed_hosts` in `config/models.yaml`.
- ✅ Run the vulnerability audit before upgrades and at the end of each phase:
  `powershell -ExecutionPolicy Bypass -File scripts\audit.ps1`

### Upgrading a package safely (one at a time)

1. Read the package's changelog and security advisories.
2. In `pyproject.toml`, move `exclude-newer` to **today minus 7 days**, then change the package's exact `==` version.
3. `uv lock --upgrade-package <name>` → review the `uv.lock` changes → `uv sync --locked`
4. `scripts\audit.ps1` → `uv run pytest` → commit.

## 5. For development

```
uv run pytest            # 48 automated tests (no internet, no cost)
uv run ruff check .      # lint
uv run ruff format .     # format
```

```
app/core/      settings, secrets (Credential Manager), logging with key redaction, security checks
app/db/        SQLite tables: AI call log (cost dashboard) and response cache
app/llm/       router (fallbacks, budget, cache, allow-list), the only LiteLLM import, health checks
app/tools/     verify_models
config/        models.yaml: task → model routing, prices, budget, allowed hosts
ui/            Streamlit app: Home.py + pages/
tests/         automated tests
scripts/       audit.ps1
docs/          project blueprint (.docx) + diagrams
data/          created at runtime: database, logs (not in Git)
```

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| "Ollama is not running" | Start the Ollama app, then refresh the page |
| Home shows a ❌ security check | Read the message. For a LiteLLM version problem run `uv sync --locked` |
| OpenAI answers are skipped | No key stored (step 4), budget reached, or the model isn't available to your key (step 6) |
| First local answer is slow (~15 s) | The model is loading into GPU memory. Later answers are faster |
