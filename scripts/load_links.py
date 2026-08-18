"""SPIDER - step 4: the load graph, derived from the source itself.

    load_links.py derive --analysis <analysis directory>
        Works out which file loads which, and writes every link that loading
        creates into `load-links.tsv`, ready for `machine_links.py fill`.
        Changes nothing in the database.

Why this step exists. The unit of measurement of the whole method is the
top-level statement, and a top-level statement executes exactly when its file
is loaded. Loading is not a call: no call graph can express it, and a version
that knows only calls can prove at best half of what execution reaches. This
step proves the other half, from the snapshot alone - it needs no graph tool,
no Java and no network.

EXECUTING IS NOT NEEDING - the owner's rule this version stands on. Loading
a file runs every one of its top-level statements, but running a line that
only NAMES something - a constant, a function, a class, an import - proves
nothing about the program needing it. The name is needed when a needed
statement writes it, and that is the work of the name graph, not of this one.
Version 2.2 linked the loader to EVERY statement of the loaded file, and on a
real project that silently kept alive every unused constant, every unread
name and every descriptive text in every loaded file.

So a load link is written only where loading itself DOES the work:

  1. an import reaches the SIDE-EFFECT statements of the file it loads -
     the top-level calls and top-level flow, the lines that change something
     by merely running; naming lines get no link from loading;
  2. a style sheet's own @import statements run when the sheet loads, and so
     do its rules that write no class and no id - bare elements, :root -
     because they act on the page by being present;
  3. an entry point reaches nothing else by itself: the rest of its file is
     needed exactly as far as needed statements use it.

This step also writes two findings files: `loaded-files.txt` - every file
something provably loads - and `demoted-entries.txt` - every 'use client' or
'use server' directive whose file nothing imports. The bundler never reads a
directive in a file it never reaches, so such a directive is not an entry;
the owner's rule, measured: four screens of a real project were alive only
through this mistake.

What cannot be resolved is counted and named, never guessed at. A module name
that matches two files in the snapshot is reported as ambiguous and no link
is written for it.

Every line below carries a comment.
"""

import argparse                                  # reads the command line
import collections                               # counters and grouped lists
import io                                        # files, always UTF-8
import os                                        # paths and directory walking
import re                                        # the import patterns
import sys                                       # exit code and stdout

if hasattr(sys.stdout, "reconfigure"):           # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")     # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")     # so non-Latin text never breaks it

STATEMENTS = "statements.txt"                    # made by step 1
ENTRY_POINTS = "entry-points.txt"                # made by step 2
SELECTORS = "css-selectors.tsv"                  # made by step 1, for the style sheets
MACHINE = "machine"                              # where step 4 keeps its files
ALIASES = "aliases.txt"                          # optional: NAME<TAB>directory/
OUTPUT = "load-links.tsv"                        # what this program writes

CODE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
STYLE_EXTENSIONS = (".css",)                     # sheets, held to the asymmetry
TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SH_EXTENSIONS = (".sh",)                         # shell scripts

# What a load link is, for the contract table of step 4:
#   source - the statement whose execution causes the loading
#   target - a statement the loading causes to run
# Reachability travels source -> target, exactly as it does along a call.
KIND = "LOADS"                                   # the one kind this step writes

# --------------------------------------------------------------------------
# Reading what the earlier steps left
# --------------------------------------------------------------------------

def read_statements(analysis):
    """Every statement: its id, its file, and its text, in id order."""
    path = os.path.join(analysis, STATEMENTS)              # the statement list
    if not os.path.isfile(path):                           # step 1 has to be done
        raise SystemExit("No statement list: " + path)
    rows = []                                              # (id, file, text)
    with io.open(path, encoding="utf-8") as handle:        # always UTF-8
        for number, line in enumerate(handle, 1):          # count for the message
            line = line.rstrip("\n")                       # drop the newline
            if not line.strip():                           # a blank line
                continue                                   # is skipped
            columns = line.split(" | ", 3)                 # id, file, first-last, text
            if len(columns) < 3 or not columns[0].strip().isdigit():
                raise SystemExit(                          # a broken list is named
                    "Line " + str(number) + " of the statement list is broken: "
                    + line[:60])
            rows.append((int(columns[0]), columns[1].strip(),
                         columns[3] if len(columns) > 3 else ""))
    if not rows:                                           # an empty list proves nothing
        raise SystemExit("The statement list is empty: " + path)
    return rows                                            # in the order step 1 wrote


