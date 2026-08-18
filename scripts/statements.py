"""SPIDER - step 1: build the statement list.

Two commands:

    statements.py copy  --project <project> --analysis <analysis directory> [--fresh]
        Copies into the analysis directory every file the intelligence listed in
        source-files.txt, keeping the same names and the same folder layout, and
        writes manifest.json with a checksum of every copied file. The project
        is only read, never modified. An existing snapshot is refused unless
        --fresh removes it first.

    statements.py split --analysis <analysis directory> [--project <project>]
        Splits every copied file into top-level statements and writes
        statements.txt, css-selectors.tsv with every name of every style rule,
        and the split report. A file left unsplit makes the exit code non-zero.

One line of statements.txt looks like this:

    id | file | first-last | text

The text comes last. A statement that spans many lines in its own file is
written on a single line here; its address points at the exact place in the
copied file. Inside quotes the text is kept exactly as written.

Every line below carries a comment. A file that cannot be read or split is
written into the split report with its reason and the rest still go through.
The refusals guard the boundaries and the snapshot, each named exactly: no
list of source files; an absolute path or one climbing out with '..'; a path
leading outside the project or the analysis; an existing snapshot without
--fresh; and no TypeScript parser inside the skill directory when the project
holds TypeScript - the parser is never taken from the analysed project.
"""

import argparse                                   # reads the command line
import ast                                        # the Python parser
import bisect                                     # finds the line an offset falls on
import hashlib                                    # the checksums of the snapshot
import json                                       # the file list and the report
import os                                         # paths, walking, checks
import platform                                   # the Python version, for the manifest
import re                                         # squeezes whitespace
import shutil                                     # copies files
import subprocess                                 # runs the TypeScript helper
import sys                                        # exit code and stdout
import tempfile                                   # the temporary file list

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the scripts directory itself
from version import VERSION, SCHEMA as SCHEMA_VERSION  # the one place the numbers live

if hasattr(sys.stdout, "reconfigure"):            # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")      # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")      # a project with non-Latin text must not break it

SOURCE_FILES = "source-files.txt"                 # written by the intelligence
STATEMENTS = "statements.txt"                     # the result of this step
SPLIT_REPORT = "split-report.json"                # the numbers of this step
SOURCE_DIR = "source"                             # where the copy lives
MANIFEST = "manifest.json"                        # the record of the snapshot
CSS_SELECTORS = "css-selectors.tsv"               # every name of every style rule, addressable

TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")  # the TypeScript parser
PY_EXTENSIONS = (".py",)                                        # the Python parser
CSS_EXTENSIONS = (".css",)                                      # the splitter below
SH_EXTENSIONS = (".sh",)                                        # the splitter below

SEPARATOR = " | "                                 # between the four columns of a line


# --------------------------------------------------------------------------
# Copying
# --------------------------------------------------------------------------

def file_sha256(path):
    """The checksum of one file, read once, in pieces."""
    digest = hashlib.sha256()                              # the running sum
    with open(path, "rb") as fh:                           # bytes, exactly as stored
        for piece in iter(lambda: fh.read(1 << 20), b""):  # a megabyte at a time
            digest.update(piece)                           # fed into the sum
    return digest.hexdigest()                              # as text


def read_source_list(analysis):
    """Reads the list of application source files the intelligence wrote.

    A path that points outside the project - absolute, with a drive letter, or
    climbing up with '..' - is refused by name. A quiet fix here would let a
    damaged list read files the analysis was never given.
    """
    path = os.path.join(analysis, SOURCE_FILES)            # it lives in the analysis directory
    if not os.path.exists(path):                           # without it there is nothing to copy
        raise SystemExit(
            "No list of application source files: " + path + "\n"
            "The intelligence must write it before copying."
        )
    cleaned = []                                           # the accepted paths
    with open(path, "r", encoding="utf-8") as fh:          # the list is UTF-8
        for number, line in enumerate(fh, 1):              # count from 1 for the message
            relative = line.strip().replace("\\", "/")     # one path per line, forward slashes
            if not relative or relative.startswith("#"):   # blanks and notes
                continue                                   # drop out
            if relative.startswith("/") or re.match(r"^[A-Za-z]:", relative):
                raise SystemExit(                          # an absolute path is refused, not fixed
                    "Line " + str(number) + " of " + SOURCE_FILES + " is an "
                    "absolute path: " + relative[:60] + "\n"
                    "Every path is relative to the project root.")
            if ".." in relative.split("/"):                # a path climbing out of the project
                raise SystemExit(
                    "Line " + str(number) + " of " + SOURCE_FILES + " climbs "
                    "outside the project with '..': " + relative[:60])
            cleaned.append(relative)                       # accepted
    return cleaned                                         # in file order


