// Helper for step 1: returns the boundaries of the top-level statements in
// TypeScript and JavaScript files, using the TypeScript parser itself.
//
// Run it like this:
//   node ts_statements.js <path-to-typescript> <path-to-file-list.json>
//
// The list is an array of absolute paths. The answer is a single JSON line:
//   { "path": { "statements": [[first, last], ...] } }  or  { "error": "text" }

const fs = require("fs");

const typescriptPath = process.argv[2];
const listPath = process.argv[3];

const ts = require(typescriptPath);
const files = JSON.parse(fs.readFileSync(listPath, "utf8"));

function scriptKind(path) {
  const lower = path.toLowerCase();
  if (lower.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (lower.endsWith(".jsx")) return ts.ScriptKind.JSX;
  if (lower.endsWith(".ts")) return ts.ScriptKind.TS;
  return ts.ScriptKind.JS;
}

const answer = {};

for (const file of files) {
  try {
    const text = fs.readFileSync(file, "utf8");
    const source = ts.createSourceFile(
      file,
      text,
      ts.ScriptTarget.Latest,
      true,
      scriptKind(file)
    );
    const statements = [];
    source.statements.forEach(function (statement) {
      // getStart(source) skips comments and blank space before the statement
      const first =
        source.getLineAndCharacterOfPosition(statement.getStart(source)).line + 1;
      const last =
        source.getLineAndCharacterOfPosition(statement.getEnd()).line + 1;
      statements.push([first, last]);
    });
    answer[file] = { statements: statements };
  } catch (error) {
    answer[file] = {
      error: String(error && error.message ? error.message : error),
    };
  }
}

process.stdout.write(JSON.stringify(answer));