def read_entries(analysis):
    """The entry point ids, exactly as step 2 wrote them."""
    path = os.path.join(analysis, ENTRY_POINTS)            # where they are
    if not os.path.isfile(path):                           # step 2 has to be done
        raise SystemExit("No entry point list: " + path)
    entries = []                                           # in file order
    with io.open(path, encoding="utf-8") as handle:        # always UTF-8
        for number, line in enumerate(handle, 1):          # count for the message
            piece = line.strip()                           # one id per line
            if not piece:                                  # a blank line
                continue                                   # is skipped
            if not piece.isdigit():                        # anything that is not an id
                raise SystemExit("Line " + str(number)     # is named, never guessed at
                                 + " of the entry point list is not an id: "
                                 + piece[:40])
            entries.append(int(piece))                     # keep it
    if not entries:                                        # an empty list proves nothing
        raise SystemExit("The entry point list is empty: " + path)
    return entries                                         # in file order


NAMED_RE = re.compile(r"[.#]")                   # a class or an id


def read_unnamed_rules(analysis):
    """Style statements whose rules write no class and no id.

    `html { ... }`, `* { box-sizing: ... }`, `:root { ... }`,
    `textarea[data-x] { ... }` - a rule of elements, pseudo-classes and
    attributes acts on the document the moment its sheet is loaded. There is
    no class anyone writes for it, so no search could ever find one, and it
    must not be left waiting for evidence. A rule with a class or an id in it
    is NOT of this kind: those are names the markup writes, and step 6 checks
    whether it does.
    """
    unnamed = set()                                        # statement ids
    named = set()                                          # those with a name in them
    path = os.path.join(analysis, SELECTORS)               # written by step 1
    if not os.path.isfile(path):                           # a project with no sheets
        return unnamed                                     # has none of either
    with io.open(path, encoding="utf-8") as handle:        # always UTF-8
        next(handle, None)                                 # the heading line
        for line in handle:                                # every recorded name
            columns = line.rstrip("\n").split("\t")        # id, ordinal, selector, line
            if len(columns) < 3 or not columns[0].isdigit():
                continue                                   # a damaged row proves nothing
            number = int(columns[0])
            if NAMED_RE.search(columns[2]):                # it carries a name
                named.add(number)                          # so the rule is not unnamed
            else:
                unnamed.add(number)                        # nothing to write, nothing to find
    return unnamed - named                                 # one named part is enough


def read_aliases(analysis):
    """The path aliases of the project, when someone has written them down.

    A project may write `@/lib/x` for `frontend/lib/x`. The build tool knows
    this from a configuration file that is not application code and so is not
    in the snapshot. This step first tries every top directory of the snapshot
    and only needs the file when that leaves the answer ambiguous.
    """
    aliases = {}                                           # alias -> directory
    path = os.path.join(analysis, MACHINE, ALIASES)        # where it would be
    if not os.path.isfile(path):                           # the file is optional
        return aliases                                     # nothing stated
    with io.open(path, encoding="utf-8") as handle:        # always UTF-8
        for number, line in enumerate(handle, 1):          # count for the message
            line = line.rstrip("\n")                       # drop the newline
            if not line.strip():                           # a blank line
                continue                                   # is skipped
            parts = line.split("\t")                       # alias and directory
            if len(parts) != 2:                            # anything else is broken
                raise SystemExit(
                    "Line " + str(number) + " of " + path
                    + " is not 'alias<TAB>directory/': " + line[:60])
            aliases[parts[0].strip()] = parts[1].strip().rstrip("/") + "/"
    return aliases                                         # what was stated


