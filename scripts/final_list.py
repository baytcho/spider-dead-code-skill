"""SPIDER - step 7: the list of statements to be checked in the live code.

    final_list.py build --analysis <analysis directory> --project <project>

This is what the whole work produces. One file, holding every statement that
has to be checked, each with its address in the source code and the code as it
stands in the analysed snapshot, with a drift note wherever the live file has
moved since.

A statement is on the list because it does not satisfy the conditions of the
cause-and-effect chain of the program: nothing the execution reaches leads to
it. That is a reason to look, not a verdict. The list holds candidates for
checking, never confirmed dead code.

The list is refused until every one of these is proved, from the files and the
database, never from memory:

  - the snapshot is complete and unchanged against the manifest;
  - no file was left unsplit;
  - the entry point list is valid and not empty;
  - when the machine ran: its fill and its walk have finished;
  - the traversal holds no handed-over statement and no pending queue;
  - the reading of step 2 covered the whole statement list;
  - not one statement is still marked unresolved;
  - every never-examined statement has passed the review;
  - the two columns of every record agree with the links table.

Two files are written into the analysis directory:

    to-check-in-live-code.md    for reading, with the code of every statement
    to-check-in-live-code.tsv   the same list as a table, for further work

Every line below carries a comment.
"""

import argparse                                  # reads the command line
import hashlib                                   # verifies the snapshot
import io                                        # files, always UTF-8
import json                                      # the manifest and the report
import os                                        # paths and file checks
import sqlite3                                   # the database itself
import sys                                       # exit code and stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the scripts directory itself
from version import VERSION                      # stamped into the list it writes

if hasattr(sys.stdout, "reconfigure"):           # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")     # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")     # so non-Latin text never breaks it

STATEMENTS = "statements.txt"                    # made by step 1
ENTRY_POINTS = "entry-points.txt"                # made by step 2
READ_PROGRESS = "read-progress.txt"              # how far step 2 got
SPLIT_REPORT = "split-report.json"               # the numbers of step 1
MANIFEST = "manifest.json"                       # the record of the snapshot
DATABASE = "analysis.db"                         # made by step 3
SOURCE_DIR = "source"                            # the snapshot itself
MACHINE = "machine"                              # the machine's directory, when it ran
DOCUMENT = "to-check-in-live-code.md"            # the list, for reading
TABLE = "to-check-in-live-code.tsv"              # the list, as a table


def file_sha256(path):
    """The checksum of one file, read once, in pieces."""
    digest = hashlib.sha256()                              # the running sum
    with open(path, "rb") as fh:                           # bytes, exactly as stored
        for piece in iter(lambda: fh.read(1 << 20), b""):  # a megabyte at a time
            digest.update(piece)                           # fed into the sum
    return digest.hexdigest()                              # as text


def refuse(reason):
    """One named refusal. The list is never written around a doubt."""
    raise SystemExit("The list is not written: " + reason)


def check_snapshot(analysis):
    """The snapshot must match its manifest, file for file, sum for sum."""
    manifest_path = os.path.join(analysis, MANIFEST)       # the record of the copy
    if not os.path.isfile(manifest_path):                  # without it nothing is provable
        refuse("no manifest. The copy step of this version writes one; "
               "an analysis without it cannot prove its snapshot.")
    with io.open(manifest_path, encoding="utf-8") as fh:   # always UTF-8
        manifest = json.load(fh)                           # what the copy recorded
    files = manifest.get("files", {})                      # path -> checksum
    if not files:                                          # an empty snapshot
        refuse("the manifest lists no files.")
    source_root = os.path.join(analysis, SOURCE_DIR)       # where the snapshot lives
    for relative, expected in sorted(files.items()):       # every recorded file
        path = os.path.join(source_root, relative.replace("/", os.sep))
        if not os.path.isfile(path):                       # a file that vanished
            refuse("the snapshot lost " + relative + " since the manifest.")
        if file_sha256(path) != expected:                  # a file that changed
            refuse("the snapshot file " + relative + " changed since the "
                   "manifest. The analysis and its snapshot no longer agree.")
    on_disk = set()                                        # what the snapshot holds now
    for base, folders, names in os.walk(source_root):      # walk it
        for name in names:                                 # every file
            on_disk.add(os.path.relpath(os.path.join(base, name), source_root)
                        .replace(os.sep, "/"))
    added = on_disk - set(files)                           # files the manifest never saw
    if added:                                              # a foreign file in the snapshot
        refuse("the snapshot holds " + str(len(added)) + " files the manifest "
               "does not know, first: " + sorted(added)[0])
    return manifest                                        # verified


