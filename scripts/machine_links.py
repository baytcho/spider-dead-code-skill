"""SPIDER - step 4: turn the machine graph into proven links and walk them.

    machine_links.py merge --analysis <analysis directory>
        Merges every exported link file into one, translates both ends of every
        link into statement ids and writes the result. Changes nothing in the
        database.

    machine_links.py fill --analysis <analysis directory>
        Writes the translated causal links into the links table and derives the
        two columns of every touched record - which ids send information in and
        which ids it sends to. Sets no visited mark: a link alone proves
        nothing about reachability.

    machine_links.py walk --analysis <analysis directory>
        Walks the causal links from the entry points and sets the visited mark
        only on the statements the walk actually reaches. Everything else is
        left for the traversal and the review. This is the only place the
        machine may mark a statement, and it may mark it only as reached.

    machine_links.py reset --analysis <analysis directory> --confirm
        Removes everything the machine wrote - the machine links, the derived
        columns, the machine marks - in one transaction, and touches nothing
        the intelligence wrote. Refuses without --confirm and refuses a base
        this code did not create.

The exported files are the ones Joern wrote, one per graph, in the `machine`
directory inside the analysis directory, each named `edges-NAME.tsv`. When a
graph was built from a subdirectory of the snapshot, the prefix that makes its
paths whole again is given in `machine/prefixes.txt`: `NAME<TAB>prefix/`.

Nothing here decides anything about the meaning of the code. The programs
merge, translate, count, walk what is written and record. Every number printed
is computed from the files and the database, never carried in memory.

Every line below carries a comment.
"""

import argparse                                  # reads the command line
import bisect                                    # finds the statement of a line
import collections                               # counters and grouped lists
import hashlib                                   # the sums of the derived files
import io                                        # files, always UTF-8
import os                                        # paths and directory walking
import sqlite3                                   # the database itself
import sys                                       # exit code and stdout


