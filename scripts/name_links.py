"""SPIDER - step 4: the name graph, derived from the source itself.

    name_links.py derive --analysis <analysis directory>
        Works out, for every statement that DEFINES a name and for every
        statement that IMPORTS names, which statements write those names, and
        writes the links into `name-links.tsv`, ready for
        `machine_links.py fill`. Changes nothing in the database.

Why this graph exists. Executing is not needing - the owner's rule. A line
that names something (a constant, a function, a class, an import) is needed
exactly when a needed statement writes its name. The call graph proves the
calls it can resolve; the load graph proves what acts by loading; this graph
proves the remaining and largest part: name use.

Every link is written USER -> NAMED STATEMENT, in the one stored direction -
the user needs what it names. Reachability travels only that way, so an
unused definition stays unreached no matter how alive its file is, and a
definition used only by dead code stays unreached with it.

The collisions that lied in real checks are shut out mechanically:

  - a statement that itself DEFINES the same name is never its user - two
    files may both define `_setting_string`, and neither uses the other;
  - a Python name is used across files only where the using file IMPORTS
    that name from the defining module, or holds the module under an alias
    and writes `alias.name`;
  - a TypeScript name is used across files only where the using file's
    import resolves to the defining file;
  - names defined in the Django settings module are the one stated
    exception: the framework hands them to any file through
    `settings.NAME` and `getattr(settings, "NAME")`, quoted included;
  - an import line is never a user of what it imports - it is needed when
    statements of ITS OWN file use the names it brings, and those links are
    written here too.

Every line below carries a comment.
"""

import argparse                                  # reads the command line
import collections                               # counters and grouped lists
import io                                        # files, always UTF-8
import os                                        # paths
import re                                        # the searches themselves
import sys                                       # exit code and stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the scripts directory
import load_links                                # the shared resolvers of step 4

if hasattr(sys.stdout, "reconfigure"):           # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")     # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")     # so non-Latin text never breaks it

STATEMENTS = "statements.txt"                    # made by step 1
OUTPUT = "name-links.tsv"                        # what this program writes
KIND = "USES"                                    # the one kind this step writes

PY_EXTENSIONS = (".py",)                         # python files
TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")  # the rest of the code
SH_EXTENSIONS = (".sh",)                         # shell scripts
SETTINGS_FILE = "backend/config/settings.py"     # the framework's stated exception
SH_FUNC = re.compile(r"^\s*(?:function\s+([A-Za-z_]\w*)|([A-Za-z_]\w*)\s*\(\))")

# what a statement DEFINES, by language
PY_DEF = re.compile(r"^\s*(?:@[^\n]{0,200}\s+)*(?:async\s+)?(?:def|class)\s+(\w+)")
PY_ASSIGN = re.compile(r"^(\w+)(?:\s*:\s*[^=]+)?\s*=(?!=)")
TS_DEF = re.compile(r"^\s*export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
                    r"(?:abstract\s+)?"
                    r"(?:function\*?|class|interface|const\s+enum|enum"
                    r"|namespace|module)\s+(\w+)")
TS_PLAIN = re.compile(r"^\s*(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?"
                      r"(?:function\*?|class|interface|const\s+enum|enum"
                      r"|namespace|module)\s+(\w+)")
TS_CONST = re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?(?:const|let|var)\s+(\w+)")
TS_COMMENT = re.compile(r"^(?:\s*/\*.*?\*/\s*|\s*//[^\n]*\n\s*)+", re.S)
TS_TYPE = re.compile(r"^\s*(?:export\s+)?type\s+(\w+)")
TS_DEFAULT = re.compile(r"^\s*export\s+default\b")

# what a statement IMPORTS, by language
PY_FROM = re.compile(r"^from\s+([.\w]+)\s+import\s+(.+)$", re.S)
PY_IMPORT = re.compile(r"^import\s+([\w.]+)(?:\s+as\s+(\w+))?")
TS_IMPORT = re.compile(r"""^\s*import\s+(?:type\s+)?(.+?)\s+from\s+["']([^"']+)["']""", re.S)
# A re-export loads a module and publishes names out of it, bringing nothing
# into its own scope. It is the whole wiring of a codebase built on barrel
# files: `export * from "./core.js"`, chained until the file that defines.
TS_REEXPORT = re.compile(r"""^\s*export\s+(?:type\s+)?(\*(?:\s+as\s+\w+)?"""
                         r"""|\{[^}]*\})\s*from\s+["']([^"']+)["']""", re.S)