def check_split(analysis):
    """No file may have been left unsplit."""
    path = os.path.join(analysis, SPLIT_REPORT)            # the numbers of step 1
    if not os.path.isfile(path):                           # without them nothing is provable
        refuse("no split report.")
    with io.open(path, encoding="utf-8") as fh:            # always UTF-8
        report = json.load(fh)                             # what the split recorded
    left = report.get("files_not_split", [])               # the failures, if any
    if left:                                               # a file nobody read
        refuse(str(len(left)) + " files were never split, first: "
               + left[0].get("file", "?") + " - " + left[0].get("reason", "?"))
    return report                                          # verified


def check_reading(analysis, last_id):
    """The reading of step 2 must have covered the whole statement list."""
    path = os.path.join(analysis, READ_PROGRESS)           # how far it got
    if not os.path.isfile(path):                           # without it nothing is provable
        refuse("no read-progress file. Step 2 records how far the reading "
               "got; a missing record means an unfinished reading.")
    with io.open(path, encoding="utf-8") as fh:            # always UTF-8
        text = fh.read().strip()                           # a single number
    if not text.isdigit() or int(text) < last_id:          # short of the end
        refuse("the reading of step 2 stopped at " + (text or "nothing")
               + " of " + str(last_id) + " statements.")


def check_entries(analysis, database):
    """The entry point list must be valid, not empty, and every entry visited."""
    path = os.path.join(analysis, ENTRY_POINTS)            # where the entries are
    if not os.path.isfile(path):                           # without them nothing is provable
        refuse("no entry point list.")
    entries = []                                           # collected for the checks
    with io.open(path, encoding="utf-8") as fh:            # always UTF-8
        for number, line in enumerate(fh, 1):              # count for the message
            piece = line.strip()                           # one id per line
            if not piece:                                  # a blank line
                continue                                   # is skipped
            if not piece.isdigit():                        # anything that is not an id
                refuse("line " + str(number) + " of the entry point list is "
                       "not an id: " + piece[:40])
            entries.append(int(piece))                     # keep it
    if not entries:                                        # an empty list proves nothing
        refuse("the entry point list is empty.")
    demoted = set()                                        # directives that are not entries
    demoted_path = os.path.join(analysis, "demoted-entries.txt")
    if os.path.isfile(demoted_path):                       # written by the load graph
        with io.open(demoted_path, encoding="utf-8") as fh:
            for line in fh:
                piece = line.split("\t", 1)[0].strip()
                if piece.isdigit():                        # a demoted one stays unvisited
                    demoted.add(int(piece))                # by design - it is a finding
    for entry in entries:                                  # every real entry must be visited
        if entry in demoted:                               # a directive nothing imports
            continue                                       # is a finding, not an entry
        row = database.execute("SELECT visited FROM statements WHERE id=?",
                               (entry,)).fetchone()
        if row is None:                                    # an entry that is no statement
            refuse("entry point " + str(entry) + " is not in the database.")
        if not row[0]:                                     # an entry nobody reached
            refuse("entry point " + str(entry) + " is not visited. The "
                   "traversal still has work.")
    return demoted                                         # for the findings section


def check_traversal(database):
    """The traversal must hold nothing: no handed statement, no queue."""
    try:                                                   # the state table exists once
        row = database.execute(                            # step 5 has run at least once
            "SELECT value FROM traversal_state WHERE key='next'").fetchone()
    except sqlite3.OperationalError:                       # it never ran at all
        row = None                                         # which also means nothing handed
    if row and row[0]:                                     # a statement stands handed over
        refuse("the traversal has handed over statement " + row[0]
               + " and no record has closed the round.")
    queued = database.execute(                             # the queue must be empty
        "SELECT COUNT(*) FROM pending_queue").fetchone()[0]
    if queued:                                             # someone still waits
        refuse(str(queued) + " statements are still in the pending queue. "
               "Run the traversal of step 5 until it stops.")


