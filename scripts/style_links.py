"""SPIDER - step 6 helper: find the users of every style statement.

    style_links.py find --analysis <analysis directory>

For every style statement that is still unvisited, this program searches the
verified snapshot for evidence of use and writes what it finds into
`style-candidates.tsv`. The intelligence then settles each statement in the
ordinary rounds of step 6, with the evidence in front of it.

The program only finds. It decides nothing: a row in its output is a place to
look, and an empty result is not proof of death - it says so itself in the
output, statement by statement.

Three traps each turned a living rule into a seemingly dead one during real
work, and this program exists so they cannot happen again:

  - a name assembled at runtime: the code writes `status-${kind}` while the
    sheet carries `status-success`; searching for the whole name finds
    nothing, so the program searches for joined beginnings as well;
  - a rule used inside its own file: an animation defined and used in the
    same sheet; the program excludes only the exact span of the definition,
    never the whole file;
  - a file name mistaken for a class: in `@import "../x.css"` the dot belongs
    to a file name; the boundaries here are CSS identifier boundaries, where
    `-` and `_` are letters, so `.btn` never matches `.button` or
    `.btn-primary` in exact mode.

Compound-name schemes searched in prefix mode, explicitly and exhaustively:
`name-...`, `name--...` and `name__...`. No other joining is assumed.

Every line below carries a comment.
"""

import argparse                                  # reads the command line
import collections                               # grouped findings
import io                                        # files, always UTF-8
import os                                        # paths and walking
import re                                        # the searches themselves
import sqlite3                                   # the database
import sys                                       # exit code and stdout

if hasattr(sys.stdout, "reconfigure"):           # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")     # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")     # so non-Latin text never breaks it

DATABASE = "analysis.db"                         # made by step 3
SOURCE_DIR = "source"                            # the verified snapshot
OUTPUT = "style-candidates.tsv"                  # what this program writes

CODE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")  # markup and logic
STYLE_EXTENSIONS = (".css",)                     # the sheets themselves

# A CSS identifier goes on through letters, digits, '-' and '_'. A boundary is
# any other character or the end. This is the language's own rule, not the
# regex notion of a word, under which `.btn` would wrongly match `.btn-primary`.
IDENT = r"[A-Za-z0-9_-]"                         # the characters an identifier holds
CLASS_RE = re.compile(r"\.(-?[_a-zA-Z]" + IDENT + r"*)")  # a class in a selector
VAR_RE = re.compile(r"(--[_a-zA-Z]" + IDENT + r"*)\s*:")  # a custom property defined
KEYFRAME_RE = re.compile(r"@keyframes\s+([_a-zA-Z]" + IDENT + r"*)")  # an animation name
JOINERS = ("-", "--", "__")                      # the compound schemes searched, all of them


def exact_pattern(name):
    """The name itself, on CSS identifier boundaries."""
    return re.compile(r"(?<!" + IDENT + r")" + re.escape(name)
                      + r"(?!" + IDENT + r")")


def prefix_pattern(name):
    """The name joined onward with '-', '--' or '__' - the sheet holds the stem."""
    return re.compile(r"(?<!" + IDENT + r")" + re.escape(name)
                      + r"(?:--|__|-)" + IDENT + r"+")


def stem_patterns(name):
    """The beginnings of the name, where the CODE holds the stem.

    The other half of the assembled case, and the half version 2.1 did not
    search at all. The sheet carries `monument-feed-status-success` while the
    markup writes `monument-feed-status-${state}`: what stands in the code is
    a BEGINNING of the name, not the whole of it and not the name joined
    onward. Searching only the two directions 2.1 knew left ten live rules of
    a real project with no evidence whatsoever.
    """
    patterns = []                                          # one per joining place
    for joiner in JOINERS:                                 # every scheme, longest first
        place = len(name)                                  # searched from the end back
        while True:
            place = name.rfind(joiner, 0, place)           # the next joining place
            if place <= 0:                                 # no joiner, or one at the start
                break
            stem = name[:place + len(joiner)]              # the beginning, joiner included
            patterns.append(re.compile(                    # written, then something else
                r"(?<!" + IDENT + r")" + re.escape(stem) + r"(?!" + IDENT + r")"))
    # A style module joins with a capital instead of a dash: the sheet carries
    # `statusSuccess` and the code writes styles[`status${state}`]. Here the
    # stem is asked for exactly as it is written there - followed by the
    # opening of a template hole - because a bare word like `status` would
    # otherwise match every mention of the word in the project.
    for place in range(1, len(name)):                      # every capital in the name
        if name[place].isupper() and not name[place - 1].isupper():
            patterns.append(re.compile(
                r"(?<!" + IDENT + r")" + re.escape(name[:place]) + r"\$\{"))
    return patterns                                        # in written order