# --------------------------------------------------------------------------
# Resolving a written import into a file of the snapshot
# --------------------------------------------------------------------------

def build_resolvers(files):
    """Two look-ups: python modules by dotted name, and plain paths."""
    by_module = collections.defaultdict(list)              # dotted name -> [file]
    for name in files:                                     # every file of the snapshot
        if not name.endswith(".py"):                       # only python has modules
            continue
        stem = name[:-len(".py")]                          # drop the extension
        if stem.endswith("/__init__"):                     # a package's own file
            stem = stem[:-len("/__init__")]                # is named by its directory
        parts = stem.split("/")                            # the path, piece by piece
        for start in range(len(parts)):                    # every suffix of it
            by_module[".".join(parts[start:])].append(name)
    return by_module                                       # ambiguity stays visible


def python_targets(module, importer, by_module, files):
    """Every snapshot file a written python import can mean."""
    if module.startswith("."):                             # a relative import
        depth = len(module) - len(module.lstrip("."))       # how many dots
        rest = module.lstrip(".")                          # what follows them
        base = os.path.dirname(importer)                   # the importer's directory
        for _ in range(depth - 1):                         # one dot is this directory
            base = os.path.dirname(base)                   # each further dot goes up
        stem = (base + "/" + rest.replace(".", "/")).strip("/") if rest else base
        found = []                                         # the two possible files
        for candidate in (stem + ".py", stem + "/__init__.py"):
            if candidate in files:                         # only what really exists
                found.append(candidate)
        return found, False                                # a path is never ambiguous
    hits = by_module.get(module, [])                       # by dotted name
    if len(hits) > 1:                                      # the same name twice
        return [], True                                    # ambiguous: nothing is written
    return list(hits), False                               # nothing, or exactly one


def ts_targets(target, importer, files, aliases, roots):
    """Every snapshot file a written TypeScript or JavaScript import can mean."""
    bases = []                                             # the paths to try
    if target.startswith("."):                             # relative to the importer
        bases.append(os.path.normpath(
            os.path.join(os.path.dirname(importer), target)).replace(os.sep, "/"))
    else:
        matched = False                                    # did a stated alias fit
        for alias, directory in aliases.items():           # the stated ones first
            if target.startswith(alias):                   # this alias fits
                bases.append(directory + target[len(alias):])
                matched = True                             # no guessing needed
        if not matched and not target[0].isalnum():        # an alias like `@/` or `~/`
            tail = target.split("/", 1)                    # the part after the alias
            if len(tail) == 2:                             # there is something after it
                for root in roots:                         # try every top directory
                    bases.append(root + "/" + tail[1])
        # a bare name is a package outside the project: nothing to try
    # A module written as "./x.js" compiles from "./x.ts" - the import names
    # the OUTPUT file while the source sits next to it. The written form is
    # tried first; its TypeScript twin is tried right after.
    JS_TO_TS = {".js": (".ts", ".tsx"), ".mjs": (".mts",), ".cjs": (".cts",),
                ".jsx": (".tsx",)}
    expanded = []                                          # base, then its twins
    for base in bases:
        expanded.append(base)
        for written, twins in JS_TO_TS.items():
            if base.endswith(written):
                for twin in twins:
                    expanded.append(base[:-len(written)] + twin)
    found = []                                             # every file a base can mean
    for base in expanded:                                  # each candidate path
        for suffix in ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css",
                       "/index.ts", "/index.tsx", "/index.js", "/index.jsx"):
            candidate = base + suffix                      # the written form
            if candidate in files and candidate not in found:
                found.append(candidate)                    # only what really exists
    return found                                           # in the order tried


def css_targets(target, importer, files):
    """Every snapshot sheet a written @import can mean."""
    if target.startswith(("http://", "https://", "//")):   # a sheet from the network
        return []                                          # is outside the project
    base = os.path.normpath(
        os.path.join(os.path.dirname(importer), target)).replace(os.sep, "/")
    return [base] if base in files else []                 # only what really exists