DOC_STARTS = ('"""', "'''", 'r"""', "r'''")      # descriptive text defines nothing


def read_statements(analysis):
    """Every statement: id, file and text, exactly as step 1 wrote them."""
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
                raise SystemExit("Line " + str(number)     # a broken list is named
                                 + " of the statement list is broken: " + line[:60])
            rows.append((int(columns[0]), columns[1].strip(),
                         columns[3] if len(columns) > 3 else ""))
    if not rows:                                           # an empty list proves nothing
        raise SystemExit("The statement list is empty: " + path)
    return rows


def defined_names(name, text):
    """The (name, exported) pairs one statement defines, or [].

    Exported matters because a re-export carries only the exported names
    onward: a module-local `function f` of one file never shadows the
    published `export function f` of the file after it in a barrel. In
    python every top-level definition is importable, so every one counts
    as exported.
    """
    stripped = text.lstrip()
    if stripped.startswith(DOC_STARTS):                    # descriptive text
        return []
    if name.endswith(PY_EXTENSIONS):                       # python
        if stripped.startswith(("import ", "from ")):      # an import defines locally,
            return []                                      # handled as an import below
        if stripped.startswith("@"):                       # a decorated def or class:
            match = re.search(r"(?<![\w.])(?:async\s+)?(?:def|class)\s+(\w+)",
                              text.replace("\\n", " "))    # the name stands after the
            if match:                                      # decorators, not at the start
                return [(match.group(1), True)]
            return []
        match = PY_DEF.match(text)                         # a def or a class
        if match:
            return [(match.group(1), True)]
        match = PY_ASSIGN.match(stripped)                  # a top-level assignment
        if match:
            return [(match.group(1), True)]
        return []
    if name.endswith(TS_EXTENSIONS):                       # typescript and javascript
        text = TS_COMMENT.sub("", text)                    # `/** @internal */ export
        stripped = text.lstrip()                           # function f(` defines f
        if stripped.startswith("import"):                  # the same for imports
            return []
        exported = stripped.startswith("export")           # what a barrel may carry
        for pattern in (TS_DEF, TS_PLAIN, TS_TYPE, TS_CONST):
            match = pattern.match(text)
            if match:
                if stripped.startswith("export default"):  # named AND the default
                    return [(match.group(1), True), ("(default)", True)]
                return [(match.group(1), exported)]
        if TS_DEFAULT.match(stripped):                     # an anonymous default export
            return [("(default)", True)]                   # addressable by the import side
        return []
    if name.endswith(SH_EXTENSIONS):                       # shell
        match = SH_FUNC.match(stripped)                    # a function definition
        if match:                                          # names what a caller writes;
            return [(match.group(1) or match.group(2), True)]  # sourcing exports it
        return []
    return []                                              # style sheets go their own way


def imported_locals(name, text, by_module, files, aliases, roots):
    """What an import statement brings in: locals, and where each comes from.

    Returns (locals, module_aliases): `locals` maps a local name to the
    defining file and the original name; `module_aliases` maps an alias to a
    module file, for `alias.name` use.
    """
    stripped = text.lstrip()
    locals_, module_aliases = {}, {}
    if name.endswith(PY_EXTENSIONS):
        match = PY_FROM.match(stripped)
        if match:
            module, names = match.groups()
            targets, ambiguous = load_links.python_targets(
                module, name, by_module, files)
            for piece in re.split(r"[,\(\)]", names.split("#")[0]):
                piece = piece.strip()
                if not piece or piece == "*":
                    continue
                parts = piece.split(" as ")
                original = parts[0].strip()
                local = parts[-1].strip()
                if not re.fullmatch(r"\w+", local or ""):
                    continue
                sub = (module + original if module.endswith(".")
                       else module + "." + original)      # "from apps.x import views"
                sub_targets, _ = load_links.python_targets(
                    sub, name, by_module, files)
                if sub_targets:                            # the name IS a module
                    module_aliases[local] = sub_targets[0]
                elif targets and not ambiguous:            # a name from the module
                    locals_[local] = (targets[0], original)
                else:                                      # a package outside the project:
                    locals_[local] = (None, original)      # the import is still needed
            return locals_, module_aliases                 # exactly when the name is used
        match = PY_IMPORT.match(stripped)
        if match:
            module, alias = match.groups()
            targets, ambiguous = load_links.python_targets(
                module, name, by_module, files)
            if targets and not ambiguous:
                module_aliases[alias or module.split(".")[0]] = targets[0]
        return locals_, module_aliases
    match = TS_IMPORT.match(stripped)
    if match:
        clause, target_text = match.groups()
        targets = load_links.ts_targets(target_text, name, files, aliases, roots)
        target = targets[0] if targets else None           # None: a package import,
        star = re.match(r"\*\s+as\s+(\w+)", clause.strip())  # still needed when used
        if star:
            if target is not None:
                module_aliases[star.group(1)] = target
            else:                                          # a whole package under a name
                locals_[star.group(1)] = (None, star.group(1))
            return locals_, module_aliases
        head = clause.split("{")[0].strip().rstrip(",").strip()
        if head and re.fullmatch(r"\w+", head):            # the default import
            locals_[head] = (target, "(default)")
        braces = re.search(r"\{([^}]*)\}", clause, re.S)
        if braces:
            for piece in braces.group(1).split(","):
                piece = piece.replace("type ", " ").strip()
                if not piece:
                    continue
                parts = piece.split(" as ")
                original = parts[0].strip()
                local = parts[-1].strip()
                if re.fullmatch(r"\w+", local or ""):
                    locals_[local] = (target, original)
    return locals_, module_aliases