def load_snapshot(analysis):
    """Every code and style file of the snapshot, as lines, read once."""
    root = os.path.join(analysis, SOURCE_DIR)              # where the snapshot lives
    if not os.path.isdir(root):                            # without it there is nothing to search
        raise SystemExit("No snapshot: " + root)
    files = {}                                             # relative path -> lines
    for base, folders, names in os.walk(root):             # walk it
        folders.sort()                                     # in a fixed order
        for name in sorted(names):                         # so the output never moves
            lower = name.lower()                           # compare without case
            if lower.endswith(CODE_EXTENSIONS) or lower.endswith(STYLE_EXTENSIONS):
                path = os.path.join(base, name)            # the file itself
                relative = os.path.relpath(path, root).replace(os.sep, "/")
                files[relative] = io.open(path, encoding="utf-8",
                                          errors="replace").read().split("\n")
    return files                                           # everything, in memory once


PSEUDO_RE = re.compile(r"::?[\w-]+(?:\([^)]*\))?")         # :hover, ::before, :not(...)
ATTRIBUTE_RE = re.compile(r"\[[^\]]*\]")                   # [data-x="y"]
COMBINATOR_RE = re.compile(r"[\s>+~]+")                    # descendant and sibling joints
# `:has(.x)`, `:is(.x)` and `:where(.x)` put a condition ON the subject
# element: the rule applies because that class is there, so the class is a
# subject of the rule. `:not(.x)` applies because it is ABSENT, which proves
# nothing about the class being used, so it stays context.
CONDITION_RE = re.compile(r":(?:has|is|where|matches)\(([^)]*)\)")


def subject_and_context(selector):
    """Which classes a selector styles, and which only say where.

    A selector styles its LAST element - `.card .title` styles the title, not
    the card. Every class standing on that last element is a subject; the
    earlier ones are context. Version 2.1 made no such distinction, so
    evidence for a living ancestor counted as evidence for the rule, and a
    dead rule under a living wrapper was declared alive. That happened.
    """
    conditions = []                                        # classes inside :has, :is, :where
    for inner in CONDITION_RE.findall(selector):           # each such condition
        conditions.extend(CLASS_RE.findall(inner))         # is a condition on the subject
    trimmed = ATTRIBUTE_RE.sub(" ", PSEUDO_RE.sub("", selector))  # only elements and classes
    parts = [piece for piece in COMBINATOR_RE.split(trimmed.strip()) if piece]
    subjects, context = [], []                             # the two roles
    for position, piece in enumerate(parts):               # every element in the chain
        found = CLASS_RE.findall(piece)                    # the classes on it
        if position == len(parts) - 1:                     # the last element is the subject
            subjects.extend(found)                         # every class on it counts
        else:                                              # the earlier ones say where
            context.extend(found)                          # and prove nothing by themselves
    subjects.extend(name for name in conditions            # the conditions stand on it too
                    if name not in subjects)
    if not subjects and context:                           # the last element carries no class
        subjects, context = context[-1:], context[:-1]     # the nearest class is the subject
    return subjects, context                               # in written order


