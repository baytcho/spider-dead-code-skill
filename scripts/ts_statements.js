// Helper for step 1: returns the boundaries of the top-level statements in
// TypeScript and JavaScript files, using the TypeScript parser itself.
//
// Run it like this:
//   node ts_statements.js <path-to-typescript> <path-to-file-list.json>
//
// The list is an array of absolute paths. The answer is a single JSON line:
//   { "path": { "statements": [[first, last], ...] } }  or  { "error": "text" }
//
// Every line below carries a comment. Nothing here can halt the analysis: a
// file that cannot be parsed comes back as an error entry, the rest are still
// answered, and the caller puts the failure into the split report.

const fs = require("fs");                          // reads the files from disk

const typescriptPath = process.argv[2];            // where the parser lives
const listPath = process.argv[3];                  // the JSON list of files to split

const ts = require(typescriptPath);                // load the parser
const files = JSON.parse(fs.readFileSync(listPath, "utf8"));  // the file list

function scriptKind(path) {
  const lower = path.toLowerCase();                // compare without case
  if (lower.endsWith(".tsx")) return ts.ScriptKind.TSX;  // TypeScript with markup
  if (lower.endsWith(".jsx")) return ts.ScriptKind.JSX;  // JavaScript with markup
  if (lower.endsWith(".ts")) return ts.ScriptKind.TS;    // plain TypeScript
  return ts.ScriptKind.JS;                               // everything else is JavaScript
}

const answer = {};                                 // one entry per file

for (const file of files) {                        // every file in turn
  try {
    const text = fs.readFileSync(file, "utf8");    // the whole file
    const source = ts.createSourceFile(            // hand it to the parser
      file,                                        // its name, for the messages
      text,                                        // its text
      ts.ScriptTarget.Latest,                      // accept the newest syntax
      true,                                        // keep the positions we need
      scriptKind(file)                             // and the right language
    );
    const statements = [];                         // the boundaries collected here
    source.statements.forEach(function (statement) {   // only the top-level ones
      // getStart(source) skips comments and blank space before the statement
      const first =
        source.getLineAndCharacterOfPosition(statement.getStart(source)).line + 1;  // first line, counted from 1
      const last =
        source.getLineAndCharacterOfPosition(statement.getEnd()).line + 1;          // last line, counted from 1
      statements.push([first, last]);              // one pair per statement
    });
    answer[file] = { statements: statements };     // the file is done
  } catch (error) {                                // a file that will not parse
    answer[file] = {                               // is never dropped in silence
      error: String(error && error.message ? error.message : error),  // the reason travels back
    };
  }
}

process.stdout.write(JSON.stringify(answer));      // one JSON line, read by statements.py
