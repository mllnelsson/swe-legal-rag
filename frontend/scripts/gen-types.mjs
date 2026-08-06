/* Regenerate src/api/schema.d.ts from the API's OpenAPI schema.
 *
 * The schema is built by importing the FastAPI app rather than by calling a
 * running server: `app.openapi()` needs no database, no API keys and no uvicorn,
 * so this works in CI and on a laptop with nothing started. Everything the client
 * sends and receives is typed off the result, which makes a backend contract
 * change a TypeScript error rather than a runtime surprise.
 *
 * Run `npm run gen:types`. The output is committed; regenerating it should be a
 * no-op unless the API actually changed.
 */

import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendDir, "..");
const schemaPath = resolve(frontendDir, "src/api/schema.d.ts");

const EXPORT_SCHEMA = `
import json
from api.main import app
print(json.dumps(app.openapi()))
`;

const openapi = execFileSync("uv", ["run", "python", "-c", EXPORT_SCHEMA], {
  cwd: repoRoot,
  encoding: "utf8",
  maxBuffer: 32 * 1024 * 1024,
});

const schema = JSON.parse(openapi);
writeFileSync(schemaPath, astToString(await openapiTS(schema)));

const { paths } = schema;
process.stdout.write(`wrote src/api/schema.d.ts (${Object.keys(paths).length} paths)\n`);
