# Svk Beslutsök Design System

Svk Beslutsök is a legal-research assistant: you ask a question in plain language or paste a citation, and it answers with the cases, statutes and secondary sources the answer rests on. The audience is a working litigation team — associates, paralegals, partners — not engineers. The system is designed to feel like well-made office stationery: warm paper, an editorial serif, a burgundy that reads as authority rather than alarm.

## Sources

**No sources were provided for this build.** No codebase, Figma file, deck, brand guidelines, logo or font binaries were attached — the design system was authored from the written brief:

> "legal-researcher assistant. It's a search tool for legal references… professional, office-worker friendly, it can't look too techy. The colour scheme should be white and apricoty, but I'd like a gradient. Also burgundy red."

Everything below is a proposal built from that brief. Two consequences to be aware of:

- **The name is "Svk Beslutsök".** It is used in the wordmark, the UI kits and the namespace (`SvkBeslutsokDesignSystem_46c55d`). Renaming again is a find-and-replace plus this readme.
- **There is no logo.** None was supplied and none was invented. Wherever a mark would go, the brand name is set in the display serif (see `guidelines/wordmark.card.html`).

## Substitutions to confirm

| Thing | What shipped | Why |
| --- | --- | --- |
| Display serif | **Newsreader** (Google Fonts) | No font files supplied. Warm, editorial, low-contrast — reads as a law review, not a startup. |
| UI sans | **Public Sans** (Google Fonts) | Neutral, faintly civic, wide apertures at 13–15px. Deliberately not Inter. |
| Citation mono | **IBM Plex Mono** (Google Fonts) | Reporter cites need a monospace with a real section sign and comfortable digits. |
| Icons | **Lucide** (`lucide-static` via unpkg, CSS-masked) | No icon set supplied. 2px round-cap stroke, matches the type weight. |

Fonts load from the Google Fonts CDN in `tokens/fonts.css`. **Send licensed binaries and I will self-host them and rewrite the `@font-face` rules.**

---

## Content fundamentals

The voice is a careful colleague who has already done the reading. Plain, specific, unhurried. It never oversells, because the user's professional exposure is real.

- **Person.** Speak to the user as *you*; the product is *Svk Beslutsök*, never *we* inside the app. Marketing may use *we* sparingly.
- **Casing.** Sentence case everywhere — buttons, headings, nav, table headers. All-caps is reserved for the 11px overline label. Title Case never appears except in case names and proper nouns.
- **Punctuation.** Full stops in body copy and hints; none on button labels, badges or single-line empty states. Em dashes sparingly; the middle dot `·` is the house separator in metadata lines.
- **Numbers and citations.** Citations are verbatim and never reformatted for looks: `812 F.3d 1044 (9th Cir. 2016)`, `49 U.S.C. § 14706(a)(1)`. Counts are digits (`48 results`).
- **Emoji.** Never. Not in the product, not in marketing, not in error states.
- **Hedging is a feature.** Where authority is split, say so: "The Sixth Circuit takes the narrower view." Never state a legal conclusion the sources don't carry.
- **Length.** Buttons 1–3 words. Hints under 10 words. Body paragraphs under 60 words, capped at 68 characters per line.

Examples, in the house voice:

| Situation | Copy |
| --- | --- |
| Search placeholder | `Ask a research question, or paste a citation` |
| Empty results | `Nothing matched in the 9th Circuit. Widen the jurisdiction or drop a filter.` |
| Save confirmation | `Saved to Novak v. Harrow` / `3 authorities added.` |
| Warning | `One authority was criticized. Review before citing.` |
| Marketing headline | `Legal research that cites itself` |
| Marketing subhead | `Ask a question the way you would ask a colleague.` |
| Disclaimer, footer | `Not a substitute for professional judgment.` |

Avoid: "AI-powered", "supercharge", "instantly", "revolutionize", "just", "simply", "magic", exclamation marks.

---

## Visual foundations

**Palette.** White and warm off-white carry the page; apricot carries warmth and every highlight; burgundy carries authority and is the only strong colour on a default screen. Ratio in practice is roughly 80% paper / 15% apricot / 5% burgundy. Neutrals are warm — every grey has red in it (`--warm-500: #7d7169`), so nothing on screen reads blue-cold. Status colours are muted and desaturated; the green and amber are closer to ink stamps than to notification badges.

**Gradients.** The apricot wash is the brand's signature and it appears in exactly three places: the marketing hero, the empty search screen, and the `AnswerPanel`. It is always soft, always warm, and never travels more than about 12% away from white at its light end (`--gradient-wash`, `#fff8f2 → #fad7bd`). The burgundy `--gradient-authority` is reserved for inverse panels and the marketing quote block. `--gradient-ember` only ever appears as a 2–4px rule. No gradient ever sits behind body text at full strength, and there are no purple or blue gradients anywhere in the system.

**Type.** Newsreader for anything a person reads as a statement — headlines, case names, restated questions, section titles down to 19px. Public Sans for everything the interface says — labels, buttons, body, metadata. IBM Plex Mono only for citations, docket numbers and statute sections; it is a signal that a string is legally exact, so never use it decoratively. Display sizes carry −0.02em tracking; body is untracked. Prose is capped at 68 characters.

