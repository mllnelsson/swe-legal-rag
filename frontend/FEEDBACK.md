# Feedback from human live testing 2026-08-25

## 1. Banner
The banner titles are a bit stale. I will suggest maybe "Agent" -> "Sökhistorik", "Sökord" is good but "Begrepp" should perhaps be "Referenser"

## 2. Search (no agent) filters
This sidebar is perhaps to big. Again striving for simple first design i am think maybe we should make the sidebar colapsable, i like the idea of all those filters, but now they are thrown at your face, similar to a web shoping page. Also the "Kategories contains SO MUCH", might be best splitting these up? even if its the same in backend frontend could probably make thos cleaner

## 3. Query expension for normal search un reachable from main page
We ashould have this in someway, maybe call it "smart search", or something similar. Carefule not to be confused with agent mode.

## 4. Agent mode should be the only label on toggle
Right now you alternate between "Sök" and "Agent". I would like a toggle just for agent (just a frontedn change). Also make this toggle more visual popping so itsa easy to find. Sök is still the default

## 5. Watch files constatnly triggering
I get alert in the backend about files changing, its probably due to the LLM trace

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