def names_of(statement_text, selectors):
    """What to search for, from one style statement.

    Returns (kind, name, role) triples. The role of a class is `subject` when
    the rule styles it and `context` when it only says where the subject
    stands; a variable and an animation are always subjects of their own name.
    """
    head = statement_text.split("{", 1)[0].strip()         # the part before the block
    found = []                                             # the names to search
    if head.startswith("@keyframes"):                      # an animation definition
        match = KEYFRAME_RE.search(head)                   # its name
        if match:                                          # is searched as an animation
            found.append(("animation", match.group(1), "subject"))
        return found                                       # nothing else in it
    if head.startswith("@import"):                         # an import names a file
        return []                                          # the dot there is no class
    if head.startswith(":root") or "--" in statement_text: # custom properties defined
        for name in sorted(set(VAR_RE.findall(statement_text))):
            found.append(("variable", name, "subject"))    # each searched as var(--name)
    sources = selectors if selectors else (                # the names step 1 recorded,
        [] if head.startswith("@") else [head])            # or the rule's own head
    for selector in sources:                               # every name of the rule
        subjects, context = subject_and_context(selector)  # what it styles, and where
        for name in subjects:                              # the styled classes
            found.append(("class", name, "subject"))
        for name in context:                               # the ones that say where
            found.append(("class", name, "context"))
    seen, unique = set(), []                               # the same name once
    for kind, name, role in found:                         # in a stable order
        if (kind, name) in seen:                           # already searched for
            continue                                       # once is enough
        seen.add((kind, name))                             # remembered
        unique.append((kind, name, role))                  # and kept
    subjects_present = set(n for k, n, r in unique if r == "subject")
    return [(k, n, r) for k, n, r in unique                # a name that is a subject
            if r == "subject" or n not in subjects_present]  # is never also context


