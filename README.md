# AI Teaching Studio

An AI teaching assistant that runs on your laptop. You add your textbook chapters (PDFs, photos, Word files),
check the extracted text once, and then an AI tutor answers students' questions **from your textbook, with page
references**. Lessons, simulations and animated videos are added in Phases 2–3.

- **Full plan:** [docs/AI_Teaching_Studio_Project_Blueprint_v1.5.docx](docs/AI_Teaching_Studio_Project_Blueprint_v1.5.docx)
  (architecture, workflows, models, security, phase plan). Diagrams: [docs/diagrams/](docs/diagrams/).
- **Learning log:** [docs/Claude Interactions.docx](docs/Claude%20Interactions.docx) — every change, the key code
  and why, and every issue/mistake with cause and fix (updated in every session).
- **Status:** Phase 0 ✅ · Phase 1 ✅ (+ improvements) · **Phase 2 ✅ built — 3 pilot lessons ready for your review**
  (section 3c) · next: Phase 3 (animated videos & narration).

**Contents:** 1 One-time setup · 2 Start / stop · 3 Test Phase 1 with your PDF · 3b Better tables & diagrams ·
3c Lessons & simulations (Phase 2) · 4 Teaching with the app · 5 Adding more chapters · 6 Models & budget ·
7 Security rules · 8 Development · 9 Troubleshooting

---

## 1. One-time setup

Already installed on this laptop: uv 0.12.11 · Python 3.12.14 (via uv) · Git 2.51 · Ollama 0.34.4 · FFmpeg 9.0.2 · MiKTeX 25.12.

Open a terminal **in this project folder** and run:

| # | Step | Command |
|---|---|---|
| 1 | Download the local AI models (free) | `ollama pull qwen3:4b-instruct` · `ollama pull qwen3-vl:2b-instruct` · `ollama pull qwen3-embedding:0.6b` |
| 2 | Install packages **only from the lockfile** (every SHA-256 hash checked) | `uv sync --locked` |
| 3 | Create your settings file (it holds no secrets) | `copy .env.example .env` |
| 4 | *(Optional — for paid OpenAI features)* store your key in Windows Credential Manager | `uv run python -m app.core.secrets set openai` |
| 5 | Security checks — every line must say `OK` | `uv run python -m app.core.startup_checks` |
| 6 | Check that every configured model is available | `uv run python -m app.tools.verify_models` |

> For step 4: in the OpenAI dashboard create a separate Project (e.g. "ai-teaching-studio") with its own restricted
> key and a **monthly budget limit**. Never paste keys into `.env`, any file, chat or screenshots.
> Everything in Phase 1 works **without** an OpenAI key (only Hindi/Marathi answers are better with it).

## 2. Start / stop the app

1. Make sure the **Ollama** app is running (tray icon).
2. Start: `uv run streamlit run ui/Home.py` → the browser opens **http://localhost:8501** (only this laptop can open it).
3. Stop: `Ctrl + C` in the terminal. Unfinished background work resumes automatically next time.

| Page | What it is for |
|---|---|
| Home | Security checks, models, library totals, monthly spend |
| Syllabus Library | Add textbook files, watch processing, edit chapter details |
| Review Text | Compare each page image with its extracted text, correct it, approve it |
| AI Tutor | Questions answered from your approved pages, with page references |
| Settings & Cost | Budget, API keys, model routing, ingestion settings, log of every AI call and its cost |
| Lesson Studio | Create lessons from your textbook, check/edit them, preview simulations, approve |
| Teach Mode | Present an approved lesson full-screen: slides, equations, 3D molecules, simulation, key points |

> **After updating the code, always restart the app** (`Ctrl + C`, then start again). An app left running from
> before an update keeps the old code in memory (this caused two failed lesson jobs once; workers now ignore
> job types they do not know).

---

## 3. Test Phase 1 with your PDF (step by step)

**A. Add the file** (either way works; the same file is never processed twice, even if renamed)
1. Copy the PDF / photos / DOCX into the **`source`** folder of this project, **or**
2. In the app open **Syllabus Library → ➕ Add files**, choose the files, fill *Class / Subject / Chapter*
   (or leave blank — they are guessed from names like *Class 9 - Science - 5th Chapter.pdf*), click **Add & process**.