def sh_targets(target, importer, files):
    """Every snapshot script a written `source` can mean.

    A path with a variable in it is assembled at runtime; nothing is
    guessed for it, so it lands among the unresolved and is counted."""
    if "$" in target or target.startswith("/"):            # assembled, or absolute
        return []                                          # outside what a copy proves
    base = os.path.normpath(
        os.path.join(os.path.dirname(importer), target)).replace(os.sep, "/")
    return [base] if base in files else []                 # only what really exists


# --------------------------------------------------------------------------
# Reading the imports out of one statement
# --------------------------------------------------------------------------

PY_FROM = re.compile(r"^from\s+([.\w]+)\s+import\s+(.+)$")     # from X import a, b
PY_IMPORT = re.compile(r"^import\s+([.\w]+(?:\s*,\s*[.\w]+)*)")  # import a, b.c
TS_FROM = re.compile(r"""\bfrom\s*["']([^"']+)["']""")         # ... from "x"
TS_BARE = re.compile(r"""\bimport\s*["']([^"']+)["']""")       # import "x"
TS_CALL = re.compile(r"""\b(?:require|import)\s*\(\s*["']([^"']+)["']""")
CSS_IMPORT = re.compile(r"""@import\s+(?:url\(\s*)?["']([^"']+)["']""")
SH_SOURCE = re.compile(r"""(?:^|[;&|]\s*)(?:source|\.)\s+["']?([^\s"';|&]+)""",
                       re.M)                                   # source lib.sh  |  . lib.sh
PY_NAMES = re.compile(r"\w+")                                  # the names in a from-list


def imports_of(path, text):
    """Every module or path this statement loads, as written."""
    written = []                                           # in the order written
    if path.endswith(".py"):                               # python
        match = PY_FROM.match(text)                        # from X import a, b
        if match:
            module, names = match.group(1), match.group(2)
            written.append(module)                         # the module itself
            head = module if module.endswith(".") else module + "."
            for name in PY_NAMES.findall(names.split("#")[0]):
                if name not in ("import", "as"):           # a name, not a keyword
                    written.append(head + name)            # may be a submodule
            return written
        match = PY_IMPORT.match(text)                      # import a, b.c
        if match:
            for piece in match.group(1).split(","):        # each module named
                piece = piece.strip()
                if piece:
                    written.append(piece)
        return written
    if path.endswith(TS_EXTENSIONS):                       # typescript and javascript
        for pattern in (TS_FROM, TS_BARE, TS_CALL):        # every way of writing it
            for found in pattern.findall(text):
                written.append(found)
        return written
    if path.endswith(STYLE_EXTENSIONS):                    # a style sheet
        for found in CSS_IMPORT.findall(text):             # @import "x"
            written.append(found)
        return written
    if path.endswith(SH_EXTENSIONS):                       # a shell script
        for found in SH_SOURCE.findall(text):              # source x  |  . x
            written.append(found)
        return written
    return written                                         # any other file loads nothing


# --------------------------------------------------------------------------
# derive
# --------------------------------------------------------------------------

PY_NAMING = ("def ", "class ", "import ", "from ", "@", '"""', "'''", "#",
             'r"""', "r'''")                               # lines that only name or decorate
PY_ASSIGN_RE = re.compile(r"^[\w.,\s\[\]\(\)]+(?::[^=]+)?=(?!=)")  # an assignment
TS_NAMING = ("import ", "export ", "function ", "class ", "interface ",
             "type ", "enum ", "const ", "let ", "var ", "//", "/*",
             '"use client"', "'use client'", '"use server"', "'use server'")
TS_CALL_RE = re.compile(r"^[A-Za-z_$][\w$.]*\s*\(")        # a bare call at the top level