def check_machine(analysis, database):
    """When the machine directory exists, its fill and walk must have finished."""
    if not os.path.isdir(os.path.join(analysis, MACHINE)): # the machine never ran
        return                                             # and nothing is required of it
    try:                                                   # the phases it recorded
        meta = dict(database.execute("SELECT key, value FROM meta"))
    except sqlite3.OperationalError:                       # a base without the meta table
        refuse("a machine directory exists but the database has no meta "
               "table. The machine work of this version records its phases.")
    if meta.get("phase4_fill") != "done":                  # the links never landed
        refuse("the machine export exists but fill has not finished.")
    if meta.get("phase4_walk") != "done":                  # the walk never ran
        refuse("the machine links are filled but the walk has not run. "
               "Without the walk the visited marks do not mean reachability.")
    # The coverage gate. Reaching needs all three machine graphs: the calls,
    # the loading and the NAMES. Without any one of them 'unreached' means
    # only that the machine saw no way in, and the list would turn that
    # blindness into findings. The list is not written on a silence like that.
    missing_graphs = [label for key, label in
                      (("walk_had_load_graph", "the load graph"),
                       ("walk_had_name_graph", "the name graph"))
                      if meta.get(key) == "no"]
    if missing_graphs:                                     # a graph never ran
        left = database.execute(                           # what would go in on that basis
            "SELECT COUNT(*) FROM statements WHERE visited IS NULL "
            "AND machine_state='unreached'").fetchone()[0]
        if left:                                           # and there is something to lose
            refuse(
                "the machine walked without " + " and ".join(missing_graphs)
                + ", and " + str(left) + " statements are unreached on that "
                "basis alone. 'Unreached' then means 'the machine saw no way "
                "in', not 'execution cannot lead here'. Run the missing "
                "derive, then machine_links.py reset --confirm, fill and "
                "walk again - or settle those statements in step 6 by hand "
                "before building the list.")


def check_fill_sums(analysis, database):
    """The derived graphs must be the very files the fill read.

    The fill records the sum of every derived file it read. A graph edited
    AFTER the fill would leave the database claiming links its files no
    longer carry; the sums make that tampering loud instead of silent. A
    base whose fill never wrote sums has nothing to be held to."""
    try:
        meta = dict(database.execute("SELECT key, value FROM meta"))
    except sqlite3.OperationalError:                       # a base without meta
        return                                             # has no sums to check
    for key, name in (("fill_sha_load", "load-links.tsv"),
                      ("fill_sha_name", "name-links.tsv"),
                      ("fill_sha_graph", "links-by-id.tsv")):
        recorded = meta.get(key)
        if not recorded:                                   # an older fill wrote none
            continue                                       # nothing to hold it to
        path = os.path.join(analysis, name)
        current = file_sha256(path) if os.path.isfile(path) else "missing"
        if current != recorded:
            refuse("the derived graph " + name + " changed after the fill. "
                   "The database was filled from a different file. Run "
                   "machine_links.py reset --confirm, then fill and walk "
                   "again.")


def check_classification(database):
    """Not one unresolved; every never-examined statement reviewed."""
    unresolved = database.execute(                         # an unsettled case is not a result
        "SELECT COUNT(*) FROM statements WHERE unresolved=1").fetchone()[0]
    if unresolved:
        refuse(str(unresolved) + " statements are still marked unresolved. "
               "Finish step 6 first.")
    try:                                                   # the machine states, when any
        unexamined = database.execute(                     # a blind spot nobody looked at
            "SELECT COUNT(*) FROM statements WHERE visited IS NULL "
            "AND reviewed IS NULL "
            "AND machine_state IN ('untouched', 'unsupported')").fetchone()[0]
    except sqlite3.OperationalError:                       # a base without the column
        unexamined = 0                                     # has no machine states to check
    if unexamined:                                         # eyes have not passed over them
        refuse(str(unexamined) + " statements were never examined by anything "
               "- not reached, not linked, not reviewed. Run review.py sweep "
               "and settle them in step 6 first.")