**B. Wait for extraction** — Syllabus Library shows a progress bar (updates every 3 s).
- Pages with real text are read instantly; scanned pages are OCR'd by the local model, **≈ 15–40 s per page**
  (measured: a 17-page scanned chapter took ≈ 9 minutes, $0). You can keep using other pages of the app meanwhile.
- Status changes to **📝 needs review** when done.

**C. Review the text** — open **Review Text**:
1. Pick the document. Left: the page image. Right: the extracted text — **✏️ Edit** tab to correct it,
   **👁️ Preview** tab to see tables displayed as real tables (the `|` signs are table borders).
2. Fix any mistakes — check **formulas (H₂SO₄), numbers, units and diagram labels** carefully.
   If a table or diagram was read badly, use **☁️ Re-read this page with the cloud model** (section 3b).
   A page marked **⚠️** had OCR trouble (e.g. the model repeated a line; repeats were removed) — compare it
   with the image line by line, or click **Retry this page**.
3. Click **✅ Save & mark reviewed → next** for each page.
   (*Mark ALL reviewed* exists, but use it only after you have actually checked the pages.)

**D. Make it searchable** — click **Make reviewed pages searchable** (Review Text or Syllabus Library).
Status becomes **✅ searchable** after a few seconds.

**E. Ask questions** — open **AI Tutor** → *My textbook*:
1. Optionally filter Class / Subject / Chapter.
2. Ask, e.g. *"What is an ionic bond?"* — the answer cites pages like **[1] Ch. 5, page 2**; open the source
   boxes under the answer to see the exact textbook passages.
3. Ask something **not** in the chapter (e.g. *"Who discovered gravity?"*) — it must reply
   *"This is not covered in the uploaded textbook pages."* (turn on the toggle only if you want a clearly
   marked general answer).
4. Choose **Hindi** or **Marathi** only when a student asks — scientific terms stay in English in brackets.
5. **Answer model:** *Local (free)* is fine for normal questions. For questions about **tables** choose
   *Cloud gpt-5-nano* (≈ $0.001 per answer) — measured: the local model missed a table answer that the cloud
   model got right.
6. **Reuse answers to very similar questions** (on by default): a question that means the same as an earlier
   one is answered instantly from memory, marked ♻️. It never reuses across different chapters/languages, after
   pages change, or when the questions differ by words like *cathode/anode, strong/weak, acid/base*.
   Turn it off for a fresh answer.

**F. Check costs** — Settings & Cost → *Recent AI calls*: local models always show **$0**.

**Same steps without the browser (command line):**
```
uv run python -m app.ingestion scan            # register new files in source/ and extract them
uv run python -m app.ingestion status          # progress of every document
uv run python -m app.ingestion approve 1       # mark all pages of document 1 reviewed (after checking!)
uv run python -m app.ingestion index 1         # make reviewed pages searchable
uv run python -m app.ingestion ask "What is an ionic bond?"
uv run python -m app.ingestion reindex 1       # rebuild search entries (adds page summaries/descriptions)
uv run python -m app.ingestion cloud 1         # cloud re-read of pages with tables (or: --pages 4,5)
uv run python -m app.ingestion clean 1         # apply the latest OCR clean-up to pages you have NOT edited
```

## 3b. Better tables & diagrams (optional, small cost)

The free local OCR reads normal text well, but sometimes misaligns tables or invents details in diagram
descriptions. Measured on your chapter (pages 3, 4, 5, 16):

| Reader | Tables & subscripts | Speed | Cost |
|---|---|---|---|
| Local `qwen3-vl:2b-instruct` | text good; tables sometimes misaligned (auto-repaired for display) | 30–110 s/page | $0 |
| Cloud `gpt-5.4-mini` | all subscripts and tables correct, honest figure lines | 3–4 s/page | ≈ $0.005/page (≈ 8–9 ¢ per chapter) |

- **One page:** Review Text → open the page → **☁️ Re-read this page with the cloud model**.
- **Several pages:** Syllabus Library → *Manage a document* → **☁️ Better tables & diagrams** → *Pages with tables*
  or *All OCR pages* (cost shown before you click).
- Re-read pages **replace the text (including your edits)** and must be **reviewed again**, then made searchable.
- Costs count towards your monthly budget and appear in Settings & Cost.

**Page summaries & descriptions (automatic, free):** when pages are made searchable, the local model also writes a
short summary of each page and a description of each table and figure. These only help **find** the right page —
the tutor always answers from your **original reviewed text** (a generated description once mixed up "acidity" and
"basicity", so it is never shown to the tutor as fact). Pages indexed before this feature: Syllabus Library →
*More…* → **Re-index searchable pages** (free, ~20 s per page).