def embedded_imports(name, text, by_module, files, aliases, roots):
    """Imports written INSIDE a python statement's body, at any indentation.

    `def get_current_user_context(...): from apps.accounts.services import
    get_permission_summary` is the codebase's own way around circular
    imports, and it is an import all the same: the containing statement
    both brings the name in and uses it. Without this, the definition it
    reaches for stays unlinked and a living function lands on the list."""
    if not name.endswith(PY_EXTENSIONS):                   # python only; the ts
        return {}, {}                                      # side has no such idiom here
    locals_, module_aliases = {}, {}
    NAME_LIST = (r"\(\s*[\w\s,]*?\)"                       # a bracketed list, or
                 r"|[\w.]+(?:\s+as\s+\w+)?"                # one name, then more
                 r"(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*")    # after commas only
    pieces = []                                            # rebuilt one-line imports
    for match in re.finditer(r"(?<![\w.])from\s+([\w.]+)\s+import\s+("
                             + NAME_LIST + r")", text):
        pieces.append("from %s import %s" % match.groups())
    for match in re.finditer(r"(?<![\w.])import\s+([\w.]+(?:\s+as\s+\w+)?)",
                             text):
        before = text[:match.start()].rstrip()             # not the tail of a
        if before.endswith("from") or before.endswith("."):  # from-import
            continue
        pieces.append("import " + match.group(1))
    for piece in pieces:
        piece_locals, piece_aliases = imported_locals(
            name, piece, by_module, files, aliases, roots)
        for local, value in piece_locals.items():
            if value[0] is not None:                       # only a name resolved to
                locals_.setdefault(local, value)           # a project file can link
        for alias, value in piece_aliases.items():
            module_aliases.setdefault(alias, value)
    return locals_, module_aliases


IDENT = r"[A-Za-z0-9_]"                          # a code identifier goes on through these


def boundary_pattern(name):
    """The name on identifier boundaries - quoted text matches too."""
    return re.compile(r"(?<!" + IDENT + r")" + re.escape(name)
                      + r"(?!" + IDENT + r")")


def defines_same(text, name, is_python):
    """True when this line is itself a definition of that very name."""
    stripped = text.lstrip()
    if is_python:
        if stripped.startswith("@"):                       # decorators first, then
            match = re.search(r"(?<![\w.])(?:async\s+)?(?:def|class)\s+(\w+)",
                              text.replace("\\n", " "))    # the definition itself
            return bool(match and match.group(1) == name)
        match = PY_DEF.match(text)
        if match and match.group(1) == name:
            return True
        match = PY_ASSIGN.match(stripped)
        return bool(match and match.group(1) == name)
    text = TS_COMMENT.sub("", text)                        # comments first
    for pattern in (TS_DEF, TS_PLAIN, TS_TYPE, TS_CONST):
        match = pattern.match(text)
        if match and match.group(1) == name:
            return True
    return False