**Spacing and layout.** 4px base, with 2px and 12px kept as real steps. Cards pad 24px, stack at 16px, group tightly at 8px. Marketing sections are 80–112px apart. Two fixed dimensions: the 264px workspace sidebar and the 1180px content maximum. The app header is sticky at 56px; the marketing header is sticky at 68px with an 8px backdrop blur over 82% white — the only blur in the system.

**Backgrounds.** No photography, no illustration, no texture, no pattern. The background range runs paper → warm-25 → warm-50, plus the apricot wash. If imagery is added later it should be warm-toned, grain-free and documentary; nothing stock-lit or blue.

**Cards.** White, 12px radius, 1px `--border-hairline`, `--shadow-sm`. On hover, interactive cards raise to `--shadow-md` and the border warms to `--apricot-300`. Cards never carry a coloured left border. Quoted matter — held passages, excerpts — is marked with a 2px apricot rule on the left and no box.

**Radii.** 5px controls, 8px medium containers, 12px cards, 18px the search field, full pill for tags and chips. Nothing is fully square except rules and dividers.

**Shadows.** Warm-tinted (`rgba(66,59,55,…)`) and low-contrast, in five steps: `xs` on controls, `sm` cards at rest, `md` hover and toasts, `lg` popovers, `overlay` for modals. There are no inner shadows in the system except the 1px hairline inset used under sticky headers.

**Interaction.** Hover warms the surface (a tint step, never a scale). Press sinks the element 0.5px and drops its shadow — nothing scales, nothing bounces. Focus is a 3px apricot ring (`--ring-focus`) plus a border colour change; it is never removed and never blue. Disabled is 42% opacity with the cursor set to `not-allowed`.

**Motion.** Short and flat: 80ms press, 140ms hover and focus, 200ms toggles, 320ms toasts, 420ms panels, all on `cubic-bezier(0.2, 0, 0.2, 1)`. Fades and small position shifts only. No spring, no overshoot, no attention-seeking loops. A streaming answer may show a static "Searching…" overline rather than a spinner.

**Transparency and blur.** Two uses only: the sticky marketing header (82% white + 8px blur) and the modal scrim (`rgba(42,37,35,0.42)` + 2px blur). Chips inside the wash use `rgba(255,255,255,0.72)` so the gradient reads through. Everything else is opaque.

---

## Iconography

- **Set:** [Lucide](https://lucide.dev), loaded per-glyph from `lucide-static` on unpkg and painted with a CSS mask so icons inherit `currentColor`. This is a **substitution** — no icon set was supplied. Swap the CDN base in `components/display/Icon.jsx` for a local sprite when the real set arrives.
- **Weight and size:** 2px stroke, round caps. 13px inside chips and badges, 15–16px in dense rows and small buttons, 17–19px in toolbars and feature blocks. Never above 20px in the app.
- **Colour:** icons are monochrome and take the colour of the text beside them — `--text-muted` at rest, `--burgundy-600` when they are the brand-carrying element.
- **House set:** `search`, `scale`, `book-open`, `gavel`, `file-text`, `bookmark`, `bookmark-check`, `quote`, `filter`, `folder`, `history`, `link-2`, `download`, `sparkles`, `plus`, `check`, `x`, `chevron-down`, `arrow-right`, `arrow-left`, `triangle-alert`, `circle-alert`, `info`, `circle-help`, `play`.
- **Never:** emoji, unicode dingbats as icons, filled/duotone glyphs, two icon sets in one view, or hand-drawn SVG. The middle dot `·` is used as a separator, which is typography, not iconography.
- **`assets/`** is currently empty of marks by design: no logo was supplied, so none was drawn.

---

## Intentional additions

The brief defined no component inventory, so the standard set was authored. Three additions are product-specific and are the reason the system is not generic:

- **`SearchField`** — the signature question box; the product's one hero control.
- **`CitationCard`** — the result unit: case name, mono citation line, authority badge, held passage on an apricot rule.
- **`AnswerPanel`** — the synthesized answer on the apricot wash, with numbered source chips. Never render it without sources.

`Icon` is a thin wrapper over Lucide so no view hand-rolls SVG.

---

## Index

| Path | What's there |
| --- | --- |
| `styles.css` | Entry point. `@import`s only — link this one file. |
| `tokens/` | `fonts`, `colors`, `typography`, `spacing`, `radii`, `elevation`, `motion`, `gradients`, `base`. |
| `guidelines/` | 20 specimen cards: colour ramps, gradients, type ladder, spacing, radii, elevation, borders, motion, states, wordmark. |
| `components/actions/` | `Button`, `IconButton` |
| `components/forms/` | `SearchField`, `Input`, `Select`, `Checkbox`, `Radio`, `Switch` |
| `components/display/` | `Card`, `Badge`, `Tag`, `Icon` |
| `components/navigation/` | `Tabs`, `SidebarNav` |
| `components/feedback/` | `Dialog`, `Toast`, `Tooltip` |
| `components/research/` | `CitationCard`, `AnswerPanel` |
| `ui_kits/workspace/` | The research app: search home → results → document reader → matter, click-through. |
| `ui_kits/website/` | Marketing home: header, hero with live answer preview, features, how-it-works, quote, footer. |
| `SKILL.md` | Agent-Skills wrapper so this folder works inside Claude Code. |

Each component directory also holds `<Name>.d.ts` (props contract) and `<Name>.prompt.md` (one-line what & when, plus a usage example).