## 3c. Lessons & simulations (Phase 2) — step by step

**Your 3 pilot lessons are already generated** (from Chapter 5, as drafts): *Neutralization Reaction*,
*Electrolysis of Water*, *Water of Crystallisation* (≈ 2 ¢ each, ≈ 20 s each).

**A. Review a lesson** — **Lesson Studio** → *Open lesson*:
1. **📄 Content** — title, objectives, sections (each shows its textbook pages), key points. Edit anything and click
   **💾 Save changes** (the version number goes up; equations are re-checked).
2. **⚗️ Equations & molecules** — ✅ = balanced in atoms *and* charge (checked by the app, not by the AI);
   ⚠️ = not balanced, with the exact reason. Molecules can be rotated in 3D (drag) and zoomed (scroll).
3. **🧪 Simulation** — try the interactive experiment. Check that what happens matches your textbook
   (e.g. H₂ : O₂ = 2 : 1; blue vitriol turns white on heating). Not right? Type a **Change request**
   (e.g. *"show the pH number bigger"*) and click **Regenerate** (≈ 2–4 ¢).
4. **📚 Textbook sources** — the exact passages the lesson was written from.
5. Click **✅ Approve for Teach Mode**.

**B. Create a new lesson** — Lesson Studio → **➕ New lesson** → choose the chapter → type a topic → **Create lesson**.
It appears in the list within about a minute (plan first, then the simulation).

**C. Present it** — **Teach Mode** → pick the lesson → **Next ▶ / ◀ Previous**. Press **F11** for full screen and
collapse the sidebar. Slides: title & objectives → sections → equations → 3D molecules → simulation → key points.
(To present a draft, switch on *Also show draft lessons* in the sidebar.)

**How the safety checks work:** the AI writes only the simulation's drawing code. Before you see it, the app checks
it (no internet, no storage, no access to the app around it, correct structure) and Node.js checks the syntax; if
anything fails, the problems are sent back to the AI to fix (up to 2 times). The simulation runs in a sealed frame
that is not allowed to connect to the internet. The drawing libraries are stored inside the project and verified by
their fingerprint, so lessons work offline.

---

## 4. Teaching with the app (class day)

**Before class (10 minutes)**
1. Start Ollama and the app (section 2).
2. On **Syllabus Library**, check the chapter you will teach shows **✅ searchable**.
3. On **AI Tutor**, set the Class / Subject / Chapter filter and ask one test question.

**In class**
1. Teach as usual. When a student asks a doubt, type it into **AI Tutor**.
2. Read the answer **and** show the page reference so students open the same page in their book.
3. If a student needs it in Hindi / Marathi, switch the answer language for that question, then back to English.
4. If the answer says *not covered*, the topic is not in the uploaded pages — explain it yourself or add the chapter.

**After class**
- Note questions the tutor answered poorly; check those pages on **Review Text** (the text may need correcting).
- Add the next chapter (section 5) so it is ready for the next class.

## 5. Adding more chapters

- Drop new files into `source/` (or upload them). Opening **Syllabus Library** processes them automatically.
- Re-adding the same file (even renamed) is detected by its content fingerprint and skipped; identical pages and
  identical passages are also stored only once.
- Fix wrong Class/Subject/Chapter on **Syllabus Library → Manage a document → Save details**, then click
  *Index reviewed pages* again.
- A page that failed: open it on **Review Text** → **Retry this page**.

---

## 6. Models and budget

- **Models:** [config/models.yaml](config/models.yaml) maps each task to a model and fallbacks. After editing, click
  **Reload configuration** on *Settings & Cost*.
  - OCR: `qwen3-vl:2b-instruct` (local) · cloud re-read: `gpt-5.4-mini` (only when you click it) ·
    search: `qwen3-embedding:0.6b` (local) · page summaries: `qwen3:4b-instruct` (local) ·
    answers: `qwen3:4b-instruct` (local) or `gpt-5-nano` (cloud switch) · Hindi/Marathi: `gpt-5.4-mini`.
  - Do **not** use plain `qwen3:4b` / `qwen3-vl:4b`: they are "thinking" models (5–15× slower).
- **Budget:** `ATS_MONTHLY_BUDGET_USD` in `.env` (default **$5/month**). At the cap, paid models are skipped and local
  models answer. Premium models are never used without your approval.
