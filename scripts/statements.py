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

Every line below carries a comment. Nothing here can halt the analysis: a file
that cannot be read or split is written into the split report with its reason
and the work goes on. Only two things stop this program, and both of them are
missing input, named exactly: no list of source files, and no TypeScript parser
when the project holds TypeScript.
"""

import argparse                                   # reads the command line
import ast                                        # the Python parser
import json                                       # the file list and the report
import os                                         # paths, walking, checks
import re                                         # squeezes whitespace
import shutil                                     # copies files
import subprocess                                 # runs the TypeScript helper
import sys                                        # exit code and stdout
import tempfile                                   # the temporary file list

if hasattr(sys.stdout, "reconfigure"):            # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")      # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")      # a project with non-Latin text must not break it

SOURCE_FILES = "source-files.txt"                 # written by the intelligence
STATEMENTS = "statements.txt"                     # the result of this step
SPLIT_REPORT = "split-report.json"                # the numbers of this step
SOURCE_DIR = "source"                             # where the copy lives

TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")  # the TypeScript parser
PY_EXTENSIONS = (".py",)                                        # the Python parser
CSS_EXTENSIONS = (".css",)                                      # the splitter below

SEPARATOR = " | "                                 # between the four columns of a line


# --------------------------------------------------------------------------
# Copying
# --------------------------------------------------------------------------

def read_source_list(analysis):
    """Reads the list of application source files the intelligence wrote."""
    path = os.path.join(analysis, SOURCE_FILES)            # it lives in the analysis directory
    if not os.path.exists(path):                           # without it there is nothing to copy
        raise SystemExit(
            "No list of application source files: " + path + "\n"
            "The intelligence must write it before copying."
        )
    with open(path, "r", encoding="utf-8") as fh:          # the list is UTF-8
        lines = [line.strip().replace("\\", "/") for line in fh]  # one path per line, forward slashes
    return [line for line in lines if line and not line.startswith("#")]  # blanks and notes drop out


def copy_sources(project, analysis):
    """Copies the listed files into the analysis directory."""
    project = os.path.abspath(project)                     # full paths only
    analysis = os.path.abspath(analysis)                   # for both sides
    listed = read_source_list(analysis)                    # what to copy

    copied, missing = [], []                               # counted for the report
    for relative in listed:                                # every listed path
        origin = os.path.join(project, relative.replace("/", os.sep))  # where it is
        if not os.path.isfile(origin):                     # a path that names nothing
            missing.append(relative)                       # is reported, not guessed at
            continue                                       # and the rest go on
        target = os.path.join(analysis, SOURCE_DIR, relative.replace("/", os.sep))  # where it goes
        os.makedirs(os.path.dirname(target), exist_ok=True)  # keep the folder layout
        shutil.copy2(origin, target)                       # copy with the timestamps
        copied.append(relative)                            # one more done

    print("Listed files:   " + str(len(listed)))           # from the list
    print("Copied files:   " + str(len(copied)))           # from the copying
    print("Missing files:  " + str(len(missing)))          # must be zero
    for name in missing:                                   # and if not
        print("   missing: " + name)                       # each one is named
    return 1 if missing else 0                             # a non-zero code marks the trouble


# --------------------------------------------------------------------------
# Splitting: Python
# --------------------------------------------------------------------------

def python_statements(text):
    """The top-level statements of a Python file, from the Python parser."""
    tree = ast.parse(text)                                 # the parser of the language itself
    spans = []                                             # first and last line of each
    for node in tree.body:                                 # tree.body is exactly the top level
        first = node.lineno                                # where the statement starts
        for decorator in getattr(node, "decorator_list", []) or []:  # a decorator belongs to it
            first = min(first, decorator.lineno)           # so the start moves up
        spans.append((first, node.end_lineno))             # and where it ends
    return spans                                           # in file order


# --------------------------------------------------------------------------
# Splitting: CSS
# --------------------------------------------------------------------------

def css_statements(text):
    """A top-level CSS statement is a rule at depth zero or an at-rule."""
    spans = []                                             # the result
    i, size = 0, len(text)                                 # a walk through the characters
    line = 1                                               # the line we are on
    first_line = None                                      # where the current statement began
    depth = 0                                              # how deep in braces we are
    has_content = False                                    # has the statement started
    in_string = None                                       # the quote we are inside, if any

    while i < size:                                        # one character at a time
        char = text[i]                                     # the character

        if char == "\n":                                   # a newline
            line += 1                                      # moves the counter
            i += 1
            continue

        if in_string:                                      # inside quotes nothing counts
            if char == "\\":                               # an escape
                i += 2                                     # skips the next character too
                continue
            if char == in_string:                          # the closing quote
                in_string = None                           # ends the string
            i += 1
            continue

        if char in "\"'":                                  # a quote opens a string
            in_string = char                               # remember which one
            if not has_content:                            # a string can start a statement
                first_line, has_content = line, True
            i += 1
            continue

        if char == "/" and i + 1 < size and text[i + 1] == "*":  # a comment opens
            end = text.find("*/", i + 2)                   # find where it closes
            if end == -1:                                  # an unclosed comment
                end = size                                 # runs to the end
            line += text.count("\n", i, end)               # count its newlines
            i = end + 2                                    # and jump over it
            continue

        if not char.strip():                               # spaces and tabs
            i += 1                                         # carry no meaning
            continue

        if not has_content:                                # the first real character
            first_line, has_content = line, True           # opens a statement

        if char == "{":                                    # a block opens
            depth += 1                                     # one level deeper
        elif char == "}":                                  # a block closes
            depth -= 1                                     # one level up
            if depth <= 0:                                 # back at the top level
                depth = 0                                  # never below zero
                spans.append((first_line, line))           # the statement is complete
                has_content = False                        # the next one may begin
        elif char == ";" and depth == 0:                   # a semicolon at the top level
            spans.append((first_line, line))               # closes an at-rule
            has_content = False                            # and the next one may begin

        i += 1                                             # on to the next character

    return spans                                           # in file order


# --------------------------------------------------------------------------
# Splitting: TypeScript / JavaScript
# --------------------------------------------------------------------------

def find_typescript(skill_dir, project_root):
    """Looks for the TypeScript parser: the skill directory first, the project second."""
    candidates = []                                        # every place worth trying
    current = skill_dir                                    # start at the skill
    while True:                                            # and walk upwards
        candidates.append(os.path.join(current, "node_modules", "typescript"))
        parent = os.path.dirname(current)                  # one folder up
        if parent == current:                              # the root of the disk
            break                                          # ends the walk
        current = parent
    if project_root and os.path.isdir(project_root):       # then the project, if given
        candidates.append(os.path.join(project_root, "node_modules", "typescript"))
        try:
            for name in sorted(os.listdir(project_root)):  # and one level inside it
                candidates.append(
                    os.path.join(project_root, name, "node_modules", "typescript")
                )
        except OSError:                                    # an unreadable folder
            pass                                           # is simply not a candidate
    for candidate in candidates:                           # try them in order
        if os.path.isfile(os.path.join(candidate, "package.json")):  # a real installation
            return candidate.replace("\\", "/")            # forward slashes for node
    return None                                            # nothing found


def typescript_statements(files, typescript_path, helper):
    """Hands the TypeScript files to the helper and reads its answer."""
    if not files:                                          # no TypeScript in the project
        return {}                                          # nothing to do
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as handle:     # the list travels in a file
        json.dump([f.replace("\\", "/") for f in files], handle)      # so long paths cannot break
        list_path = handle.name                            # remember where it is
    try:
        result = subprocess.run(                           # run the helper
            ["node", helper, typescript_path, list_path],  # node, the helper, the parser, the list
            capture_output=True, text=True, encoding="utf-8",  # read its answer as text
        )
        if result.returncode != 0:                         # the helper itself failed
            raise SystemExit(
                "The TypeScript parser did not answer:\n" + (result.stderr or "")
            )
        return json.loads(result.stdout)                   # the boundaries, per file
    finally:
        os.unlink(list_path)                               # the temporary file always goes


# --------------------------------------------------------------------------
# Splitting: common
# --------------------------------------------------------------------------

def join_lines(lines, first, last):
    """Squeezes a many-line statement onto one line."""
    chunk = "\n".join(lines[first - 1:last])               # the lines it occupies
    return re.sub(r"\s+", " ", chunk).strip()              # every run of whitespace becomes one space


def split_sources(analysis, project=None):
    """Splits every copied file and writes the statement list."""
    analysis = os.path.abspath(analysis)                   # full path
    root = os.path.join(analysis, SOURCE_DIR)              # the copy made by 'copy'
    if not os.path.isdir(root):                            # without it there is nothing to split
        raise SystemExit("No copied source: " + root)

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the skill directory
    helper = os.path.join(skill_dir, "scripts", "ts_statements.js")          # the TypeScript helper

    all_files = []                                         # every copied file
    for base, folders, names in os.walk(root):             # walk the copy
        folders.sort()                                     # in a fixed order
        for name in sorted(names):                         # so the ids never move
            all_files.append(os.path.join(base, name))

    ts_files = [f for f in all_files if f.lower().endswith(TS_EXTENSIONS)]  # the TypeScript ones
    ts_result = {}                                         # their boundaries
    if ts_files:                                           # only when there are any
        typescript_path = find_typescript(skill_dir, project)   # find the parser
        if not typescript_path:                            # without it TypeScript cannot be split
            raise SystemExit(
                "The TypeScript parser is missing.\n"
                "Run inside the skill directory: npm install typescript@5"
            )
        ts_result = typescript_statements(ts_files, typescript_path, helper)  # ask it once, for all

    output_lines = []                                      # the lines of statements.txt
    not_split = []                                         # files that failed, with the reason
    by_extension = {}                                      # how many statements per extension
    number = 0                                             # the running id

    for path in all_files:                                 # every file in turn
        relative = os.path.relpath(path, root).replace("\\", "/")  # its address in the list
        extension = os.path.splitext(path)[1].lower()      # which parser it needs
        try:
            with open(path, "r", encoding="utf-8", errors="strict") as fh:  # strict: no silent damage
                text = fh.read()                           # the whole file
        except (OSError, UnicodeDecodeError) as error:     # unreadable or not UTF-8
            not_split.append({"file": relative, "reason": "cannot read: " + str(error)})
            continue                                       # never dropped in silence

        lines = text.split("\n")                           # for cutting out the text later

        try:
            if extension in PY_EXTENSIONS:                 # Python
                spans = python_statements(text)
            elif extension in CSS_EXTENSIONS:              # CSS
                spans = css_statements(text)
            elif extension in TS_EXTENSIONS:               # TypeScript and JavaScript
                answer = ts_result.get(path.replace("\\", "/"), {})  # what the helper said
                if "error" in answer:                      # it could not parse this one
                    raise ValueError(answer["error"])      # so the reason travels on
                spans = [tuple(span) for span in answer.get("statements", [])]
            else:                                          # a language with no parser here
                not_split.append({
                    "file": relative,
                    "reason": "no parser for extension " + (extension or "(none)"),
                })
                continue                                   # again: named, not dropped
        except (SyntaxError, ValueError) as error:         # broken syntax
            not_split.append({"file": relative, "reason": "cannot split: " + str(error)})
            continue                                       # the other files still go through

        by_extension[extension] = by_extension.get(extension, 0) + len(spans)  # count them
        for first, last in spans:                          # every statement of this file
            text_of_statement = join_lines(lines, first, last)  # its text on one line
            if not text_of_statement:                      # an empty span carries nothing
                continue                                   # and gets no id
            number += 1                                    # the next id
            output_lines.append(                           # id | file | first-last | text
                str(number) + SEPARATOR + relative + SEPARATOR
                + str(first) + "-" + str(last) + SEPARATOR + text_of_statement
            )

    statements_path = os.path.join(analysis, STATEMENTS)   # where the list goes
    with open(statements_path, "w", encoding="utf-8", newline="\n") as fh:  # always UTF-8, always \n
        for line in output_lines:
            fh.write(line + "\n")                          # one statement per line

    report = {                                             # the numbers of this step
        "files_in_analysis_directory": len(all_files),     # how many were there
        "files_split": len(all_files) - len(not_split),    # how many went through
        "statements": number,                              # how many statements came out
        "statements_by_extension": by_extension,           # and of which languages
        "files_not_split": not_split,                      # with every failure named
    }
    with open(os.path.join(analysis, SPLIT_REPORT), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)  # readable, non-Latin text kept

    print("Files in the analysis directory: "              # the same numbers on screen
          + str(report["files_in_analysis_directory"]))
    print("Files split:                     " + str(report["files_split"]))
    print("Top-level statements:            " + str(report["statements"]))
    for extension in sorted(by_extension):                 # the breakdown
        print("   " + extension + ": " + str(by_extension[extension]))
    if not_split:                                          # if anything failed
        print("Files not split:                 " + str(len(not_split)))
        for item in not_split[:20]:                        # the first twenty, with reasons
            print("   " + item["file"] + " - " + item["reason"])
    print("Statement list: " + statements_path)            # where the result is
    return 0                                               # success


# --------------------------------------------------------------------------

def main():
    """Two commands: copy and split."""
    parser = argparse.ArgumentParser(prog="statements.py",     # the program name in the help
                                     description="SPIDER - step 1")
    commands = parser.add_subparsers(dest="command", required=True)  # a command is required

    copy_command = commands.add_parser("copy")                 # copy the source
    copy_command.add_argument("--project", required=True)      # from where
    copy_command.add_argument("--analysis", required=True)     # to where

    split_command = commands.add_parser("split")               # split the copy
    split_command.add_argument("--analysis", required=True)    # where the copy is
    split_command.add_argument("--project", required=False, default=None)  # only to find the parser

    arguments = parser.parse_args()                            # read them
    if arguments.command == "copy":                            # and do the work
        return copy_sources(arguments.project, arguments.analysis)
    return split_sources(arguments.analysis, arguments.project)


if __name__ == "__main__":                                     # when run directly
    sys.exit(main())                                           # the exit code is the result