def check_links_agree(database):
    """The two columns of every record must agree with the links table."""
    try:                                                   # the links table, when it exists
        rows = database.execute(                           # what the evidence says
            "SELECT source, target, kind, origin FROM links").fetchall()
    except sqlite3.OperationalError:                       # a base from the old layout
        return                                             # has only its columns
    from machine_links import CAUSAL_KINDS                 # the sender side per kind
    inputs, outputs = {}, {}                               # derived fresh, then compared
    for source, target, kind, origin in rows:              # every evidence row
        if origin == "intelligence":                       # stated: source sends to target
            sender, receiver = source, target
        else:                                              # machine: the contract decides
            rule = CAUSAL_KINDS.get(kind)                  # its kind must be known
            if rule is None:                               # an unknown kind is damage
                refuse("the links table holds an unknown machine kind: " + str(kind))
            if rule["sender"] == "source":                 # the needing side sends
                sender, receiver = source, target
            else:                                          # the needed side sends
                sender, receiver = target, source
        outputs.setdefault(sender, set()).add(receiver)    # sender's outputs
        inputs.setdefault(receiver, set()).add(sender)     # receiver's inputs
    for number, stored_in, stored_out in database.execute(
            "SELECT id, inputs, outputs FROM statements "
            "WHERE inputs IS NOT NULL OR outputs IS NOT NULL"):
        want_in = ",".join(str(x) for x in sorted(inputs.get(number, ())))
        want_out = ",".join(str(x) for x in sorted(outputs.get(number, ())))
        if (stored_in or "") != want_in or (stored_out or "") != want_out:
            refuse("statement " + str(number) + " disagrees with the links "
                   "table: columns " + repr(stored_in) + "/" + repr(stored_out)
                   + " against derived " + repr(want_in) + "/" + repr(want_out))