- **Ingestion settings** (in `.env`, restart after changing): `ATS_SOURCE_DIR`, `ATS_AUTO_INGEST`,
  `ATS_REQUIRE_REVIEW`, `ATS_OCR_MAX_IMAGE_PX`, `ATS_PDF_TEXT_MIN_WORDS`, `ATS_ENRICH_PAGES` (page summaries),
  `ATS_SEMANTIC_CACHE` / `ATS_SEMANTIC_CACHE_MIN` (reuse answers, default threshold 0.97) — current values are
  shown on *Settings & Cost*, which also has **Forget all reused answers**.

## 7. Security rules (blueprint §14) — always

- ✅ Install with `uv sync --locked` only. ❌ Never `pip install …` into this project.
- ✅ API keys only in Credential Manager. ❌ Never in `.env`, code, `*.key` files, chat or screenshots.
- ✅ LiteLLM pinned to a clean version ≥ 1.83.0 (now **1.102.1**); 1.82.7 / 1.82.8 were malicious.
- ✅ AI calls only to hosts in `allowed_hosts` (`config/models.yaml`).
- ✅ Your textbook files (`source/`) and data (`data/`) stay on this laptop — both are excluded from Git.
- ✅ Vulnerability audit before upgrades and at the end of each phase: `powershell -ExecutionPolicy Bypass -File scripts\audit.ps1`

**Upgrading a package (one at a time):** read its changelog/advisories → move `exclude-newer` in `pyproject.toml` to
*today − 7 days* and change its exact `==` version → `uv lock --upgrade-package <name>` → review `uv.lock` →
`uv sync --locked` → `scripts\audit.ps1` → `uv run pytest`.

## 8. Development

```
uv run pytest            # 160 automated tests (offline, no cost)
uv run ruff check .      # lint
uv run ruff format .     # format
```

```
app/core/       settings, secrets (Credential Manager), logging with key redaction, security checks
app/db/         SQLite tables (documents, pages, passages+vectors, jobs, AI call log, caches) + migrations
app/ingestion/  file types & hashing, extraction (text layer / OCR / cloud re-read), table repair,
                page summaries, chunking, pipeline, CLI
app/rag/        vector store (SQLite + NumPy), textbook-grounded tutor, similar-question answer cache
app/lessons/    lesson planner, equation checker, molecules (RDKit), simulations (checks), viewers
app/jobs/       background worker (resumable job queue)
assets/vendor/  offline p5.js and 3Dmol.js (pinned, SHA-256 verified; see manifest.json)
app/llm/        model router (fallbacks, budget, cache, allow-list) — the only LiteLLM import
config/         models.yaml
ui/             Streamlit app: Home.py + pages/
source/         your textbook files (not in Git)
data/           database and logs (not in Git)
docs/           blueprint (.docx), diagrams, doc generators
```

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| "Ollama is not running" | Start the Ollama app, then refresh |
| A ❌ security check on Home | Read the message; for a LiteLLM version problem run `uv sync --locked` |
| Processing seems stuck | Syllabus Library shows the running job. Closing the app is safe — it resumes later |
| OCR is very slow (> 1 min/page) | Make sure `config/models.yaml` uses `qwen3-vl:2b-instruct`, and close other GPU-heavy apps |
| Tutor says "not covered" for a topic that is in the book | Is the page reviewed **and** searchable? Is the chapter filter right? Is the OCR text of that page correct? For table questions, switch the answer model to *Cloud* |
| A reused (♻️) answer is not what you wanted | Turn off *Reuse answers…* and ask again, or Settings & Cost → *Forget all reused answers* |
| A table looks broken in the Edit tab | Check the **Preview** tab; if it is still wrong, use the cloud re-read for that page |
| A lesson shows ❌ failed | Read the note (e.g. no reviewed pages match the topic); use words from the textbook in the topic, or review/index the chapter first |
| Simulation shows a warning instead of the experiment | It failed the safety/syntax checks after 2 automatic fixes — click **Regenerate**, optionally with a change request |
| A molecule says "not available" | It is not in the local molecule table (`app/lessons/molecules.py`) yet — tell Claude which one to add |
| A lesson job failed with "Unknown job kind" | The app was started before a code update — restart it |
| OpenAI answers are skipped | No key stored, budget reached, or model not available to your key (`verify_models`) |
| First answer is slow (~15 s) | Model loading into GPU memory; later answers are faster |