def find(analysis, limit=0):
    """Searches the snapshot and writes the evidence file. No cap unless asked."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    database_path = os.path.join(analysis, DATABASE)       # where the records are
    if not os.path.isfile(database_path):                  # step 3 has to be done
        raise SystemExit("No database: " + database_path)

    database = sqlite3.connect("file:" + database_path + "?mode=ro", uri=True)
    try:
        targets = database.execute(                        # the style statements still open
            "SELECT id, file, first_line, last_line FROM statements "
            "WHERE file LIKE '%.css' AND visited IS NULL ORDER BY id").fetchall()
        children = collections.defaultdict(list)           # id -> its recorded names
        try:                                               # when step 1 recorded them
            for statement_id, selector in database.execute(
                    "SELECT statement_id, selector FROM css_selectors"):
                children[statement_id].append(selector)    # kept per statement
        except sqlite3.OperationalError:                   # a base without the table
            pass                                           # falls back to the rule heads
    finally:
        database.close()                                   # closed even if something threw

    files = load_snapshot(analysis)                        # the snapshot, read once
    statement_text = {}                                    # id -> its own text
    for statement_id, name, first, last in targets:        # cut from the snapshot itself
        lines = files.get(name)                            # the file it lives in
        if lines is None:                                  # a sheet outside the snapshot
            raise SystemExit("The snapshot does not hold " + name)
        statement_text[statement_id] = "\n".join(lines[first - 1:last])

    out_path = os.path.join(analysis, OUTPUT)              # where the evidence goes
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as out:
        out.write("statement\tsearched\tkind\trole\tmode\tfile\tline\texcerpt\n")
        with_subject = only_context = without = capped = 0  # counted for the report
        for statement_id, own_file, first, last in targets:  # every open style statement
            rows = []                                      # the findings for this one
            context_hits = {}                              # context class -> found at all
            for kind, name, role in names_of(statement_text[statement_id],
                                             children.get(statement_id)):
                if kind == "class" and role == "context":
                    context_hits.setdefault(name, False)   # counted even when absent
                if kind == "class":                        # a class name
                    patterns = [("exact", exact_pattern(name)),      # written whole
                                ("prefix", prefix_pattern(name))]    # the sheet holds the stem
                    patterns.extend(("stem", pattern)                # the code holds the stem
                                    for pattern in stem_patterns(name))
                elif kind == "variable":                   # a custom property
                    patterns = [("exact", re.compile(     # used through var(--name)
                        r"var\(\s*" + re.escape(name) + r"(?!" + IDENT + r")"))]
                else:                                      # an animation name
                    patterns = [("exact", exact_pattern(name))]
                for relative, lines in files.items():      # every snapshot file
                    if kind == "class" and relative.lower().endswith(STYLE_EXTENSIONS):
                        continue                           # a class name inside any sheet is a
                                                           # definition, never a use; only the
                                                           # markup and the code prove a class
                    for line_number, line in enumerate(lines, 1):
                        if relative == own_file and first <= line_number <= last:
                            continue                       # the definition never proves itself
                        for mode, pattern in patterns:     # every way of writing it
                            if pattern.search(line):       # found on this line
                                rows.append((name, kind, role, mode, relative,
                                             line_number, line.strip()[:80]))
                                if kind == "class" and role == "context":
                                    context_hits[name] = True  # the place exists
                                break                      # one finding per line is enough
            # A selector matches only where EVERY class of its chain exists.
            # A living subject under a context class nobody writes is a rule
            # that never applies - that exact case slipped through a real
            # check as alive. A context class with no occurrence anywhere in
            # the code is therefore written down as a finding of its own.
            for name in sorted(context_hits):              # every context class
                if not context_hits[name]:                 # written by nobody
                    rows.append((name, "class", "context", "context-missing",
                                 "", 0, "the context class is written nowhere "
                                 "in the code - the rule can never apply"))
            # The strongest evidence first, so that a cap - if one is ever
            # asked for - cuts the weakest and never the row that proves it.
            # In 2.1 a fixed cap of forty cut exactly the proving row of 132
            # statements, because the rows arrived in file order.
            rows.sort(key=lambda row: (row[2] != "subject", row[3] != "exact",
                                       row[4], row[5]))
            if limit and len(rows) > limit:                # a cap was asked for
                capped += 1                                # counted, and said out loud
                out.write("%d\t\t\t\tcapped\t\t0\t%d findings were left out by "
                          "--max-rows %d; this evidence is NOT complete\n"
                          % (statement_id, len(rows) - limit, limit))
                rows = rows[:limit]                        # only then is anything dropped
            if any(row[2] == "subject" for row in rows):   # the rule's own name was found
                with_subject += 1                          # counted
            elif rows:                                     # only the surroundings were found
                only_context += 1                          # which proves nothing by itself
            else:                                          # nothing found anywhere
                without += 1                               # which is not a verdict either
            for name, kind, role, mode, relative, line_number, excerpt in rows:
                out.write("%d\t%s\t%s\t%s\t%s\t%s\t%d\t%s\n"  # every finding that was kept
                          % (statement_id, name, kind, role, mode, relative,
                             line_number, excerpt))
            if not rows:                                   # say so, statement by statement
                out.write("%d\t\t\t\tnone-found\t\t0\tno evidence found - "
                          "this is a reason to look closer, not a verdict\n"
                          % statement_id)

    print("Style statements searched:   ", len(targets))   # what was covered
    print("Their own name was found:    ", with_subject)   # evidence for the rule itself
    print("Only their surroundings:     ", only_context)   # context alone proves nothing
    print("Nothing found at all:        ", without)        # to be settled by eyes
    if limit:                                              # only when one was asked for
        print("Statements cut by --max-rows:", capped)     # never a silent truncation
    print("Evidence file:", out_path)                      # where it all is
    print()
    print("Every row is evidence for the review of step 6, never a decision.")
    print("A row whose role is `context` says where the subject stands. It is "
          "not evidence that this rule is used.")
    return 0                                               # success


def main():
    """One command only: find."""
    parser = argparse.ArgumentParser(prog="style_links.py",
                                     description="SPIDER - step 6 helper")
    commands = parser.add_subparsers(dest="command", required=True)
    find_command = commands.add_parser("find")             # the only one
    find_command.add_argument("--analysis", required=True) # the analysis directory
    find_command.add_argument("--max-rows", type=int, default=0,  # 0 means no cap
                              help="cap the findings per statement; a cap is "
                                   "always written down in the file itself")
    arguments = parser.parse_args()                        # read them
    return find(arguments.analysis, arguments.max_rows)    # and do the work


if __name__ == "__main__":                                 # when run directly
    sys.exit(main())                                       # the exit code is the result