def derive(analysis):
    """Writes every name link the snapshot proves."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    rows = read_statements(analysis)                       # the statement list
    aliases = load_links.read_aliases(analysis)            # stated path aliases

    by_file = collections.defaultdict(list)                # file -> [(id, text)]
    for number, name, text in rows:                        # every statement
        by_file[name].append((number, text))
    files = set(by_file)                                   # every file in the list
    roots = sorted(set(name.split("/", 1)[0] for name in files if "/" in name))
    by_module = load_links.build_resolvers(files)          # python modules by name

    # 1. every definition: (file, name) -> EVERY statement that carries it.
    # One name can stand on several statements - two overload signatures
    # and the implementation are three statements of one function, and a
    # user needs them all: remove the implementation and the program is
    # broken, remove a signature and a call stops compiling. Which names a
    # file EXPORTS is kept apart, because only those travel onward through
    # an import or a re-export.
    definitions = collections.defaultdict(dict)            # file -> {name: (ids)}
    exported_names = collections.defaultdict(set)          # file -> {name}
    for number, name, text in rows:
        for defined, exported in defined_names(name, text):
            definitions[name].setdefault(defined, []).append(number)
            if exported:
                exported_names[name].add(defined)

    # 2. every import: what it brings, and from where. Re-exports are read
    # in the same pass: they bring nothing into their own scope, they only
    # publish, so they go into the republish maps and never into brought.
    import_rows = {}                                       # id -> (file, locals, aliases)
    imports_by_file = collections.defaultdict(list)        # file -> [id]
    importers_of = collections.defaultdict(set)            # def file -> {user files}
    republish_star = collections.defaultdict(list)         # file -> [(unit, target)]
    republish_named = collections.defaultdict(dict)        # file -> {published:
    republish_local = collections.defaultdict(dict)        #   (unit, target, original)}
    file_imports = collections.defaultdict(dict)           # file -> {local: how it came}
    reexport_of = {}                                       # unit -> (kind, target, names)
    for number, name, text in rows:
        stripped = text.lstrip()
        if name.endswith(TS_EXTENSIONS) and stripped.startswith("export"):
            match = TS_REEXPORT.match(stripped)
            if not match:
                # A bare `export { X };` publishes the file's OWN local X -
                # defined here or brought in by an import. The emulated
                # namespaces stand on exactly this: `import * as Completions
                # from "./ts.Completions.js"; export { Completions };`.
                bare = re.match(r"^export\s+(?:type\s+)?\{([^}]*)\}\s*;?\s*$",
                                stripped)
                if bare:
                    for piece in bare.group(1).split(","):
                        piece = piece.replace("type ", " ").strip()
                        if not piece:
                            continue
                        parts = piece.split(" as ")
                        local = parts[0].strip()
                        published = parts[-1].strip()
                        if re.fullmatch(r"\w+", published or ""):
                            republish_local[name][published] = (number, local)
                continue                                   # an ordinary definition
            clause, target_text = match.groups()
            targets = load_links.ts_targets(target_text, name, files,
                                            aliases, roots)
            if not targets:
                continue                                   # a package outside the project
            target = targets[0]
            clause = clause.strip()
            if clause.startswith("*"):
                star_as = re.match(r"\*\s+as\s+(\w+)", clause)
                if star_as:                                # publishes one name for
                    republish_named[name][star_as.group(1)] = (number, target, "*")
                    reexport_of[number] = ("module", target, ())
                else:                                      # publishes everything
                    republish_star[name].append((number, target))
                    reexport_of[number] = ("star", target, ())
            else:                                          # export { a, b as c } from
                published_here = []
                for piece in clause.strip("{}").split(","):
                    piece = piece.replace("type ", " ").strip()
                    if not piece:
                        continue
                    parts = piece.split(" as ")
                    original = parts[0].strip()
                    published = parts[-1].strip()
                    if re.fullmatch(r"\w+", published or ""):
                        republish_named[name][published] = (number, target,
                                                            original)
                        published_here.append(original)
                reexport_of[number] = ("named", target, tuple(published_here))
            importers_of[target].add(name)
            continue
        if name.endswith(SH_EXTENSIONS):                   # a script sourcing a script
            locals_, module_aliases = {}, {}               # gains its functions
            for written in load_links.SH_SOURCE.findall(text):
                for target in load_links.sh_targets(written, name, files):
                    for function_name in definitions.get(target, {}):
                        locals_.setdefault(function_name, (target, function_name))
        elif (stripped.startswith(("import ", "from ")) or
                (name.endswith(TS_EXTENSIONS) and stripped.startswith("import"))):
            locals_, module_aliases = imported_locals(
                name, text, by_module, files, aliases, roots)
        elif "import " in text and not stripped.startswith(DOC_STARTS):
            locals_, module_aliases = embedded_imports(    # an import inside the body;
                name, text, by_module, files, aliases, roots)  # never inside prose
        else:
            continue                                       # no import here at all
        if not locals_ and not module_aliases:
            continue                                       # a package outside the project
        import_rows[number] = (name, locals_, module_aliases)
        imports_by_file[name].append(number)
        for local, (target, original) in locals_.items():
            importers_of[target].add(name)
            file_imports[name].setdefault(local, ("named", number, target,
                                                  original))
        for alias, target in module_aliases.items():
            importers_of[target].add(name)
            file_imports[name].setdefault(alias, ("module", number, target))

    # The chase: where is this name really defined, seen from this file?
    # Straight definitions first, then the named re-exports, then the bare
    # `export { X }` of the file's own locals, then the star re-exports in
    # the order they stand. Returns three things: the defining statement,
    # every statement the name flows through - the conduits: a user needs
    # the whole chain, or the name never arrives - and, when the name is a
    # whole module under one label, the module's file, so that the caller
    # can resolve `label.attr` against it.
    MISS = ((), (), None)
    resolved_cache = {}

    def resolve_name(file_name, wanted, trail=()):
        """(defining units, conduit units, module file or None)."""
        key = (file_name, wanted)
        if key in resolved_cache:
            return resolved_cache[key]
        if file_name in trail:                             # a circle of barrels
            return MISS
        trail = trail + (file_name,)
        # Cross-file resolution sees only what the file EXPORTS: an import
        # and a re-export carry the exported names and nothing else. The
        # file's own module-locals are linked by the same-file pass.
        own = (definitions.get(file_name, {}).get(wanted)
               if wanted in exported_names.get(file_name, ()) else None)
        if own:
            answer = (tuple(own), (), None)
            resolved_cache[key] = answer
            return answer
        named = republish_named.get(file_name, {}).get(wanted)
        if named is not None:
            unit, target, original = named
            if original == "*":                            # a whole module under a name
                resolved_cache[key] = ((unit,), (), target)  # the publishing statement
                return ((unit,), (), target)               # stands for the module
            def_ids, conduits, module = resolve_name(target, original, trail)
            answer = ((def_ids, (unit,) + conduits, module)
                      if def_ids else MISS)
            resolved_cache[key] = answer
            return answer
        bare = republish_local.get(file_name, {}).get(wanted)
        if bare is not None:                               # export { X } of a local
            unit, local = bare
            came = file_imports.get(file_name, {}).get(local)
            if came is not None and came[0] == "module":   # import * as X, exported
                _, import_unit, target = came
                answer = ((import_unit,), (unit,), target)  # the import stands for
                resolved_cache[key] = answer               # the module it holds
                return answer
            if came is not None:                           # a named import, exported
                _, import_unit, target, original = came
                def_ids, conduits, module = resolve_name(target, original, trail)
                answer = ((def_ids, (unit, import_unit) + conduits, module)
                          if def_ids else MISS)
                resolved_cache[key] = answer
                return answer
            own_local = definitions.get(file_name, {}).get(local)
            if own_local:                                  # a local definition,
                answer = (tuple(own_local), (unit,), None)  # published under a
                resolved_cache[key] = answer               # different name
                return answer
        for unit, target in republish_star.get(file_name, ()):
            def_ids, conduits, module = resolve_name(target, wanted, trail)
            if def_ids:
                answer = (def_ids, (unit,) + conduits, module)
                resolved_cache[key] = answer
                return answer
        resolved_cache[key] = MISS
        return MISS

    links = []                                             # (user, named statement)
    counts = collections.Counter()                         # what was written, by way

    # The surface. An entry point that is a re-export is the statement the
    # OUTSIDE reads: a package's public face. The outside may write any name
    # published through it, so the entry needs every one of them - the
    # definition, and the chain each name rides through. Nothing else gets
    # surface links: an internal barrel is needed only as far as internal
    # users write the names that flow through it.
    entry_path = os.path.join(analysis, "entry-points.txt")
    entry_ids = []
    if os.path.isfile(entry_path):                         # step 2's list, when present
        with io.open(entry_path, encoding="utf-8") as handle:
            entry_ids = [int(piece) for piece in handle.read().split()
                         if piece.strip().isdigit()]

    names_cache = {}

    def all_published(file_name, trail=()):
        """Every name this file publishes, its own definitions included."""
        if file_name in names_cache:
            return names_cache[file_name]
        if file_name in trail:                             # a circle of barrels
            return set()
        trail = trail + (file_name,)
        published = set(exported_names.get(file_name, ()))  # only what it exports
        published.update(republish_named.get(file_name, ()))
        published.update(republish_local.get(file_name, ()))
        for _, target in republish_star.get(file_name, ()):
            published.update(all_published(target, trail))
        names_cache[file_name] = published
        return published

    def link_surface(entry):
        row = reexport_of.get(entry)
        if row is None:
            return                                         # not a re-export entry
        kind, first_target, named_originals = row
        seen_modules = set()
        worklist = [(first_target, named_originals or None)]
        while worklist:
            module_file, only = worklist.pop()
            if module_file in seen_modules:
                continue
            seen_modules.add(module_file)
            wanted_names = only if only is not None else sorted(
                all_published(module_file))
            for wanted in wanted_names:
                def_ids, conduits, module = resolve_name(module_file, wanted)
                for def_id in def_ids:
                    if def_id != entry:
                        links.append((entry, def_id))
                        counts["published surface"] += 1
                for conduit in conduits:
                    if conduit != entry:
                        links.append((entry, conduit))
                        counts["published surface"] += 1
                if module is not None:                     # a namespace inside the
                    worklist.append((module, None))        # surface: all of it too

    def link_attr_paths(number, text, label, module_file):
        """Resolves every `label.attr[.attr...]` written in this statement.

        The emulated namespaces nest - `ts.server.protocol.Request` - so the
        written path is walked segment by segment: while a segment resolves
        to a whole module, the next segment is resolved against that module.
        Everything the path rides through is linked, because the user needs
        the whole chain."""
        for match in re.finditer(r"(?<!" + IDENT + r")" + re.escape(label)
                                 + r"((?:\s*\.\s*\w+)+)", text):
            segments = re.findall(r"\w+", match.group(1))  # the attrs, in order
            current = module_file                           # resolved against
            for segment in segments:                        # each hop in turn
                def_ids, conduits, module = resolve_name(current, segment)
                if not def_ids:
                    break                                  # not a name of that module
                for def_id in def_ids:
                    if def_id != number:
                        links.append((number, def_id))     # the hop is needed
                        counts["across files"] += 1
                for conduit in conduits:                   # and the chain it rode
                    if conduit != number:
                        links.append((number, conduit))
                        counts["through a re-export"] += 1
                if module is None:                         # a plain definition:
                    break                                  # the path ends here
                current = module                           # a module: walk on

    # 3. same-file use of definitions, and use of what imports bring
    for name in sorted(files):
        local_defs = definitions.get(name, {})             # this file's own names
        brought = {}                                       # local name -> how it resolves
        alias_map = {}                                     # alias -> (import id, module file)
        for import_id in imports_by_file.get(name, ()):
            _, locals_, module_aliases = import_rows[import_id]
            for local, (target, original) in locals_.items():
                if target is not None:                     # a package has no statement
                    def_ids, conduits, module = resolve_name(target, original)
                else:
                    def_ids, conduits, module = (), (), None
                brought[local] = (import_id, def_ids, conduits, module)
            for alias, target in module_aliases.items():
                alias_map[alias] = (import_id, target)
        if not local_defs and not brought and not alias_map:
            continue
        patterns = {n: boundary_pattern(n) for n in
                    list(local_defs) + list(brought) + list(alias_map)}
        is_python = name.endswith(PY_EXTENSIONS)
        for number, text in by_file[name]:                 # every statement of the file
            stripped = text.lstrip()
            if stripped.startswith(("import ", "from ")) or (
                    not is_python and stripped.startswith("import")):
                continue                                   # an import is never a user
            for local, def_ids in local_defs.items():      # its own names
                if number in def_ids:                      # a carrier of the name
                    continue                               # is never its user
                if patterns[local].search(text) and not defines_same(
                        text, local, is_python):
                    for def_id in def_ids:                 # every statement that
                        links.append((number, def_id))     # carries the name
                        counts["same file"] += 1
            for local, (import_id, def_ids, conduits, module) in brought.items():
                if patterns[local].search(text):           # imported names
                    links.append((number, import_id))      # the import is used
                    counts["import used"] += 1
                    for def_id in def_ids:                 # every carrier of the
                        if def_id != number:               # definition
                            links.append((number, def_id))
                            counts["across files"] += 1
                    for conduit in conduits:               # and every re-export
                        if conduit != number:              # the name flows through
                            links.append((number, conduit))
                            counts["through a re-export"] += 1
                    if module is not None:                 # a whole module under a
                        link_attr_paths(number, text, local, module)  # name
            for alias, (import_id, target) in alias_map.items():  # alias.name use
                if not patterns[alias].search(text):
                    continue
                links.append((number, import_id))          # the module import is used
                counts["import used"] += 1
                link_attr_paths(number, text, alias, target)

    # 3b. the published surface of every entry that is a re-export
    for entry in entry_ids:
        link_surface(entry)

    # 4. the settings exception: settings.NAME and "NAME" anywhere in python
    settings_defs = definitions.get(SETTINGS_FILE, {})
    for defined, def_ids in sorted(settings_defs.items()):
        pattern = re.compile(r"""(?:settings\s*\.\s*|["'])""" + re.escape(defined)
                             + r"(?!" + IDENT + r")")
        for name in sorted(files):
            if not name.endswith(PY_EXTENSIONS) or name == SETTINGS_FILE:
                continue
            for number, text in by_file[name]:
                if defined in text and pattern.search(text):
                    for def_id in def_ids:                 # the framework hands it over
                        links.append((number, def_id))
                        counts["through settings"] += 1

    seen = set()                                           # the same link once
    kept = []
    for source, target in links:
        if source == target or (source, target) in seen:
            continue
        seen.add((source, target))
        kept.append((source, target))

    out_path = os.path.join(analysis, OUTPUT)              # where the links go
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for source, target in sorted(kept):                # in a fixed order
            out.write("%d\t%d\t%s\n" % (source, target, KIND))

    # The record of which statement defines which name. The graph's REF kind
    # means "the user needs the definition of the name it uses" - so a REF
    # may land only on a statement that defines a name. The merge checks the
    # landing against this file; a REF into a statement that defines nothing
    # is the wiring of the file scope, not a definition, and stays out.
    defined_path = os.path.join(analysis, "defined-names.tsv")
    with io.open(defined_path, "w", encoding="utf-8", newline="\n") as out:
        for name in sorted(definitions):                   # every defining statement
            for defined, def_ids in sorted(definitions[name].items()):
                for def_id in def_ids:                     # every carrier of it
                    out.write("%d\t%s\n" % (def_id, defined))
        for import_id in sorted(import_rows):              # an import defines its
            file_name, locals_, module_aliases = import_rows[import_id]
            for local in sorted(locals_):                  # brought-in locals
                out.write("%d\t%s\n" % (import_id, local))
            for alias in sorted(module_aliases):           # and its module aliases
                out.write("%d\t%s\n" % (import_id, alias))
        for name in sorted(republish_named):               # a named re-export
            for published, (unit, _, _) in sorted(republish_named[name].items()):
                out.write("%d\t%s\n" % (unit, published))  # defines what it publishes
        for name in sorted(republish_local):               # a bare export { X }
            for published, (unit, _) in sorted(republish_local[name].items()):
                out.write("%d\t%s\n" % (unit, published))  # publishes a local

    print("Statements read:        ", len(rows))
    print("Definitions found:      ", sum(len(d) for d in definitions.values()))
    print("Import statements read: ", len(import_rows))
    print("Name links written:     ", len(kept))
    for key in ("same file", "across files", "import used",
                "through a re-export", "published surface", "through settings"):
        print("   %-22s %d" % (key + ":", counts[key]))
    print()
    print("Name links file:", out_path)
    print("Nothing was written into the database. Run machine_links.py fill next.")
    return 0


def main():
    """One command only: derive."""
    parser = argparse.ArgumentParser(prog="name_links.py",
                                     description="SPIDER - step 4, the name graph")
    commands = parser.add_subparsers(dest="command", required=True)
    derive_command = commands.add_parser("derive")         # the only one
    derive_command.add_argument("--analysis", required=True)
    arguments = parser.parse_args()
    return derive(arguments.analysis)


if __name__ == "__main__":                                 # when run directly
    sys.exit(main())