def contained(child, parent):
    """True when the real place of child is inside the real place of parent."""
    child = os.path.realpath(child)                        # symlinks resolved
    parent = os.path.realpath(parent)                      # on both sides
    return child == parent or child.startswith(parent + os.sep)  # inside or equal


def read_scope_register(analysis):
    """Reads the OPTIONAL register of the whole discovered world.

    `source-scope.tsv`, three columns per line: path, role, evidence. Roles:
    application, test, control, migration, generated, dependency, excluded.
    When the register exists, the copy checks that every path of the
    application list carries the role `application` and says how much of
    the world the register covers. The register cannot decide anything -
    it records WHY each file is in or out, so the decision can be checked
    by anyone, the owner's rules 1-3 first of all."""
    path = os.path.join(analysis, "source-scope.tsv")
    if not os.path.isfile(path):
        return None
    roles = {"application", "test", "control", "migration", "generated",
             "dependency", "excluded"}
    register = {}
    with open(path, "r", encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise SystemExit("Line " + str(number) + " of source-scope.tsv"
                                 " is not path<TAB>role<TAB>evidence.")
            relative, role, evidence = parts
            if role not in roles:
                raise SystemExit("Line " + str(number) + " of source-scope.tsv"
                                 " carries an unknown role: " + role)
            if not evidence.strip():
                raise SystemExit("Line " + str(number) + " of source-scope.tsv"
                                 " carries no evidence.")
            if relative in register:
                raise SystemExit("source-scope.tsv names " + relative + " twice.")
            register[relative] = role
    return register


def copy_sources(project, analysis, fresh):
    """Copies the listed files into the analysis directory."""
    project = os.path.abspath(project)                     # full paths only
    analysis = os.path.abspath(analysis)                   # for both sides
    listed = read_source_list(analysis)                    # what to copy
    register = read_scope_register(analysis)               # why, when it exists

    if register is not None:                               # the register is checked
        unregistered = [r for r in listed if r not in register]
        if unregistered:                                   # a listed file must carry
            raise SystemExit("Listed but not in source-scope.tsv: "
                             + unregistered[0])            # its recorded reason
        misroled = [r for r in listed if register[r] != "application"]
        if misroled:
            raise SystemExit("Listed as source but registered as "
                             + register[misroled[0]] + ": " + misroled[0])

    source_dir = os.path.join(analysis, SOURCE_DIR)        # where the snapshot lives
    if os.path.isdir(source_dir):                          # an old snapshot underneath
        if not fresh:                                      # would mix two versions of the code
            raise SystemExit(
                "The snapshot directory already exists: " + source_dir + "\n"
                "A copy over an old snapshot mixes two versions of the code. "
                "Run with --fresh to remove it first.")
        shutil.rmtree(source_dir)                          # only the snapshot, nothing else

    copied, missing, quarantined = [], [], []              # counted for the report
    hashes = {}                                            # path -> checksum, for the manifest
    for relative in listed:                                # every listed path
        origin = os.path.join(project, relative.replace("/", os.sep))  # where it is
        if not contained(origin, project):                 # a link or a trick leading outside
            raise SystemExit(
                "The path " + relative + " leads outside the project: " + origin)
        if not os.path.isfile(origin):                     # a path that names nothing
            missing.append(relative)                       # is reported, not guessed at
            continue                                       # and the rest go on
        try:                                               # a file that is not UTF-8
            with open(origin, "rb") as fh:                 # cannot be split or searched;
                fh.read().decode("utf-8", "strict")        # it is quarantined BY NAME
        except UnicodeDecodeError as error:                # and the work goes on -
            quarantined.append({"file": relative,          # a finding, not a stop
                                "reason": str(error)[:120]})
            continue
        target = os.path.join(source_dir, relative.replace("/", os.sep))  # where it goes
        if not contained(os.path.dirname(target), analysis):  # never outside the analysis
            raise SystemExit(
                "The path " + relative + " would land outside the analysis "
                "directory: " + target)
        os.makedirs(os.path.dirname(target), exist_ok=True)  # keep the folder layout
        shutil.copy2(origin, target)                       # copy with the timestamps
        hashes[relative] = file_sha256(target)             # the checksum of the copy
        copied.append(relative)                            # one more done

    manifest = {                                           # the record of this snapshot
        "spider_version": VERSION,                         # which code took it
        "schema_version": SCHEMA_VERSION,                  # which layout it belongs to
        "python_version": platform.python_version(),       # which Python split it
        "files": hashes,                                   # every file with its checksum
        "listed": len(listed),                             # how many were asked for
        "copied": len(copied),                             # how many arrived
        "missing": missing,                                # and which did not
        "quarantined": quarantined,                        # named, never silent
        "scope_register": register is not None,            # whether the reasons exist
    }
    with open(os.path.join(analysis, MANIFEST), "w",       # written next to the snapshot
              encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=True, indent=2)  # plain characters only
        fh.write("\n")                                     # a closing newline

    print("Listed files:   " + str(len(listed)))           # from the list
    print("Copied files:   " + str(len(copied)))           # from the copying
    print("Missing files:  " + str(len(missing)))          # must be zero
    for name in missing:                                   # and if not
        print("   missing: " + name)                       # each one is named
    if quarantined:                                        # named out loud as well
        print("Quarantined (not UTF-8): " + str(len(quarantined)))
        for entry in quarantined:
            print("   quarantined: " + entry["file"])
    print("Manifest: " + os.path.join(analysis, MANIFEST)) # where the record is
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
# Splitting: shell
# --------------------------------------------------------------------------

SH_HEREDOC = re.compile(r"<<-?\s*(?:\"([\w./-]+)\"|'([\w./-]+)'|([\w./-]+))")
SH_OPENERS = {"if": "fi", "for": "done", "while": "done",
              "until": "done", "case": "esac"}


def shell_line_state(line, depth, in_single, in_double):
    """Walks one line and returns the brace depth and quote state after it.

    Comments start at an unquoted #, quotes carry across lines, and braces
    inside quotes or comments never count. Close enough for real scripts;
    a file this cannot follow lands in the split report by name.
    """
    i = 0
    while i < len(line):
        character = line[i]
        if in_single:
            if character == "'":
                in_single = False
        elif in_double:
            if character == "\\":
                i += 1                                     # the next one is literal
            elif character == '"':
                in_double = False
        elif character == "\\":
            i += 1                                         # the next one is literal
        elif character == "'":
            in_single = True
        elif character == '"':
            in_double = True
        elif character == "#":
            break                                          # a comment to the end
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        i += 1
    return depth, in_single, in_double


def shell_statements(text):
    """A top-level shell statement: a function with its body, a compound
    command with its closer, or one command with its continuations and
    here-documents. Comments and blank lines drop out."""
    lines = text.split("\n")
    spans = []
    start = None                                           # first line of the open unit
    depth = 0                                              # brace depth
    in_single = in_double = False                          # quote state across lines
    compound = []                                          # open if/for/while/until/case
    heredocs = []                                          # markers still to close
    for number, raw in enumerate(lines, 1):
        line = raw.rstrip("\r")
        stripped = line.strip()
        if heredocs:                                       # inside a here-document
            marker = heredocs[0]
            if stripped == marker or line.lstrip("\t") == marker:
                heredocs.pop(0)                            # this one is closed
            if start is None:                              # never true in honest input
                start = number
            if not heredocs and not compound and depth == 0 \
                    and not line.endswith("\\"):
                spans.append((start, number))
                start = None
            continue
        if not stripped:                                   # a blank line
            continue                                       # drops out
        if stripped.startswith("#") and start is None:     # a comment line
            if number == 1 and stripped.startswith("#!"):  # except the shebang:
                spans.append((1, 1))                       # data the system reads
            continue
        if start is None:
            start = number
        # what this line opens and closes
        first_word = re.match(r"[A-Za-z_{]+", stripped)
        word = first_word.group(0) if first_word else ""
        if word in SH_OPENERS:
            compound.append(SH_OPENERS[word])
        elif compound and (stripped == compound[-1]
                           or stripped.startswith(compound[-1] + " ")
                           or stripped.startswith(compound[-1] + ";")):
            compound.pop()
        depth, in_single, in_double = shell_line_state(line, depth,
                                                       in_single, in_double)
        for match in SH_HEREDOC.finditer(line):            # a here-document opens
            heredocs.append(next(g for g in match.groups() if g))
        if depth < 0:
            raise ValueError("unbalanced braces at line " + str(number))
        if (depth == 0 and not compound and not heredocs
                and not in_single and not in_double
                and not line.endswith("\\")):
            spans.append((start, number))                  # the unit is whole
            start = None
    if heredocs:
        raise ValueError("an unterminated here-document: " + heredocs[0])
    if in_single or in_double:
        raise ValueError("an unterminated quote at the end of the file")
    if depth != 0 or compound:
        raise ValueError("an unclosed block at the end of the file")
    if start is not None:
        spans.append((start, len(lines)))
    return spans


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
                if i + 1 < size and text[i + 1] == "\n":   # an escaped newline
                    line += 1                              # still counts as a line
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

    if depth > 0 or has_content or in_string:              # the file ended mid-statement
        raise ValueError(                                  # a half statement is damage,
            "the file ends inside an unclosed "            # not a statement - the file
            + ("string" if in_string else "block or rule") # goes into the report with
            + " that began on line " + str(first_line))    # its reason, never in silence

    return spans                                           # in file order


def split_selector_list(text, line_of, names, start_offset):
    """Splits one prelude on the commas at nesting depth zero, into `names`."""
    start, depth = 0, 0                                    # the current name and nesting
    for position, char in enumerate(text + ","):           # a closing comma ends the last name
        if char in "([":                                   # nesting opens
            depth += 1                                     # one level deeper
        elif char in ")]":                                 # nesting closes
            depth -= 1                                     # one level up
        elif char == "," and depth == 0:                   # a comma between names
            piece = text[start:position]                   # the name with its spaces
            stripped = piece.strip()                       # the name alone
            if stripped:                                   # an empty piece is no name
                offset = start + (len(piece) - len(piece.lstrip()))  # where it starts
                names.append((len(names) + 1, stripped,    # ordinal and text
                              line_of(start_offset + offset)))
            start = position + 1                           # the next name begins after


def css_rule_selectors(lines, first, last):
    """Every name this style statement carries, wherever it stands inside it.

    A plain rule carries the names before its own brace. An at-rule - `@media`,
    `@supports` and the rest - carries the names of every rule nested inside
    it, each one addressable on its own line. Version 2.1 returned nothing at
    all for an at-rule: in a real project that left 95 statements with no name
    to search for, so their whole contents reached the review with no evidence
    and a dead name could hide inside a living block untouched.

    Returns (ordinal, selector, line) for every name. Strings and comments are
    walked through without being read as structure, so a brace inside quotes
    never shifts the nesting.
    """
    written = "\n".join(lines[first - 1:last])             # the statement, as written
    blanked = list(written)                                # a working copy of it
    scan_index = 0                                         # every comment is blanked first,
    while scan_index < len(written):                       # so its contents can never be
        if written[scan_index:scan_index + 2] == "/*":     # read as a name later on
            end = written.find("*/", scan_index + 2)       # where it closes
            end = len(written) if end < 0 else end + 2     # or the end of the statement
            for position in range(scan_index, end):        # every character of it
                if blanked[position] != "\n":              # the line breaks stay,
                    blanked[position] = " "                # so every offset keeps its line
            scan_index = end                               # on past the comment
            continue
        scan_index += 1                                    # on to the next character
    text = "".join(blanked)                                # the statement without comments
    line_starts = [0]                                      # where each of its lines begins
    for char_index, char in enumerate(text):               # walked once
        if char == "\n":                                   # a line ends here
            line_starts.append(char_index + 1)             # the next one starts after it

    def line_of(offset):
        """The file line an offset inside the statement falls on."""
        place = bisect.bisect_right(line_starts, min(offset, len(text))) - 1
        return first + max(place, 0)                       # counted from the statement's first

    names = []                                             # the result, in written order
    prelude_start = 0                                      # where the current prelude began
    depth = 0                                              # how deep in braces we stand
    index = 0                                              # the character being read
    quote = ""                                             # the quote we are inside, if any
    while index < len(text):                               # every character of the statement
        char = text[index]                                 # the one being read
        if quote:                                          # inside a string
            if char == "\\":                               # an escape takes the next one
                index += 2                                 # with it
                continue
            if char == quote:                              # the string closes
                quote = ""                                 # and structure counts again
            index += 1
            continue
        if char in "\"'":                                  # a string opens
            quote = char                                   # nothing inside it is structure
            index += 1
            continue
        if char == "{":                                    # a block opens
            prelude = text[prelude_start:index]            # what stood before it
            if not prelude.lstrip().startswith("@"):       # an at-rule is not a name list
                split_selector_list(prelude, line_of, names, prelude_start)
            depth += 1                                     # one level deeper
            prelude_start = index + 1                      # the next prelude starts here
        elif char == "}":                                  # a block closes
            depth -= 1                                     # one level up
            prelude_start = index + 1                      # whatever follows is new
        elif char == ";" and depth == 0:                   # an at-rule with no block
            prelude_start = index + 1                      # ends here
        index += 1                                         # on to the next character
    return names                                           # in written order


# --------------------------------------------------------------------------
# Splitting: TypeScript / JavaScript
# --------------------------------------------------------------------------

def find_typescript(skill_dir):
    """The TypeScript parser is taken from the skill directory and nowhere else.

    Loading it from the analysed project would execute the project's own code,
    and the project is only read - a promise this program is not allowed to
    break, whatever the convenience.
    """
    candidate = os.path.join(skill_dir, "node_modules", "typescript")  # the one place
    if os.path.isfile(os.path.join(candidate, "package.json")):  # a real installation
        return candidate.replace("\\", "/")                # forward slashes for node
    return None                                            # nothing found - the caller refuses


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
    """Squeezes a many-line statement onto one line.

    Outside quotes every run of whitespace becomes one space. Inside quotes
    the text is kept exactly as written, because "a  b" and "a b" are two
    different strings and the analysis must see the one the program holds;
    only a newline inside a string is written as backslash-n, since the whole
    statement has to live on a single line of the list.
    """
    chunk = "\n".join(lines[first - 1:last])               # the lines it occupies
    out = []                                               # the squeezed text
    in_string = None                                       # the quote we are inside, if any
    triple = None                                          # the triple quote we are inside, if any
    i, size = 0, len(chunk)                                # a walk through the characters
    while i < size:                                        # one character at a time
        char = chunk[i]                                    # the character
        if triple:                                         # inside a triple-quoted string
            if chunk.startswith(triple, i):                # the closing triple
                out.append(triple)                         # kept as written
                i += 3                                     # jumped over
                triple = None                              # the string ends
                continue
            out.append("\\n" if char == "\n" else char)    # content kept, newline written out
            i += 1
            continue
        if in_string:                                      # inside a plain string
            if char == "\\" and i + 1 < size:              # an escape
                out.append(char)                           # the backslash itself
                out.append("\\n" if chunk[i + 1] == "\n" else chunk[i + 1])  # and what it guards
                i += 2                                     # both are done
                continue
            if char == in_string:                          # the closing quote
                in_string = None                           # the string ends
            out.append("\\n" if char == "\n" else char)    # content kept, newline written out
            i += 1
            continue
        if chunk.startswith("'''", i) or chunk.startswith('"""', i):  # a triple quote opens
            triple = chunk[i:i + 3]                        # remember which one
            out.append(triple)                             # kept as written
            i += 3
            continue
        if char in "\"'`":                                 # a plain quote opens a string
            in_string = char                               # remember which one
            out.append(char)
            i += 1
            continue
        if char.isspace():                                 # whitespace outside strings
            if out and out[-1] != " ":                     # a run becomes
                out.append(" ")                            # a single space
            i += 1
            continue
        out.append(char)                                   # an ordinary character
        i += 1
    return "".join(out).strip()                            # on one line, trimmed


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
    ts_version = None                                      # the parser version, for the manifest
    if ts_files:                                           # only when there are any
        typescript_path = find_typescript(skill_dir)       # the skill's own parser, nowhere else
        if not typescript_path:                            # without it TypeScript cannot be split
            raise SystemExit(
                "The TypeScript parser is missing from the skill directory.\n"
                "Run inside the skill directory: npm install typescript@5\n"
                "The parser is never taken from the analysed project - that "
                "would execute the project's code, and the project is only read."
            )
        ts_result = typescript_statements(ts_files, typescript_path, helper)  # ask it once, for all
        ts_version = ts_result.pop("__version__", None)    # the helper reports its parser version

    output_lines = []                                      # the lines of statements.txt
    not_split = []                                         # files that failed, with the reason
    by_extension = {}                                      # how many statements per extension
    selector_rows = []                                     # every name of every style rule
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
            elif extension in SH_EXTENSIONS:               # shell
                spans = shell_statements(text)
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

        for first, last in spans:                          # every statement of this file
            text_of_statement = join_lines(lines, first, last)  # its text on one line
            if not text_of_statement:                      # an empty span carries nothing
                continue                                   # and gets no id
            if extension in CSS_EXTENSIONS:                # a style rule
                # The unit of measurement for a style sheet is EVERY NAME the
                # rule addresses. When one name in a written list works and
                # another does not, the dead one must be checkable and
                # repairable on its own - a dead name hiding inside a living
                # list is exactly what the rule-sized unit could not see.
                # A rule that writes no class, id or attribute anywhere -
                # bare elements, :root, @import, @keyframes - stays one unit:
                # it acts by being present, and its whole text (variables,
                # animation frames) must stay addressable together.
                names = css_rule_selectors(lines, first, last)
                addressed = any(("." in selector or "#" in selector)
                                for _, selector, _ in names)
                if names and addressed:                    # one unit per written name
                    for ordinal, selector, name_line in names:
                        number += 1                        # the next id
                        by_extension[extension] = by_extension.get(extension, 0) + 1
                        output_lines.append(               # the name's own address
                            str(number) + SEPARATOR + relative + SEPARATOR
                            + str(name_line) + "-" + str(name_line) + SEPARATOR
                            + selector + " { of the rule at "
                            + str(first) + "-" + str(last) + " }")
                        selector_rows.append((number, 1, selector, name_line))
                    continue                               # the rule itself is its names
            number += 1                                    # the next id
            by_extension[extension] = by_extension.get(extension, 0) + 1
            output_lines.append(                           # id | file | first-last | text
                str(number) + SEPARATOR + relative + SEPARATOR
                + str(first) + "-" + str(last) + SEPARATOR + text_of_statement
            )
            if extension in CSS_EXTENSIONS:                # a rule that names nothing
                selector_rows.append((number, 1,           # is addressable as itself
                                      text_of_statement.split("{", 1)[0].strip()[:120],
                                      first))

    statements_path = os.path.join(analysis, STATEMENTS)   # where the list goes
    with open(statements_path, "w", encoding="utf-8", newline="\n") as fh:  # always UTF-8, always \n
        for line in output_lines:
            fh.write(line + "\n")                          # one statement per line

    if selector_rows:                                      # a project with styles
        with open(os.path.join(analysis, CSS_SELECTORS), "w",
                  encoding="utf-8", newline="\n") as fh:   # the addressable names
            fh.write("statement_id\tordinal\tselector\tline\n")  # the heading
            for row in selector_rows:                      # one name per line
                fh.write("%d\t%d\t%s\t%d\n" % row)         # id, ordinal, name, line

    report = {                                             # the numbers of this step
        "files_in_analysis_directory": len(all_files),     # how many were there
        "files_split": len(all_files) - len(not_split),    # how many went through
        "statements": number,                              # how many statements came out
        "statements_by_extension": by_extension,           # and of which languages
        "css_selector_names": len(selector_rows),          # how many style names are addressable
        "files_not_split": not_split,                      # with every failure named
    }
    with open(os.path.join(analysis, SPLIT_REPORT), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)  # readable, non-Latin text kept

    manifest_path = os.path.join(analysis, MANIFEST)       # the record the copy step wrote
    if os.path.isfile(manifest_path):                      # extend it with the split facts
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)                       # what the copy recorded
        manifest["statements"] = number                    # how many statements came out
        manifest["typescript_version"] = ts_version        # which parser split them
        manifest["files_not_split"] = len(not_split)       # and how many files failed
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(manifest, fh, ensure_ascii=True, indent=2)  # plain characters only
            fh.write("\n")                                 # a closing newline

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
    return 1 if not_split else 0                           # a file left unsplit is not success


# --------------------------------------------------------------------------

def main():
    """Two commands: copy and split."""
    parser = argparse.ArgumentParser(prog="statements.py",     # the program name in the help
                                     description="SPIDER - step 1")
    commands = parser.add_subparsers(dest="command", required=True)  # a command is required

    copy_command = commands.add_parser("copy")                 # copy the source
    copy_command.add_argument("--project", required=True)      # from where
    copy_command.add_argument("--analysis", required=True)     # to where
    copy_command.add_argument("--fresh", action="store_true")  # remove an old snapshot first

    split_command = commands.add_parser("split")               # split the copy
    split_command.add_argument("--analysis", required=True)    # where the copy is
    split_command.add_argument("--project", required=False, default=None)  # kept for compatibility

    arguments = parser.parse_args()                            # read them
    if arguments.command == "copy":                            # and do the work
        return copy_sources(arguments.project, arguments.analysis, arguments.fresh)
    return split_sources(arguments.analysis, arguments.project)


if __name__ == "__main__":                                     # when run directly
    sys.exit(main())                                           # the exit code is the result
