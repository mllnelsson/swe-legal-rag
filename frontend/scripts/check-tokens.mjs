/* Design-token adherence check.
 *
 * The design skill ships these as ESLint `no-restricted-syntax` selectors, which
 * oxlint does not implement. Only three of its 33 rules are worth keeping: the
 * other 30 assert component prop names and variant literals, and TypeScript
 * enforces those far better than an AST selector can, now that the components are
 * typed .tsx rather than the skill's untyped .jsx.
 *
 * What survives is the part a type system cannot express: no raw colour, no raw
 * spacing, no font outside the three the system ships. Everything visual has to
 * come through a var() token, so the token layer stays the single source of truth.
 */

import { globSync, readFileSync } from "node:fs";
import { relative } from "node:path";

const SYSTEM_FONTS = ["Newsreader", "Public Sans", "IBM Plex Mono"];

/** Blank out border and outline widths before scanning for raw px.
 *
 *  The design system has no border-width token and never claimed one: hairlines
 *  are 1px, quoted matter carries a 2px apricot rule, the ember accent is a 2-4px
 *  rule. Every component in the skill is written that way, so a rule that flagged
 *  them would fire on the whole design system and teach everyone to ignore it. */
function stripBorderWidths(line) {
  return line.replace(
    /\b(border|outline)[A-Za-z]*\s*:\s*(`[^`]*`|"[^"]*"|'[^']*'|[^,;}\n]*)/g,
    (match) => " ".repeat(match.length),
  );
}

/** An explicit, greppable escape for a value the token layer genuinely lacks.
 *  Requires a reason so the exception stays reviewable rather than habitual. */
const EXEMPTION = /token-exempt:\s*\S/;

// Two things the skill's version of this rule gets wrong, both of which made it
// silently useless rather than noisy:
//
//   1. It spells the property `font-family`, which only matches CSS text. The
//      components style with JSX inline objects, where the key is `fontFamily`.
//   2. It ends `...\s*(?!allowed)`, and the trailing `\s*` backtracks to
//      zero-width, so the negative lookahead gets retried against the whitespace
//      itself and trivially succeeds. Every declaration matched, valid or not.
//
// Capturing the value and comparing it is both correct and legible.
const FONT_DECLARATION = /font-?family\s*:\s*(['"]?)([^;,'"}\n]+)/i;

const RULES = [
  {
    name: "raw-hex-color",
    message: "Raw hex color — use a design-system color token via var().",
    fires: (line) => /#[0-9a-fA-F]{3,8}\b/.test(line),
  },
  {
    name: "raw-px-value",
    message:
      "Raw px value — use a design-system spacing token via var(), or mark the line " +
      "`token-exempt: <reason>` if the system has no token for it.",
    fires: (line) => /\b[\d.]+px\b/.test(stripBorderWidths(line)),
  },
  {
    name: "non-system-font",
    message: `Font not provided by the design system. Available: ${SYSTEM_FONTS.join(", ")}.`,
    fires: (line) => {
      const declaration = FONT_DECLARATION.exec(line);
      if (declaration === null) return false;
      // The value may be an expression rather than a literal — a ternary picking
      // between two tokens is ordinary code. Anything reaching a font token on this
      // line is using the system, whatever shape the expression takes; a hardcoded
      // family name still has no var(--font-…) anywhere and still fires.
      if (line.includes("var(--font-")) return false;
      const value = declaration[2].trim();
      return !SYSTEM_FONTS.some((font) => value.toLowerCase().startsWith(font.toLowerCase()));
    },
  },
];

// The token layer is where literal values are *supposed* to live, and the
// vendored Lucide geometry is path data rather than styling.
const EXEMPT = [/^src\/styles\//, /^src\/components\/display\/icon-paths\.ts$/];

const COMMENT_LINE = /^\s*(\/\/|\/\*|\*)/;

/** True when the line carries an exemption, or the comment block directly above
 *  it does. Scanning the whole block means the reason can be a sentence on its own
 *  line, or part of a JSDoc comment, rather than having to fit beside the value. */
function isExempt(rawLines, index) {
  if (EXEMPTION.test(rawLines[index] ?? "")) return true;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const line = rawLines[cursor] ?? "";
    if (!COMMENT_LINE.test(line)) return false;
    if (EXEMPTION.test(line)) return true;
  }
  return false;
}

/** Blank out comments and import specifiers so they cannot trip the patterns. */
function stripNonCode(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
    .replace(/\/\/[^\n]*/g, (match) => " ".repeat(match.length))
    .replace(/^\s*import\s[^;]*;/gm, (match) => " ".repeat(match.length));
}

const files = globSync("src/**/*.{ts,tsx}").filter(
  (file) => !EXEMPT.some((exempt) => exempt.test(file)),
);

const violations = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  // Exemptions are read from the raw text because they live in comments, which
  // the code-only view below deliberately blanks out.
  const rawLines = source.split("\n");
  const lines = stripNonCode(source).split("\n");
  lines.forEach((line, index) => {
    if (isExempt(rawLines, index)) return;
    for (const rule of RULES) {
      if (rule.fires(line)) {
        violations.push({
          location: `${relative(".", file)}:${index + 1}`,
          rule: rule.name,
          message: rule.message,
          source: line.trim().slice(0, 90),
        });
      }
    }
  });
}

if (violations.length > 0) {
  for (const violation of violations) {
    process.stderr.write(
      `${violation.location}  ${violation.rule}\n  ${violation.message}\n  ${violation.source}\n\n`,
    );
  }
  process.stderr.write(`${violations.length} token-adherence violation(s)\n`);
  process.exit(1);
}

process.stdout.write(`token adherence clean (${files.length} files)\n`);
