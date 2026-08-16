"""SPIDER - step 1: build the statement list.

Two commands:

    statements.py copy  --project <project> --analysis <analysis directory>
        Copies into the analysis directory every file the intelligence listed in
        source-files.txt, keeping the same names and the same folder layout.
        The project is only read, never modified.

    statements.py split --analysis <analysis directory> [--project <project>]
        Splits every copied file into top-level statements and writes
        statements.txt.

One line of statements.txt looks like this:

    id | file | first-last | text

The text comes last. A statement that spans many lines in its own file is
written on a single line here; its address points at the exact place in the
copied file.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SOURCE_FILES = "source-files.txt"
STATEMENTS = "statements.txt"
SPLIT_REPORT = "split-report.json"
SOURCE_DIR = "source"

TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
PY_EXTENSIONS = (".py",)
CSS_EXTENSIONS = (".css",)

SEPARATOR = " | "


# --------------------------------------------------------------------------
# Copying
# --------------------------------------------------------------------------

def read_source_list(analysis):
    path = os.path.join(analysis, SOURCE_FILES)
    if not os.path.exists(path):
        raise SystemExit(
            "No list of application source files: " + path + "\n"
            "The intelligence must write it before copying."
        )
    with open(path, "r", encoding="utf-8") as fh:
        lines = [line.strip().replace("\\", "/") for line in fh]
    return [line for line in lines if line and not line.startswith("#")]


def copy_sources(project, analysis):
    project = os.path.abspath(project)
    analysis = os.path.abspath(analysis)
    listed = read_source_list(analysis)

    copied, missing = [], []
    for relative in listed:
        origin = os.path.join(project, relative.replace("/", os.sep))
        if not os.path.isfile(origin):
            missing.append(relative)
            continue
        target = os.path.join(analysis, SOURCE_DIR, relative.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(origin, target)
        copied.append(relative)

    print("Listed files:   " + str(len(listed)))
    print("Copied files:   " + str(len(copied)))
    print("Missing files:  " + str(len(missing)))
    for name in missing:
        print("   missing: " + name)
    return 1 if missing else 0


# --------------------------------------------------------------------------
# Splitting: Python
# --------------------------------------------------------------------------

def python_statements(text):
    tree = ast.parse(text)
    spans = []
    for node in tree.body:
        first = node.lineno
        for decorator in getattr(node, "decorator_list", []) or []:
            first = min(first, decorator.lineno)
        spans.append((first, node.end_lineno))
    return spans


# --------------------------------------------------------------------------
# Splitting: CSS
# --------------------------------------------------------------------------

def css_statements(text):
    """A top-level CSS statement is a rule at depth zero or an at-rule."""
    spans = []
    i, size = 0, len(text)
    line = 1
    first_line = None
    depth = 0
    has_content = False
    in_string = None

    while i < size:
        char = text[i]

        if char == "\n":
            line += 1
            i += 1
            continue

        if in_string:
            if char == "\\":
                i += 2
                continue
            if char == in_string:
                in_string = None
            i += 1
            continue

        if char in "\"'":
            in_string = char
            if not has_content:
                first_line, has_content = line, True
            i += 1
            continue

        if char == "/" and i + 1 < size and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                end = size
            line += text.count("\n", i, end)
            i = end + 2
            continue

        if not char.strip():
            i += 1
            continue

        if not has_content:
            first_line, has_content = line, True

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth <= 0:
                depth = 0
                spans.append((first_line, line))
                has_content = False
        elif char == ";" and depth == 0:
            spans.append((first_line, line))
            has_content = False

        i += 1

    return spans


# --------------------------------------------------------------------------
# Splitting: TypeScript / JavaScript
# --------------------------------------------------------------------------

def find_typescript(skill_dir, project_root):
    candidates = []
    current = skill_dir
    while True:
        candidates.append(os.path.join(current, "node_modules", "typescript"))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    if project_root and os.path.isdir(project_root):
        candidates.append(os.path.join(project_root, "node_modules", "typescript"))
        try:
            for name in sorted(os.listdir(project_root)):
                candidates.append(
                    os.path.join(project_root, name, "node_modules", "typescript")
                )
        except OSError:
            pass
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "package.json")):
            return candidate.replace("\\", "/")
    return None


def typescript_statements(files, typescript_path, helper):
    if not files:
        return {}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as handle:
        json.dump([f.replace("\\", "/") for f in files], handle)
        list_path = handle.name
    try:
        result = subprocess.run(
            ["node", helper, typescript_path, list_path],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            raise SystemExit(
                "The TypeScript parser did not answer:\n" + (result.stderr or "")
            )
        return json.loads(result.stdout)
    finally:
        os.unlink(list_path)


# --------------------------------------------------------------------------
# Splitting: common
# --------------------------------------------------------------------------

def join_lines(lines, first, last):
    chunk = "\n".join(lines[first - 1:last])
    return re.sub(r"\s+", " ", chunk).strip()


def split_sources(analysis, project=None):
    analysis = os.path.abspath(analysis)
    root = os.path.join(analysis, SOURCE_DIR)
    if not os.path.isdir(root):
        raise SystemExit("No copied source: " + root)

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    helper = os.path.join(skill_dir, "scripts", "ts_statements.js")

    all_files = []
    for base, folders, names in os.walk(root):
        folders.sort()
        for name in sorted(names):
            all_files.append(os.path.join(base, name))

    ts_files = [f for f in all_files if f.lower().endswith(TS_EXTENSIONS)]
    ts_result = {}
    if ts_files:
        typescript_path = find_typescript(skill_dir, project)
        if not typescript_path:
            raise SystemExit(
                "The TypeScript parser is missing.\n"
                "Run inside the skill directory: npm install typescript@5"
            )
        ts_result = typescript_statements(ts_files, typescript_path, helper)

    output_lines = []
    not_split = []
    by_extension = {}
    number = 0

    for path in all_files:
        relative = os.path.relpath(path, root).replace("\\", "/")
        extension = os.path.splitext(path)[1].lower()
        try:
            with open(path, "r", encoding="utf-8", errors="strict") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as error:
            not_split.append({"file": relative, "reason": "cannot read: " + str(error)})
            continue

        lines = text.split("\n")

        try:
            if extension in PY_EXTENSIONS:
                spans = python_statements(text)
            elif extension in CSS_EXTENSIONS:
                spans = css_statements(text)
            elif extension in TS_EXTENSIONS:
                answer = ts_result.get(path.replace("\\", "/"), {})
                if "error" in answer:
                    raise ValueError(answer["error"])
                spans = [tuple(span) for span in answer.get("statements", [])]
            else:
                not_split.append({
                    "file": relative,
                    "reason": "no parser for extension " + (extension or "(none)"),
                })
                continue
        except (SyntaxError, ValueError) as error:
            not_split.append({"file": relative, "reason": "cannot split: " + str(error)})
            continue

        by_extension[extension] = by_extension.get(extension, 0) + len(spans)
        for first, last in spans:
            text_of_statement = join_lines(lines, first, last)
            if not text_of_statement:
                continue
            number += 1
            output_lines.append(
                str(number) + SEPARATOR + relative + SEPARATOR
                + str(first) + "-" + str(last) + SEPARATOR + text_of_statement
            )

    statements_path = os.path.join(analysis, STATEMENTS)
    with open(statements_path, "w", encoding="utf-8", newline="\n") as fh:
        for line in output_lines:
            fh.write(line + "\n")

    report = {
        "files_in_analysis_directory": len(all_files),
        "files_split": len(all_files) - len(not_split),
        "statements": number,
        "statements_by_extension": by_extension,
        "files_not_split": not_split,
    }
    with open(os.path.join(analysis, SPLIT_REPORT), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print("Files in the analysis directory: "
          + str(report["files_in_analysis_directory"]))
    print("Files split:                     " + str(report["files_split"]))
    print("Top-level statements:            " + str(report["statements"]))
    for extension in sorted(by_extension):
        print("   " + extension + ": " + str(by_extension[extension]))
    if not_split:
        print("Files not split:                 " + str(len(not_split)))
        for item in not_split[:20]:
            print("   " + item["file"] + " - " + item["reason"])
    print("Statement list: " + statements_path)
    return 0


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="statements.py",
                                     description="SPIDER - step 1")
    commands = parser.add_subparsers(dest="command", required=True)

    copy_command = commands.add_parser("copy")
    copy_command.add_argument("--project", required=True)
    copy_command.add_argument("--analysis", required=True)

    split_command = commands.add_parser("split")
    split_command.add_argument("--analysis", required=True)
    split_command.add_argument("--project", required=False, default=None)

    arguments = parser.parse_args()
    if arguments.command == "copy":
        return copy_sources(arguments.project, arguments.analysis)
    return split_sources(arguments.analysis, arguments.project)


if __name__ == "__main__":
    sys.exit(main())
