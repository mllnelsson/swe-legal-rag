# Workspace UI kit

The research app. Four views, click-through:

1. **SearchHome** — apricot-wash empty state, signature `SearchField`, suggested questions, recent searches.
2. **ResultsView** — `AnswerPanel` with numbered sources, authority tabs, applied-filter tags, `CitationCard` list, filter rail.
3. **DocumentView** — case reader with the held paragraph highlighted, "why this matched" and citing-references rails.
4. **MatterView** — saved authorities, coverage summary, gap check, export dialog.

`AppShell.jsx` owns navigation, save state, toasts and the export dialog. `data.js` holds the fictional matter (Novak v. Harrow Logistics) — invented content, not real case law. Screens compose the published components; nothing is re-implemented locally.
