# Security

## What SPIDER promises about the analysed project

- **The project is only read.** Nothing in it is modified, executed or built.
- **No code of the analysed project is ever loaded or run.** The TypeScript
  parser is taken exclusively from the skill's own directory; a missing parser
  is a refusal with instructions, never a fallback to the project's
  `node_modules`.
- **Paths are contained.** The source list refuses absolute paths and paths
  that climb out with `..`; the copy step verifies with resolved real paths
  that every origin lies inside the project and every target inside the
  analysis directory.
- **The analysis is bound to a snapshot.** The copy step writes a manifest
  with a checksum of every file; the final list refuses a snapshot that
  changed, and names every live file that drifted.

## What SPIDER does not promise

- It does not prove code dead. Its result is a list of candidates for a human
  check in the live code, and the skill's own documents forbid presenting it
  as a deletion list.
- Step 4 runs Joern, a third-party tool, over the snapshot. Joern parses the
  code; it does not execute it. Install Joern from its official releases and
  verify the checksum of the download.

## Reporting

Open an issue in the repository. Include the smallest project that reproduces
the problem and the exact commands run. Do not include code you may not
publish.