def file_sha256(path):
    """The checksum of one file, read once, in pieces."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for piece in iter(lambda: handle.read(1 << 20), b""):
            digest.update(piece)
    return digest.hexdigest()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the scripts directory itself
from version import SCHEMA as SCHEMA_VERSION     # the layout this code expects

if hasattr(sys.stdout, "reconfigure"):           # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")     # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")     # so non-Latin text never breaks it

STATEMENTS = "statements.txt"                    # made by step 1
ENTRY_POINTS = "entry-points.txt"                # made by step 2
DATABASE = "analysis.db"                         # made by step 3
MACHINE = "machine"                              # where the exports live
PREFIXES = "prefixes.txt"                        # how a graph's paths are made whole
MERGED = "all-links.tsv"                         # every exported link, in one file
TRANSLATED = "links-by-id.tsv"                   # the causal links, as statement ids

# Which files the graph frontends actually parse. A statement in any other
# kind of file was never looked at by the machine, and its empty record means
# "not looked at", never "not needed".
SUPPORTED_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

# The kinds of link this step is allowed to carry into the database, and what
# each one means. This table is the contract of step 4:
#
#   flip    - the direction the graph exports versus the direction SPIDER
#             needs. SPIDER stores every link as "source NEEDS target": the
#             statement that depends first, the statement it depends on second.
#             Reachability may only travel that way - from a living statement
#             to what it needs - because the reverse claim ("what I need is
#             used, so I am used") is exactly how dead callers of living code
#             would come back to life.
#   sender  - which side of the NEEDS pair sends the information, for deriving
#             the owner's two columns: the sender's outputs gain the receiver,
#             the receiver's inputs gain the sender.
#   why     - why reachability is allowed to travel along this kind at all.
#
# Every other kind the graph exports - AST, CONTAINS, CFG, DOMINATE and the
# rest - is structure and order, not need. It stays in the merged file for
# anyone to inspect and is never written into the database.
CAUSAL_KINDS = {
    "CALL": {                                    # a call site and its callee
        "flip": False,                           # exported caller -> callee; the caller needs the callee
        "sender": "source",                      # the caller sends its arguments into the callee
        "why": "a living caller executes its callee",
    },
    "REF": {                                     # a used name and its definition
        "flip": False,                           # exported user -> definition; the user needs the definition
        "sender": "target",                      # the definition sends its value to the user
        "why": "a living user needs the definition of the name it uses",
    },
    # REACHING_DEF is NOT here, and that is a decision, not an omission.
    # Between two TOP-LEVEL statements of one file the graph's data-flow
    # edge degenerates into the wiring of the module body: the docstring,
    # every import and every definition chain into one web, and a name
    # nobody uses is dragged alive by its neighbours - the same neighbour
    # trap that ruined the first analysis, machine edition. Real data
    # dependency between top-level statements always writes the used name,
    # and the name graph records exactly that. So at this granularity
    # REACHING_DEF is structure, and it stays in the merged file only.
    "IS_CALL_FOR_IMPORT": {                      # an import statement and what carries it out
        "flip": False,                           # exported importer -> imported; the importer needs it
        "sender": "target",                      # the imported side sends the name to the importer
        "why": "a living importer needs what it imports",
    },
    "LOADS": {                                   # a loading statement and what loading runs
        "flip": False,                           # derived importer -> loaded statement, already the NEEDS way
        "sender": "source",                      # the loader sends control into the loaded statement
        "why": "a side-effect statement acts exactly when its file is loaded",
    },
    "USES": {                                    # a user and the named statement it writes
        "flip": False,                           # derived user -> definition, already the NEEDS way
        "sender": "target",                      # the named side sends its value to the user
        "why": "a naming statement is needed exactly when a needed statement writes its name",
    },
}

# Where the causal links come from. The graph gives what it can prove about
# calls; `load_links.py` gives what the source itself proves about loading.
# Either may be missing - a run without a graph tool still has the load graph,
# and a run with no import anywhere still has the graph's calls - but a fill
# with neither would be filling nothing.
LINK_SOURCES = (
    ("links-by-id.tsv", "the graph export"),     # written by merge
    ("load-links.tsv", "the load graph"),        # written by load_links.py derive
    ("name-links.tsv", "the name graph"),        # written by name_links.py derive
)


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------

def open_database(analysis):
    """Opens the database and refuses one this code did not create."""
    path = os.path.join(analysis, DATABASE)                # where step 3 put it
    if not os.path.isfile(path):                           # step 3 has to be done
        raise SystemExit("No database: " + path)
    database = sqlite3.connect(path)                       # open for writing
    try:
        meta = dict(database.execute("SELECT key, value FROM meta"))  # the facts of the base
    except sqlite3.OperationalError:                       # a base without the meta table
        database.close()                                   # is from another layout
        raise SystemExit(
            "The database carries no meta table. It was made by an older "
            "layout. The safe way forward is a new analysis, not a quiet "
            "adjustment of an old base.")
    if meta.get("created_by") != "spider":                 # a base someone else made
        database.close()                                   # is not touched
        raise SystemExit("The database was not created by SPIDER. Refusing.")
    if meta.get("schema_version") != str(SCHEMA_VERSION):  # a base of another layout
        database.close()                                   # is not adjusted in silence
        raise SystemExit(
            "The database layout is version " + str(meta.get("schema_version"))
            + " and this code writes version " + str(SCHEMA_VERSION) + ". "
            "The safe way forward is a new analysis.")
    return database                                        # checked and open


def read_prefixes(machine_dir):
    """Reads the prefix of every graph, when the file naming them exists."""
    prefixes = {}                                          # graph name -> prefix
    path = os.path.join(machine_dir, PREFIXES)             # where they are named
    if not os.path.isfile(path):                           # the file is optional
        return prefixes                                    # no prefix for anything
    with io.open(path, encoding="utf-8") as handle:        # always UTF-8
        for number, line in enumerate(handle, 1):          # count for the message
            line = line.rstrip("\n")                       # drop the newline
            if not line.strip():                           # a blank line
                continue                                   # is skipped
            parts = line.split("\t")                       # name and prefix
            if len(parts) != 2:                            # anything else is broken
                raise SystemExit(                          # named, not guessed at
                    "Line " + str(number) + " of " + path
                    + " is not 'name<TAB>prefix/': " + line[:60])
            prefixes[parts[0].strip()] = parts[1].strip()  # keep it
    return prefixes                                        # for the merge


def exported_files(machine_dir):
    """Every exported link file, with the graph name taken from its own name."""
    if not os.path.isdir(machine_dir):                     # step 4 has to be prepared
        raise SystemExit("No machine directory: " + machine_dir)
    found = []                                             # (graph name, path)
    for name in sorted(os.listdir(machine_dir)):           # in a fixed order
        if name.startswith("edges-") and name.endswith(".tsv"):
            found.append((name[len("edges-"):-len(".tsv")],
                          os.path.join(machine_dir, name)))
    if not found:                                          # nothing to merge
        raise SystemExit(
            "No exported links in " + machine_dir + ".\n"
            "Every export has to be named edges-NAME.tsv.")
    return found                                           # in name order


def build_index(analysis):
    """For every file: the sorted spans of its statements, and a look-up."""
    path = os.path.join(analysis, STATEMENTS)              # the statement list
    if not os.path.isfile(path):                           # step 1 has to be done
        raise SystemExit("No statement list: " + path)
    by_file = collections.defaultdict(list)                # file -> [(first, last, id)]
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
            span = columns[2].strip().split("-")           # first-last
            if len(span) != 2 or not span[0].isdigit() or not span[1].isdigit():
                raise SystemExit(
                    "Line " + str(number) + " has a broken address: "
                    + columns[2][:40])
            by_file[columns[1].strip()].append(
                (int(span[0]), int(span[1]), int(columns[0])))
    for name in by_file:                                   # every file
        by_file[name].sort()                               # in line order
    starts = {name: [row[0] for row in rows]               # the first lines alone
              for name, rows in by_file.items()}           # for the binary search

    def find(name, line):
        """The id of the statement covering this line, or None."""
        rows = by_file.get(name)                           # the file's statements
        if rows is None:                                   # a file not in the list
            return None                                    # nothing covers it
        place = bisect.bisect_right(starts[name], line) - 1  # the last one starting before
        if place < 0:                                      # the line is before them all
            return None                                    # nothing covers it
        first, last, number = rows[place]                  # the candidate
        return number if first <= line <= last else None   # only if the line is inside

    return find                                            # the look-up


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


def rebuild_columns(database, touched):
    """Derives the owner's two columns from the links table, for these ids.

    The links table is the single source: machine links carry their kind and
    the sender side comes from the contract table; intelligence links are
    stated directly and their sender is always the source. Deriving instead of
    writing twice makes the two sides of every link agree by construction.
    """
    for number in sorted(touched):                         # every statement to rebuild
        inputs, outputs = set(), set()                     # collected fresh
        for source, target, kind, origin in database.execute(
                "SELECT source, target, kind, origin FROM links "
                "WHERE source=? OR target=?", (number, number)):
            if origin == "intelligence":                   # a stated link: source sends to target
                sender, receiver = source, target          # exactly as stated
            else:                                          # a machine link: the contract decides
                rule = CAUSAL_KINDS.get(kind)              # its kind must be known
                if rule is None:                           # an unknown kind in the table
                    raise SystemExit("Unknown machine link kind in the "
                                     "database: " + str(kind))
                if rule["sender"] == "source":             # the needing side sends
                    sender, receiver = source, target      # as stored
                else:                                      # the needed side sends
                    sender, receiver = target, source      # the other way round
            if sender == number:                           # this statement sends
                outputs.add(receiver)                      # to the receiver
            if receiver == number:                         # this statement receives
                inputs.add(sender)                         # from the sender
        database.execute(                                  # the derived record
            "UPDATE statements SET inputs=?, outputs=?, is_source=?, is_sink=? "
            "WHERE id=?",
            (",".join(str(x) for x in sorted(inputs)),     # stored as text
             ",".join(str(x) for x in sorted(outputs)),    # so it can be read by eye
             1 if (outputs and not inputs) else None,      # the definition of a source
             1 if not outputs else None,                   # the definition of a sink
             number),
        )


# --------------------------------------------------------------------------
# merge - one file with everything, one file with the causal ids
# --------------------------------------------------------------------------

def read_defining(analysis):
    """The statements that define a name, from the name graph's record.

    The REF kind means "the user needs the definition of the name it uses",
    so a REF may land only on a statement that defines a name. The graph
    wires file-scope variables to the file node, whose address is line one -
    the docstring - and without this check that wiring would keep alive a
    statement that defines nothing."""
    path = os.path.join(analysis, "defined-names.tsv")     # written by name_links
    if not os.path.isfile(path):                           # the order is part of
        return None                                        # the contract; walk checks
    defining = set()
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            piece = line.split("\t", 1)[0].strip()
            if piece.isdigit():
                defining.add(int(piece))
    return defining


def merge(analysis):
    """Merges the exports and translates them into statement ids."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    machine_dir = os.path.join(analysis, MACHINE)          # where the exports live
    prefixes = read_prefixes(machine_dir)                  # how paths are made whole
    files = exported_files(machine_dir)                    # what there is to merge
    find = build_index(analysis)                           # address -> statement id
    defining = read_defining(analysis)                     # who defines a name

    merged_path = os.path.join(analysis, MERGED)           # every link, in one file
    translated_path = os.path.join(analysis, TRANSLATED)   # the causal links, as ids

    # Two export shapes are read. The old one carries five columns: kind and
    # an address per end. The rich one carries twelve: kind, then per end
    # file, line, enclosing method, node label and node code, and last the
    # variable a data-flow edge carries. The extra columns let the merge
    # judge a link by the graph's own record; an old export still works and
    # simply offers no record to judge by.
    per_graph = collections.Counter()                      # how many each graph gave
    with io.open(merged_path, "w", encoding="utf-8", newline="\n") as out:
        for name, path in files:                           # every export in turn
            prefix = prefixes.get(name, "")                # its prefix, if any
            with io.open(path, encoding="utf-8") as handle:  # strict UTF-8: damage stops here
                try:
                    for number, line in enumerate(handle, 1):  # every link, counted
                        columns = line.rstrip("\n").split("\t")
                        if len(columns) == 5:              # the old shape
                            kind, from_file, from_line, to_file, to_line = columns
                            rest = ("", "", "", "", "", "")
                        elif len(columns) == 12:           # the rich shape
                            (kind, from_file, from_line, from_method, from_label,
                             from_code, to_file, to_line, to_method, to_label,
                             to_code, variable) = columns
                            rest = (from_method, from_label, to_method, to_label,
                                    from_code[:80], to_code[:80])
                        else:                              # a malformed line is damage,
                            raise SystemExit(              # never a thing to skip quietly
                                "Line " + str(number) + " of " + path
                                + " carries neither five nor twelve columns: "
                                + line[:60])
                        if from_file:                      # an end with an address
                            from_file = prefix + from_file.replace("\\", "/")
                        if to_file:                        # the same for the other end
                            to_file = prefix + to_file.replace("\\", "/")
                        out.write("\t".join(
                            (kind, from_file, from_line, to_file, to_line)
                            + rest) + "\n")
                        per_graph[name] += 1               # counted per graph
                except UnicodeDecodeError as error:        # a byte that is not UTF-8
                    raise SystemExit("The export " + path  # is damage, named exactly
                                     + " is not valid UTF-8: " + str(error))

    # Node labels of the graph that are scope wiring, not statements: a REF
    # landing on one of these lands on a variable slot or a parameter slot,
    # whose recorded line is the line of the scope - the docstring trap of
    # the earlier version, now cut by the graph's own record instead of
    # being cut only by the derived name record.
    SCOPE_LABELS = {"LOCAL", "METHOD_PARAMETER_IN", "METHOD_PARAMETER_OUT"}

    counts = collections.Counter()                         # what happened to the links
    per_kind = collections.defaultdict(collections.Counter)  # the same, per kind
    seen = set()                                           # the distinct causal triples
    with io.open(merged_path, encoding="utf-8") as handle, \
            io.open(translated_path, "w", encoding="utf-8", newline="\n") as out:
        for line in handle:                                # every merged link
            columns = line.rstrip("\n").split("\t")        # five or eleven columns
            kind, from_file, from_line, to_file, to_line = columns[:5]
            to_label = columns[8] if len(columns) > 8 else ""
            counts["links"] += 1                           # counted in total
            per_kind[kind]["links"] += 1                   # and per kind
            if not from_file or not from_line or not to_file or not to_line:
                counts["an end without an address"] += 1   # nothing to translate
                per_kind[kind]["without an address"] += 1
                continue                                   # on to the next
            try:
                first = find(from_file, int(from_line))    # which statement it starts in
                second = find(to_file, int(to_line))       # and which it ends in
            except ValueError:                             # a line number that is not one
                raise SystemExit("A link of kind " + kind  # is damage, named exactly
                                 + " carries a line number that is not a "
                                 "number: " + from_line + " / " + to_line)
            if first is None or second is None:            # an address outside the list
                counts["an address in no statement"] += 1
                per_kind[kind]["outside the statements"] += 1
                continue
            per_kind[kind]["with two addresses"] += 1      # both ends landed
            if first == second:                            # a link inside one statement
                counts["both ends in one statement"] += 1
                per_kind[kind]["inside one statement"] += 1
                continue                                   # it joins nothing
            counts["between two statements"] += 1          # a real link
            per_kind[kind]["between two statements"] += 1
            rule = CAUSAL_KINDS.get(kind)                  # is this kind causal
            if rule is None:                               # structure and order
                counts["structural, kept in the merged file only"] += 1
                continue                                   # never enter the database
            if rule["flip"]:                               # the export runs the other way
                first, second = second, first              # so the NEEDS direction is restored
            if kind == "REF":                              # a REF lands on a definition
                if to_label in SCOPE_LABELS:               # the graph's own record
                    counts["REF into scope wiring - node label"] += 1
                    per_kind[kind]["scope wiring by label"] += 1
                    continue                               # stays out of the database
                if defining is None:                       # the derived record is missing
                    raise SystemExit(
                        "The export holds REF links, but there is no "
                        "defined-names.tsv to check their landing against. "
                        "Run name_links.py derive first.")
                if second not in defining:                 # it defines nothing
                    counts["REF into no definition - scope wiring"] += 1
                    continue                               # stays out of the database
            triple = (first, second, kind)                 # what is written down
            if triple in seen:                             # the same link twice
                counts["repeated"] += 1                    # is counted
                continue                                   # and written once
            seen.add(triple)                               # remembered
            out.write("%d\t%d\t%s\n" % (first, second, kind))
            counts["written causal"] += 1                  # and counted

    print("Merged:")                                       # what came from where
    for name, number in sorted(per_graph.items()):
        print("   %-24s %d" % (name, number))
    print("   %-24s %d" % ("in one file", sum(per_graph.values())))
    print()
    print("Translated into statement ids:")                # what happened to them
    for key in ("links", "an end without an address", "an address in no statement",
                "both ends in one statement", "between two statements",
                "structural, kept in the merged file only",
                "REF into scope wiring - node label",
                "REF into no definition - scope wiring", "repeated",
                "written causal"):
        print("   %-40s %d" % (key, counts[key]))
    print()
    print("By kind:")                                      # and the same per kind
    print("   %-24s %10s %10s %10s %10s"
          % ("kind", "links", "addressed", "inside one", "between two"))
    for kind in sorted(per_kind, key=lambda k: -per_kind[k]["between two statements"]):
        row = per_kind[kind]
        print("   %-24s %10d %10d %10d %10d"
              % (kind, row["links"], row["with two addresses"],
                 row["inside one statement"], row["between two statements"]))
    print()
    print("Merged file:    ", merged_path)                 # where the results are
    print("Translated file:", translated_path)
    return 0                                               # success