def side_effect(target_file, text):
    """True when the statement DOES something by merely running at load.

    Executing is not needing - the owner's rule. A line that names something
    (a definition, an assignment, an import, text) is needed only when a
    needed statement uses the name, and the name graph proves that. A line
    that CALLS something at the top level, or opens top-level flow, changes
    the world the moment its file loads - only those lines the loading itself
    proves.
    """
    stripped = text.lstrip()
    if not stripped:                                       # nothing at all
        return False
    if target_file.endswith(".py"):                        # python
        if stripped.startswith("from __future__ "):        # changes how the file parses
            return True                                    # by merely standing there
        if stripped.startswith(PY_NAMING):                 # names or documents
            return False
        if PY_ASSIGN_RE.match(stripped):                   # binds a name
            return False
        return True                                        # calls, flow: it acts
    if target_file.endswith(SH_EXTENSIONS):                # shell
        if re.match(r"^(?:function\s+[A-Za-z_]\w*|[A-Za-z_]\w*\s*\(\))",
                    stripped):                             # a function definition
            return False                                   # names, waits to be called
        if stripped.startswith("#"):                       # comment or shebang
            return False                                   # data, not an act
        return True                                        # commands act when sourced
    if stripped.startswith(('import "', "import '")):      # a bare import is loaded
        return True                                        # for its side effect alone
    if stripped.startswith(("declare module", "declare global")):
        return True                                        # an augmentation acts by
    if stripped.startswith(TS_NAMING):                     # being present; the rest
        return False                                       # names or documents
    if stripped.startswith(("/*", "//", "declare ", "namespace ", "module ")):
        return False                                       # text and declarations
    return True                                            # calls, member assignments,
                                                           # top-level flow: it acts


def loadable_targets(target_file, by_file, sheet_loaders, unnamed_rules,
                     detonators=None):
    """Which statements of a loaded file the loading itself proves.

    A code file: its side-effect statements - the lines that act by
    running - and its import statements that load a file which itself
    holds side effects, because evaluating the module evaluates what it
    imports: such an import acts by the very act of loading. The registries
    that self-register at load - a code fix, a refactoring - are reached
    through exactly that chain and through nothing else. The remaining
    naming lines wait for the name graph. A style sheet: the at-rules that
    pull in further sheets, and the rules that write no class and no id -
    both act by being present. A named rule waits for the markup to write
    its name, which is step 6's work. Without these lines no unused name
    and no dead style rule could ever be found.
    """
    if target_file.endswith(STYLE_EXTENSIONS):             # the sheet asymmetry
        return sorted(set(sheet_loaders.get(target_file, []))
                      | set(number for number, _ in by_file.get(target_file, [])
                            if number in unnamed_rules))
    acting = [number for number, text in by_file.get(target_file, [])
              if side_effect(target_file, text)]           # what acts by running
    if detonators:                                         # what acts by loading
        acting.extend(number for number in detonators.get(target_file, ())
                      if number not in acting)
    return sorted(acting)


