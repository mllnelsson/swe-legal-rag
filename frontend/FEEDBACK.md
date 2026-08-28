# Feedback from human live testing 2026-08-25

## 1. Banner ✅ Resolved
The banner titles are a bit stale. I will suggest maybe "Agent" -> "Sökhistorik", "Sökord" is good but "Begrepp" should perhaps be "Referenser"

**Resolution:** "Begrepp" → "Referenser". "Sökord" kept. "Agent" left as-is
rather than "Sökhistorik": the link opens the agent chat, and there is no
search-history view to point that label at — renaming it would mislabel where it
goes. (`AppShell.tsx`.)

## 2. Search (no agent) filters ✅ Resolved
This sidebar is perhaps to big. Again striving for simple first design i am think maybe we should make the sidebar colapsable, i like the idea of all those filters, but now they are thrown at your face, similar to a web shoping page. Also the "Kategories contains SO MUCH", might be best splitting these up? even if its the same in backend frontend could probably make thos cleaner

**Resolution:**
- The rail is gone as an always-open column. The results page is now one column,
  and every filter lives behind a **"Filter" disclosure that is collapsed by
  default** and sits above the results — the page opens on what came back, not on
  a wall of controls. The disclosure carries a count badge so a collapsed rail
  still says how many filters are in force; active filters also stay visible as
  removable tags in the results column. (`FacetRail.tsx`, `ResultsPage.tsx`.)
- **Kategori** is no longer one long dropdown but a **searchable typeahead**
  (type to filter) — cleaner for a long free-text list, and the value it sends
  stays byte-identical, so nothing the corpus never merged is merged here.
  (`Combobox.tsx`.)

## 3. Query expension for normal search un reachable from main page ✅ Resolved
We ashould have this in someway, maybe call it "smart search", or something similar. Carefule not to be confused with agent mode.

**Resolution:** Query expansion is now reachable from the home page as a **"Smart
sökning" switch**, shown only in search mode (hidden when Agentläge is on, since
expansion is search-only) and visually secondary to the mode toggle so it is not
confused with agent mode. It still round-trips as `utoka=1` and can be toggled
after the fact from the results rail. (`SearchHomePage.tsx`.)

## 4. Agent mode should be the only label on toggle ✅ Resolved
Right now you alternate between "Sök" and "Agent". I would like a toggle just for agent (just a frontedn change). Also make this toggle more visual popping so itsa easy to find. Sök is still the default

**Resolution:** The mode control is an agent-only switch labelled "Agentläge",
now rendered at a new prominent **`lg` size** so it is easy to find. Sök stays the
default (the switch is off on load). The submit button still reads Sök / Fråga per
mode — that is the action label, not the toggle. (`Switch.tsx`, `SearchHomePage.tsx`.)

## 5. Watch files constatnly triggering ✅ Resolved
I get alert in the backend about files changing, its probably due to the LLM trace

**Resolution:** Confirmed — the dev server ran a bare `uvicorn … --reload` from
the repo root, so it watched `./data/llm-traces/`, where a trace JSON is written on
every LLM call. The documented dev command now scopes the watcher to source with
**`--reload-dir packages`**, so trace writes no longer trigger reloads while edits
under `packages/` still do. (Docs: local-dev, frontend/overview, live-testing.)

## 6. Chat behaviour ✅ Resolved
Long description about the behaviour and experience of the chat.

**Resolution:**
- *Presentation* — SQL lineage now sits behind a one-click "Så räknades siffrorna
  fram" disclosure instead of a table dumped over the answer; references moved to
  a slide-in side panel reached from a discreet "N källor" button. (Honesty rules
  14 and 22 reframed from *shown* to *reachable*; docs updated.)
- *Perceived speed* — the false "~1 minute" ceiling copy is gone; a turn-level
  reassurance after 30s and a per-step "tar en stund…" hint after 8s keep the
  wait legible.
- *Real latency* — the chat agent is now three phases: a strong-model (GLM) plan
  step that either answers a chatty turn directly or hands a plan to a smaller
  model (gpt-oss-120b) that runs the tool loop, then GLM writes the answer. The
  trace framework confirmed the win: the counting turn dropped from ~124s to ~55s
  (executor iterations fell from ~35–40s on GLM to ~2–5s), and a chatty follow-up
  short-circuits in a single call. Follow-up: tune the CHAT_PLAN prompt across
  more question shapes against live GLM.

Firstly it feels slow. I think we need to improve the feedback so it doesnt feel so tideous.


I asked the following question:
"Hur många beslut avslog nämned 2022"

I can observe session=508f1ee2-5cc8-404e-8f01-fac99651b5fe from logs and interaction=14140e81-0a73-478c-8cce-58fb67ae8ef.Then i got the minimal feedback until BAM, SQL queries ofver the screen. I think these should not be expanded, th overwhelm a non tecnical users. The none technical users does not want the linage up front. it is better to semi hide this, until user wants to verify. Then an answer started streaming, all in all 124 seconds

Then i askeed a trickier followup:
"vad handlade dessa avslag generellt om?"

Now it ran its tool loop for 231 seconds and then BAM a bunch of references. Againb its really great wirth the possible details of the sources, but i feel like they should be more discrete by default, and maybe even put on the side or something, its really good with showing the context and optional more info (again my design principle with the option to "drill down" applies here). Then the answer is streamed finally
These are for the following IDs
interaction=64578341-dc18-485a-bf44-6d12a63d3f58
session=508f1ee2-5cc8-404e-8f01-fac99651b5fe