# --------------------------------------------------------------------------
# fill - the causal links enter the database; no mark is set
# --------------------------------------------------------------------------

def fill(analysis):
    """Writes every causal link - the graph's and the load graph's - into the table."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative

    rows = []                                              # (source, target, kind)
    per_file = collections.Counter()                       # how many each source gave
    found_any = False                                      # was there anything to read
    for name, description in LINK_SOURCES:                 # both producers, in order
        path = os.path.join(analysis, name)                # where it would be
        if not os.path.isfile(path):                       # a missing producer is allowed
            continue                                       # the other one may carry the run
        found_any = True                                   # something was read
        with io.open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):      # every link it wrote
                columns = line.rstrip("\n").split("\t")    # source, target, kind
                if len(columns) != 3 or not columns[0].isdigit() or not columns[1].isdigit():
                    raise SystemExit("Line " + str(number)  # damage is named, not skipped
                                     + " of " + path + " is broken: " + line[:60])
                if columns[2] not in CAUSAL_KINDS:         # a kind outside the contract
                    raise SystemExit("Line " + str(number) + " of " + path
                                     + " carries the kind " + columns[2]
                                     + ", which is not in the contract of step 4.")
                rows.append((int(columns[0]), int(columns[1]), columns[2]))
                per_file[description] += 1                 # counted per producer
    if not found_any:                                      # neither producer ran
        raise SystemExit(
            "Neither " + " nor ".join(n for n, _ in LINK_SOURCES) + " exists in "
            + analysis + ". Run machine_links.py merge, or load_links.py derive, "
            "or both - fill writes down what they produced.")

    database = open_database(analysis)                     # checked and open
    try:
        already = database.execute(                        # a filled base is not refilled
            "SELECT COUNT(*) FROM links WHERE origin='machine'").fetchone()[0]
        if already:
            raise SystemExit(
                "The database already holds " + str(already) + " machine "
                "links. It is not filled twice - run reset first, with "
                "--confirm, and then fill again.")
        known = set(row[0] for row in database.execute(    # every id the base holds
            "SELECT id FROM statements"))
        for source, target, kind in rows:                  # every link must name real ids
            if source not in known or target not in known:
                raise SystemExit("The translated link " + str(source) + " -> "
                                 + str(target) + " names a statement that is "
                                 "not in the database.")
        database.executemany(                              # one transaction for all of them
            "INSERT OR IGNORE INTO links (source, target, kind, origin) "
            "VALUES (?, ?, ?, 'machine')", rows)
        touched = set()                                    # whose columns to derive
        for source, target, _ in rows:                     # both ends of every link
            touched.add(source)
            touched.add(target)
        rebuild_columns(database, touched)                 # derived, never written twice
        database.execute(                                  # the phase is recorded
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('phase4_fill', 'done')")
        for name, description in LINK_SOURCES:             # which producers really ran -
            ran = os.path.isfile(os.path.join(analysis, name))  # a producer may honestly
            database.execute(                              # write zero links and still
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("fill_source_" + name, "yes" if ran else "no"))
        # The sum of every derived file the fill read, so that step 7 can
        # prove the database was filled from exactly these files and they
        # have not been edited since.
        for key, name in (("fill_sha_load", "load-links.tsv"),
                          ("fill_sha_name", "name-links.tsv"),
                          ("fill_sha_graph", "links-by-id.tsv")):
            path = os.path.join(analysis, name)
            if os.path.isfile(path):
                database.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    (key, file_sha256(path)))
        database.commit()                                  # everything lands together
        stored = database.execute(                         # counted back from the base
            "SELECT COUNT(*) FROM links WHERE origin='machine'").fetchone()[0]
    finally:
        database.close()                                   # closed even if something threw

    print("Causal links read:   ", len(rows))              # from the files
    for description, number in sorted(per_file.items()):   # and where each came from
        print("   from %-22s %d" % (description, number))
    print("Causal links stored: ", stored)                 # from the database
    print("Statements with derived columns:", len(touched))
    print("No visited mark was set. Run walk next.")       # the mark comes only from the walk
    return 0                                               # success


# --------------------------------------------------------------------------
# walk - reachability from the entry points; the only machine mark
# --------------------------------------------------------------------------

def read_demoted(analysis):
    """The entries the load graph demoted: directives in unimported files."""
    path = os.path.join(analysis, "demoted-entries.txt")   # written by load_links
    demoted = set()
    if os.path.isfile(path):                               # the file is optional
        with io.open(path, encoding="utf-8") as handle:
            for line in handle:
                piece = line.split("\t", 1)[0].strip()     # the id column
                if piece.isdigit():
                    demoted.add(int(piece))
    return demoted


def walk(analysis):
    """Walks the machine links from the entries; marks only what it reaches."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    entries = read_entries(analysis)                       # where execution starts
    demoted = read_demoted(analysis)                       # directives that are not entries
    if demoted:                                            # said out loud, then subtracted
        entries = [e for e in entries if e not in demoted]
        print("Demoted entries skipped:   ", len(demoted),
              "(directives in files nothing imports - findings, not entries)")
    database = open_database(analysis)                     # checked and open
    try:
        filled = database.execute(                         # fill has to have run
            "SELECT value FROM meta WHERE key='phase4_fill'").fetchone()
        if not filled or filled[0] != "done":
            raise SystemExit("The links are not filled yet. Run fill first.")
        known = set(row[0] for row in database.execute(    # every id the base holds
            "SELECT id FROM statements"))
        for entry in entries:                              # every entry must be real
            if entry not in known:
                raise SystemExit("Entry point " + str(entry)
                                 + " is not in the database.")

        needs = collections.defaultdict(list)              # id -> the ids it needs
        linked = set()                                     # every id with any causal link
        by_kind = collections.defaultdict(set)             # kind -> the ids it can reach
        for source, target, kind in database.execute(      # the stored NEEDS pairs
                "SELECT source, target, kind FROM links WHERE origin='machine'"):
            needs[source].append(target)                   # source needs target
            linked.add(source)                             # both ends
            linked.add(target)                             # are linked
            by_kind[kind].add(target)                      # for the coverage measure

        reached = set()                                    # what the walk arrives at
        stack = list(entries)                              # it starts at every entry
        while stack:                                       # a plain depth walk
            current = stack.pop()                          # the next statement
            if current in reached:                         # already walked
                continue                                   # is never walked twice
            reached.add(current)                           # now reached
            for needed in needs.get(current, ()):          # everything it needs
                if needed not in reached:                  # that is not walked yet
                    stack.append(needed)                   # is walked in its turn

        supported = tuple(SUPPORTED_EXTENSIONS)            # what the graph can read
        marked = {"reached": 0, "unreached": 0,            # counted for the report
                  "untouched": 0, "unsupported": 0}
        for number, name in database.execute(              # every statement gets its state
                "SELECT id, file FROM statements"):
            if number in reached:                          # the walk arrived here
                state = "reached"                          # proven from the entries
            elif not name.lower().endswith(supported):     # a file the graph cannot read
                state = "unsupported"                      # never looked at
            elif number in linked:                         # linked but never arrived at
                state = "unreached"                        # no path from any entry
            else:                                          # parsed but no link at all
                state = "untouched"                        # the machine said nothing
            marked[state] += 1                             # counted
            if state == "reached":                         # the only mark the machine sets
                database.execute(
                    "UPDATE statements SET visited=1, visited_by='machine', "
                    "machine_state='reached' WHERE id=?", (number,))
            else:                                          # everything else stays unvisited
                database.execute(
                    "UPDATE statements SET machine_state=? WHERE id=?",
                    (state, number))
        # The coverage measure. Loading no longer proves whole files, so the
        # loaded set comes from the load graph's own file record; the walk
        # explains what the three graphs together prove, and a loaded file
        # with nothing reached in it is a FINDING - a file the program can
        # load and never needs - not an error of the walk.
        file_of = dict(database.execute("SELECT id, file FROM statements"))
        loaded_path = os.path.join(analysis, "loaded-files.txt")
        loaded_files = set()
        if os.path.isfile(loaded_path):                    # written by load_links
            with io.open(loaded_path, encoding="utf-8") as handle:
                loaded_files = set(l.strip() for l in handle if l.strip())
        for entry in entries:                              # a file with an entry point
            loaded_files.add(file_of[entry])               # was loaded by the framework
        walked_files = set(file_of[i] for i in reached)     # what the walk explained
        code_files = set(name for name in file_of.values()
                         if name.lower().endswith(supported))
        missing = sorted(loaded_files - walked_files)      # loaded, nothing needed inside
        share = (100.0 * len(walked_files) / len(loaded_files)) if loaded_files else 0.0
        meta_now = dict(database.execute("SELECT key, value FROM meta"))
        had_load = (meta_now.get("fill_source_load-links.tsv") == "yes"
                    or bool(by_kind.get("LOADS")))         # ran, even with zero links
        had_names = (meta_now.get("fill_source_name-links.tsv") == "yes"
                     or bool(by_kind.get("USES")))
        for key, value in (("walk_files_walked", len(walked_files)),
                           ("walk_files_loaded", len(loaded_files)),
                           ("walk_files_code", len(code_files)),
                           ("walk_had_load_graph", "yes" if had_load else "no"),
                           ("walk_had_name_graph", "yes" if had_names else "no")):
            database.execute(                              # every number, in the base
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (key, str(value)))
        database.execute(                                  # the phase is recorded
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('phase4_walk', 'done')")
        database.commit()                                  # everything lands together

        visited = database.execute(                        # counted back from the base
            "SELECT COUNT(*) FROM statements WHERE visited=1").fetchone()[0]
    finally:
        database.close()                                   # closed even if something threw

    print("Entry points walked from:  ", len(entries))     # what the walk was given
    print("Reached and marked:        ", marked["reached"])  # the only machine mark
    print("Linked but unreached:      ", marked["unreached"])  # candidates, unproven alive
    print("Parsed but never linked:   ", marked["untouched"])  # the machine said nothing
    print("In files the graph cannot read:", marked["unsupported"])  # never looked at
    print("Visited in the database:   ", visited)          # must equal reached
    print()
    print("Coverage of this walk:")                        # what it explained, and of what
    print("   files with anything reached:    %d" % len(walked_files))
    print("   files something loads:          %d" % len(loaded_files))
    print("   loaded with nothing needed:     %d  (findings, not errors)"
          % len(missing))
    if not had_load or not had_names:                      # a graph never ran
        print()
        print("A MACHINE GRAPH IS MISSING: "
              + ("the load graph " if not had_load else "")
              + ("the name graph " if not had_names else "")
              + "was never filled. Without it 'unreached' means only that "
              "the machine saw no way in. Run the missing derive, then reset "
              "--confirm, fill and walk again.")
    elif missing:                                          # findings, named
        print()
        print("LOADED, NOTHING NEEDED INSIDE: " + str(len(missing)) + " files. "
              "The program can load them and needs nothing in them. Every "
              "statement of theirs is a candidate. The first few:")
        for name in missing[:10]:                          # named, never summed away
            print("   " + name)
    print()
    print("Unreached and untouched statements are NOT dead. They are what "
          "steps 5 and 6 exist for.")                      # the one sentence that matters
    return 0                                               # success


# --------------------------------------------------------------------------
# reset - removes the machine's work and nothing else
# --------------------------------------------------------------------------

def reset(analysis, confirm):
    """Removes everything the machine wrote, in one transaction."""
    if not confirm:                                        # an explicit key is required
        raise SystemExit("reset removes everything the machine wrote. "
                         "Run it with --confirm to mean it.")
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    database = open_database(analysis)                     # checked and open
    try:
        touched = set()                                    # whose columns to rebuild
        for source, target in database.execute(            # both ends of every machine link
                "SELECT source, target FROM links WHERE origin='machine'"):
            touched.add(source)
            touched.add(target)
        database.execute(                                  # the machine links fall
            "DELETE FROM links WHERE origin='machine'")
        database.execute(                                  # the machine marks fall
            "UPDATE statements SET visited=NULL, visited_by=NULL "
            "WHERE visited_by='machine'")
        database.execute(                                  # the machine states fall everywhere
            "UPDATE statements SET machine_state=NULL")
        # A sweep marks the machine's blind spots unresolved. Those marks were
        # set from the machine states that are being removed here, so they
        # cannot outlive them: a second walk that now reaches such a statement
        # would leave it both visited and unresolved, and step 7 would refuse
        # on a contradiction nobody wrote. Only the sweep's own marks fall -
        # never one the traversal or the review set, which carry visited or
        # reviewed with them.
        swept = database.execute(
            "SELECT COUNT(*) FROM statements WHERE unresolved=1 "
            "AND visited IS NULL AND reviewed IS NULL").fetchone()[0]
        database.execute(
            "UPDATE statements SET unresolved=NULL WHERE unresolved=1 "
            "AND visited IS NULL AND reviewed IS NULL")
        rebuild_columns(database, touched)                 # columns rebuilt from what remains
        database.execute("DELETE FROM meta WHERE key='phase4_fill'")  # the phases fall
        database.execute("DELETE FROM meta WHERE key='phase4_walk'")
        database.execute(                                  # and the sums of the fill
            "DELETE FROM meta WHERE key IN ('fill_sha_load', 'fill_sha_name', "
            "'fill_sha_graph')")                           # they described the removed one
        database.commit()                                  # everything lands together
        left = database.execute(                           # counted back from the base
            "SELECT COUNT(*) FROM links WHERE origin='machine'").fetchone()[0]
        reviews = database.execute(                        # the human work must be intact
            "SELECT COUNT(*) FROM statements WHERE reviewed=1").fetchone()[0]
    finally:
        database.close()                                   # closed even if something threw

    print("Machine links left:            ", left)         # must be zero
    print("Statements with columns rebuilt:", len(touched))
    print("Sweep marks cleared with them: ", swept)        # they came from the machine states
    print("Reviewed statements untouched: ", reviews)      # the intelligence's work stays
    return 0                                               # success


# --------------------------------------------------------------------------

def main():
    """Four commands: merge, fill, walk and reset."""
    parser = argparse.ArgumentParser(prog="machine_links.py",
                                     description="SPIDER - step 4")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("merge", "fill", "walk"):                 # the three plain ones
        command = commands.add_parser(name)                # each with one argument
        command.add_argument("--analysis", required=True)  # the analysis directory
    reset_command = commands.add_parser("reset")           # the guarded one
    reset_command.add_argument("--analysis", required=True)
    reset_command.add_argument("--confirm", action="store_true")  # the explicit key
    arguments = parser.parse_args()                        # read them
    if arguments.command == "merge":                       # which one was asked for
        return merge(arguments.analysis)
    if arguments.command == "fill":
        return fill(arguments.analysis)
    if arguments.command == "walk":
        return walk(arguments.analysis)
    return reset(arguments.analysis, arguments.confirm)    # the last one


if __name__ == "__main__":                                 # when run directly
    sys.exit(main())                                       # the exit code is the result