def derive(analysis):
    """Writes every load link the snapshot proves."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    rows = read_statements(analysis)                       # the statement list
    entries = read_entries(analysis)                       # where the framework starts
    aliases = read_aliases(analysis)                       # stated path aliases, if any
    unnamed_rules = read_unnamed_rules(analysis)           # rules that name nothing

    by_file = collections.defaultdict(list)                # file -> [(id, text)]
    file_of = {}                                           # id -> file
    for number, name, text in rows:                        # every statement
        by_file[name].append((number, text))               # grouped by its file
        file_of[number] = name                             # and remembered
    files = set(by_file)                                   # every file in the list
    roots = sorted(set(name.split("/", 1)[0] for name in files if "/" in name))
    by_module = build_resolvers(files)                     # python modules by name

    sheet_loaders = collections.defaultdict(list)          # sheet -> its own @import ids
    for name in files:                                     # every style sheet
        if not name.endswith(STYLE_EXTENSIONS):
            continue
        for number, text in by_file[name]:                 # every statement in it
            if CSS_IMPORT.search(text):                    # that pulls in a sheet
                sheet_loaders[name].append(number)         # is run when the sheet loads

    links = []                                             # (source, target)
    counts = collections.Counter()                         # what happened to each import
    unresolved = collections.Counter()                     # what could not be resolved
    ambiguous = []                                         # named, never guessed at
    imported_targets = set()                               # every file an import resolves to

    # First pass: every import, resolved once. The edges are written in the
    # second pass, because which statements a loading proves depends on which
    # files act at load - and that is a chain: a file acts when a statement
    # of its own acts, or when an import of its own loads a file that acts.
    resolved_imports = []                                  # (unit, its file, target file)
    for number, name, text in rows:                        # every statement in turn
        for written in imports_of(name, text):             # everything it loads
            counts["written imports"] += 1                 # counted in total
            if name.endswith(".py"):                       # python resolution
                targets, is_ambiguous = python_targets(
                    written, name, by_module, files)
                if is_ambiguous:                           # two files of the same name
                    ambiguous.append((number, name, written))
                    counts["ambiguous"] += 1               # nothing is written for it
                    continue
            elif name.endswith(TS_EXTENSIONS):             # typescript and javascript
                targets = ts_targets(written, name, files, aliases, roots)
            elif name.endswith(STYLE_EXTENSIONS):          # a sheet loading a sheet
                targets = css_targets(written, name, files)
            elif name.endswith(SH_EXTENSIONS):             # a script sourcing a script
                targets = sh_targets(written, name, files)
            else:                                          # any other file
                targets = []                               # loads nothing
            if not targets:                                # outside the project, or a package
                counts["outside the snapshot"] += 1        # counted, never guessed at
                unresolved[written.split("/")[0][:40]] += 1
                continue
            counts["resolved"] += 1                        # a real file of the project
            for target_file in targets:                    # every file it can mean
                if target_file == name:                    # a file loading itself
                    continue                               # joins nothing
                imported_targets.add(target_file)          # imported, links or not
                resolved_imports.append((number, name, target_file))

    # The chain of acting files, to a standstill: a file acts when one of
    # its statements acts by running, or when an import of its own loads a
    # file that acts. A sheet acts by being present at all.
    acts = set()                                           # the files that act
    for name in files:
        if name.endswith(STYLE_EXTENSIONS):
            if sheet_loaders.get(name) or any(
                    number in unnamed_rules for number, _ in by_file[name]):
                acts.add(name)
        elif any(side_effect(name, text) for _, text in by_file[name]):
            acts.add(name)
    while True:                                            # propagate up the imports
        grew = False
        for number, name, target_file in resolved_imports:
            if target_file in acts and name not in acts:
                acts.add(name)
                grew = True
        if not grew:
            break
    detonators = collections.defaultdict(list)             # file -> import units that
    for number, name, target_file in resolved_imports:     # load a file that acts
        if target_file in acts:
            detonators[name].append(number)

    # Second pass: the edges themselves.
    for number, name, target_file in resolved_imports:
        for other in loadable_targets(target_file, by_file, sheet_loaders,
                                      unnamed_rules, detonators):
            if other != number:                            # never itself
                links.append((number, other))              # the loading reaches it

    # An entry point proves only itself: the rest of its file is needed
    # exactly as far as needed statements use it, and the name graph carries
    # that. What the entry list DOES settle here is the directive rule:
    # a 'use client' or 'use server' directive is read by the bundler only
    # when the bundler reaches the file, and the bundler reaches a file that
    # something imports. A directive in a file nothing imports, with no other
    # entry in that file, is not an entry - it is a finding.
    text_of = {number: text for number, name, text in rows}
    DIRECTIVES = ('"use client";', "'use client';", '"use server";',
                  "'use server';", '"use client"', "'use client'")
    imported_files = set(imported_targets)                 # what an import resolves to,
    # whether or not the loading found side effects inside - a file with no
    # side effects is imported all the same, and its directive stands.
    entry_files = collections.defaultdict(list)            # file -> its entry ids
    for entry in entries:                                  # every entry point
        if entry in file_of:                               # that the list knows
            entry_files[file_of[entry]].append(entry)      # grouped by its file
    demoted = []                                           # (id, file) - not entries at all
    for name, found in sorted(entry_files.items()):        # every file with an entry
        directives_here = [e for e in found
                           if text_of.get(e, "").strip() in DIRECTIVES]
        others_here = [e for e in found if e not in directives_here]
        if directives_here and not others_here and name not in imported_files:
            demoted.extend((e, name) for e in directives_here)
            continue                                       # a file that never loads
        # The framework loaded the file to reach its entry, so the file's
        # SIDE-EFFECT statements ran - the bare imports, the future imports,
        # the top-level calls - and so did its imports of files that act,
        # because evaluating the module evaluates what it imports. Only
        # those; the naming lines of an entry file are needed exactly as
        # far as needed statements use them.
        first = min(found)                                 # one entry proves the loading
        exploding = set(detonators.get(name, ()))          # imports that load acting files
        for other, other_text in by_file[name]:            # every statement of the file
            if other == first:
                continue
            if side_effect(name, other_text) or other in exploding:
                links.append((first, other))               # the loading ran it

    demoted_path = os.path.join(analysis, "demoted-entries.txt")
    with io.open(demoted_path, "w", encoding="utf-8", newline="\n") as out:
        for entry, name in demoted:                        # id TAB file TAB reason
            out.write("%d\t%s\tdirective in a file nothing imports\n"
                      % (entry, name))
    loaded_path = os.path.join(analysis, "loaded-files.txt")
    with io.open(loaded_path, "w", encoding="utf-8", newline="\n") as out:
        for name in sorted(imported_files):                # every provably loaded file
            out.write(name + "\n")

    seen = set()                                           # the same link once
    kept = []                                              # what is written down
    for source, target in links:                           # every link found
        if (source, target) in seen:                       # already written
            counts["repeated"] += 1                        # counted
            continue                                       # and written once
        seen.add((source, target))                         # remembered
        kept.append((source, target))                      # and kept

    out_path = os.path.join(analysis, OUTPUT)              # where the links go
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for source, target in sorted(kept):                # in a fixed order
            out.write("%d\t%d\t%s\n" % (source, target, KIND))

    reached_files = set(file_of[t] for _, t in kept)       # what any load link enters
    print("Statements read:              ", len(rows))     # from the list
    print("Written imports found:        ", counts["written imports"])
    print("   resolved to a project file:", counts["resolved"])
    print("   outside the snapshot:      ", counts["outside the snapshot"])
    print("   ambiguous, nothing written:", counts["ambiguous"])
    print("Style rules that name nothing:", len(unnamed_rules))
    print()
    print("Load links written:           ", len(kept))
    print("   repeated, written once:    ", counts["repeated"])
    print("Files any load link enters:   ", len(reached_files), "of", len(files))
    print("Files something loads:        ", len(imported_files))
    if demoted:                                            # named one by one - findings
        print()
        print("DEMOTED ENTRIES - a directive in a file nothing imports is not "
              "an entry:")
        for entry, name in demoted:
            print("   statement %d in %s" % (entry, name))
    if ambiguous:                                          # named one by one
        print()
        print("AMBIGUOUS - two files of the snapshot carry the same module name:")
        for number, name, written in ambiguous[:20]:       # the first twenty
            print("   statement %d in %s writes %s" % (number, name, written))
    if unresolved:                                         # the biggest groups
        print()
        print("Outside the snapshot, by first piece (packages and framework):")
        for written, count in unresolved.most_common(10):
            print("   %-32s %d" % (written, count))
    print()
    print("Load links file:", out_path)
    print("Nothing was written into the database. Run machine_links.py fill next.")
    return 0                                               # success


# --------------------------------------------------------------------------

def main():
    """One command only: derive."""
    parser = argparse.ArgumentParser(prog="load_links.py",
                                     description="SPIDER - step 4, the load graph")
    commands = parser.add_subparsers(dest="command", required=True)
    derive_command = commands.add_parser("derive")         # the only one
    derive_command.add_argument("--analysis", required=True)  # the analysis directory
    arguments = parser.parse_args()                        # read them
    return derive(arguments.analysis)                      # and do the work


if __name__ == "__main__":                                 # when run directly
    sys.exit(main())                                       # the exit code is the result