def build(analysis, project):
    """Writes the list of statements that have to be checked in the live code."""
    analysis = os.path.abspath(analysis)                   # a full path, never relative
    project = os.path.abspath(project)                     # the same for the project
    database_path = os.path.join(analysis, DATABASE)       # where the records are
    if not os.path.isfile(database_path):                  # step 3 has to be done
        refuse("no database: " + database_path)
    if not os.path.isdir(project):                         # the live code has to be there
        refuse("no project directory: " + project)

    manifest = check_snapshot(analysis)                    # the snapshot is intact
    check_split(analysis)                                  # nothing was left unsplit

    database = sqlite3.connect("file:" + database_path + "?mode=ro", uri=True)
    try:
        total = database.execute(                          # counted from the database
            "SELECT COUNT(*) FROM statements").fetchone()[0]
        last_id = database.execute(                        # the end the reading must reach
            "SELECT MAX(id) FROM statements").fetchone()[0]
        check_reading(analysis, last_id)                   # step 2 went to the end
        demoted = check_entries(analysis, database)        # entries valid and visited
        check_traversal(database)                          # no open round, no queue
        check_machine(analysis, database)                  # the machine finished, if it ran
        check_fill_sums(analysis, database)                # the graphs are the filled ones
        check_classification(database)                     # one category per statement
        check_links_agree(database)                        # columns and links agree

        reached = database.execute(                        # the first kind
            "SELECT COUNT(*) FROM statements WHERE visited=1").fetchone()[0]
        rows = database.execute(                           # the candidates
            "SELECT id, file, first_line, last_line, inputs, outputs, "
            "machine_state, reviewed FROM statements "
            "WHERE visited IS NULL ORDER BY id").fetchall()
    finally:
        database.close()                                   # closed even if something threw

    live_hash = {}                                         # live file -> checksum, once each
    def drift_of(relative):
        """How the live file stands against the snapshot: same, changed, gone."""
        if relative not in live_hash:                      # each file is read once
            path = os.path.join(project, relative.replace("/", os.sep))
            if not os.path.isfile(path):                   # the live file vanished
                live_hash[relative] = "missing"
            else:                                          # compare with the manifest
                same = file_sha256(path) == manifest["files"].get(relative)
                live_hash[relative] = "same" if same else "changed"
        return live_hash[relative]

    table_path = os.path.join(analysis, TABLE)             # the table
    with io.open(table_path, "w", encoding="utf-8", newline="\n") as table:
        table.write("id\tfile\tfirst_line\tlast_line\tlines\tinputs\toutputs"
                    "\tmachine_state\treviewed\tlive_file\n")
        for number, name, first, last, entering, leaving, mstate, reviewed in rows:
            table.write("%d\t%s\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\n"
                        % (number, name, first, last, last - first + 1,
                           entering or "", leaving or "", mstate or "",
                           "yes" if reviewed else "", drift_of(name)))

    document_path = os.path.join(analysis, DOCUMENT)       # the document
    with io.open(document_path, "w", encoding="utf-8", newline="\n") as document:
        document.write("# Statements to be checked in the live code\n\n")
        document.write(
            "Every statement below is a CANDIDATE for checking, never a "
            "verdict. It is here because nothing the execution reaches leads "
            "to it. A name assembled while the program runs, a rule used "
            "inside its own file, a framework that reads a value instead of "
            "calling a function - each of those can put a living statement on "
            "this list. Check every one in the live code before anything is "
            "touched.\n\n")
        document.write("| | |\n| --- | --- |\n")
        document.write("| SPIDER version | " + VERSION + " |\n")
        document.write("| Statements in the project | %d |\n" % total)
        document.write("| Proven or established as used | %d |\n" % reached)
        document.write("| **Candidates to check** | **%d** |\n\n" % len(rows))
        # Findings that are not statements of the list: files whose syntax
        # could not be split, and directives demoted from the entry list.
        # Both were established mechanically and belong in front of the eyes.
        split_path = os.path.join(analysis, "split-report.json")
        broken = []
        if os.path.isfile(split_path):                     # written by step 1
            with io.open(split_path, encoding="utf-8") as fh:
                broken = json.load(fh).get("files_not_split", [])
        if broken:                                         # syntax findings, named
            document.write("## Files that could not be split - syntax "
                           "findings\n\n")
            for item in broken:
                document.write("- `%s` - %s\n" % (item.get("file", "?"),
                                                  item.get("reason", "?")))
            document.write("\n")
        quarantined = manifest.get("quarantined", [])      # named by the copy
        if quarantined:                                    # files nobody could read
            document.write("## Files quarantined at the copy - not UTF-8\n\n")
            document.write(
                "These files could not be read as UTF-8, so nothing about "
                "them is proven: they are neither split nor searched. Each "
                "one has to be looked at by hand.\n\n")
            for item in quarantined:
                document.write("- `%s` - %s\n" % (item.get("file", "?"),
                                                  item.get("reason", "?")))
            document.write("\n")
        # Supported files that appeared in the live project after the
        # snapshot. They are not part of this analysis - which is exactly
        # why they are named: code the analysis never saw is code the list
        # says nothing about.
        SUPPORTED = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                     ".css", ".sh")
        known = set(manifest["files"])
        register_path = os.path.join(analysis, "source-scope.tsv")
        if os.path.isfile(register_path):                  # a registered exclusion
            with io.open(register_path, encoding="utf-8") as fh:
                for line in fh:                            # is accounted for, not new
                    piece = line.split("\t", 1)[0].strip()
                    if piece and not piece.startswith("#"):
                        known.add(piece)
        appeared = []
        for walk_root, walk_dirs, walk_files in os.walk(project):
            walk_dirs[:] = [d for d in walk_dirs
                            if d not in (".git", "node_modules")]
            for walk_name in walk_files:
                if not walk_name.lower().endswith(SUPPORTED):
                    continue
                relative = os.path.relpath(
                    os.path.join(walk_root, walk_name),
                    project).replace(os.sep, "/")
                if relative not in known:
                    appeared.append(relative)
        if appeared:
            document.write("## Live files the snapshot never saw\n\n")
            document.write(
                "Supported code files present in the live project and "
                "absent from this snapshot - excluded at step 1 or born "
                "after it. The list below says nothing about them.\n\n")
            for relative in sorted(appeared)[:200]:
                document.write("- `%s`\n" % relative)
            if len(appeared) > 200:
                document.write("- ... and %d more\n" % (len(appeared) - 200))
            document.write("\n")
        if demoted:                                        # the directive findings
            document.write("## Directives demoted from the entry list\n\n")
            document.write(
                "A `'use client'` or `'use server'` directive is read by the "
                "bundler only when something imports the file. These files "
                "nothing imports, so their directives are not entries and "
                "every statement of those files stands in the list below.\n\n")
            for entry in sorted(demoted):
                row = None
                for number, name, first, last, *_ in rows:
                    if number == entry:
                        row = (name, first, last)
                        break
                if row:
                    document.write("- statement %d - `%s` lines %d-%d\n"
                                   % (entry, row[0], row[1], row[2]))
                else:
                    document.write("- statement %d\n" % entry)
            document.write("\n")
        document.write("The code below comes from the verified snapshot. The "
                       "live file is only compared against it: `live: same` "
                       "means it has not moved, `live: changed` means it has, "
                       "and the lines may sit elsewhere now.\n\n")
        document.write("The live code is in:\n\n    %s\n\n---\n" % project)

        source_root = os.path.join(analysis, SOURCE_DIR)   # the snapshot the code comes from
        for number, name, first, last, entering, leaving, mstate, reviewed in rows:
            drift = drift_of(name)                         # same, changed or missing
            document.write("\n## Statement %d\n\n" % number)
            document.write("| | |\n| --- | --- |\n")
            document.write("| File | `%s` |\n" % name)
            document.write("| Lines | %d to %d (%d lines) |\n"
                           % (first, last, last - first + 1))
            document.write("| Ids that send in | %s |\n" % (entering or "none"))
            document.write("| Ids it sends to | %s |\n" % (leaving or "none"))
            document.write("| Machine state | %s |\n" % (mstate or "not recorded"))
            document.write("| Human review | %s |\n"
                           % ("yes, see review.md" if reviewed else "no"))
            document.write("| Live file | %s |\n\n" % drift)
            document.write("**The code, from the verified snapshot:**\n\n```\n")
            snapshot_file = os.path.join(source_root, name.replace("/", os.sep))
            text = io.open(snapshot_file, encoding="utf-8",
                           errors="replace").read()        # the snapshot always reads
            lines = text.split("\n")                       # its lines
            if last > len(lines):                          # a range past the file's end
                refuse("statement " + str(number) + " points past the end of "
                       "the snapshot file " + name + ". The base and the "
                       "snapshot disagree - this is damage, not drift.")
            for line_number in range(first, last + 1):     # only the statement's own lines
                document.write("%5d | %s\n" % (line_number, lines[line_number - 1]))
            document.write("```\n")
            if drift != "same":                            # the live file moved
                document.write("\n**The live file is " + drift + ". Find the "
                               "statement by its text, not by these line "
                               "numbers.**\n")

    print("Statements in the project:", total)             # from the database
    print("Proven or established used:", reached)
    print("Candidates to check:      ", len(rows))
    drifted = sum(1 for v in live_hash.values() if v != "same")
    if drifted:                                            # named, never passed over
        print("Live files that moved:    ", drifted)
    if appeared:
        print("Live files never seen:    ", len(appeared))
    print("Document:", document_path)
    print("Document SHA-256:", file_sha256(document_path)) # so the file can be
    print("Table:   ", table_path)                         # proven untouched later
    return 0                                               # success


def main():
    """One command only: build."""
    parser = argparse.ArgumentParser(prog="final_list.py",
                                     description="SPIDER - step 7")
    commands = parser.add_subparsers(dest="command", required=True)
    build_command = commands.add_parser("build")           # the only one
    build_command.add_argument("--analysis", required=True)  # the analysis directory
    build_command.add_argument("--project", required=True)   # the live code
    arguments = parser.parse_args()                        # read them
    return build(arguments.analysis, arguments.project)    # and do the work


if __name__ == "__main__":                                 # when run directly
    sys.exit(main())                                       # the exit code is the result
