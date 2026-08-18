"""SPIDER - step 5: traversal and filling of the database.

The program decides nothing about the statements. It only:
  - names the next statement, following the movement rules;
  - records in the database what the intelligence has established;
  - keeps the pending queue.

Which ids go in and which go out is decided by the intelligence.

    traverse.py next   --analysis <dir>
    traverse.py record --analysis <dir> --id N --inputs "1,2" --outputs "5,7"
                       [--unresolved]
    traverse.py report --analysis <dir>

Every line below carries a comment. Nothing here can halt the analysis. The
refusals all fire before anything is written and each one names what to do:
no database, no statement list, no entry point list; an id that is not in the
database; a statement recorded twice; and the contract of the round - record
accepts only the id the last `next` handed over, and refuses everything else.
A statement that cannot be understood is not a refusal - it is recorded with
--unresolved and the work goes on.
"""

import argparse                                   # reads the command line
import json                                       # the answers are JSON lines
import os                                         # paths and checks
import sqlite3                                    # the database
import sys                                        # exit code and stdout

if hasattr(sys.stdout, "reconfigure"):            # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")      # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")      # statement text may hold any alphabet

STATEMENTS = "statements.txt"                     # made by step 1
ENTRY_POINTS = "entry-points.txt"                 # made by step 2
DATABASE = "analysis.db"                          # made by step 3

WORKING_TABLES = """
CREATE TABLE IF NOT EXISTS traversal_state (
    key   TEXT PRIMARY KEY,                       -- only one key is used: 'next'
    value TEXT                                    -- the id the path continues to
);

CREATE TABLE IF NOT EXISTS line_index (
    id     INTEGER PRIMARY KEY,                   -- the id of a statement
    offset INTEGER                                -- where its line begins in the file
);
"""


# --------------------------------------------------------------------------

def open_analysis(analysis):
    """Opens the database and makes sure the two working tables exist."""
    analysis = os.path.abspath(analysis)                   # full path only
    database_path = os.path.join(analysis, DATABASE)       # where the database is
    if not os.path.isfile(database_path):                  # step 3 has to be done first
        raise SystemExit("No database: " + database_path)
    database = sqlite3.connect(database_path)              # open it
    database.executescript(WORKING_TABLES)                 # create the working tables if new
    database.commit()                                      # and keep them
    return analysis, database                              # both are needed everywhere


def build_line_index(analysis, database):
    """Remembers where every statement line starts, so any id is read at once."""
    already = database.execute("SELECT COUNT(*) FROM line_index").fetchone()[0]
    if already:                                            # built once, on the first round
        return                                             # and never again
    path = os.path.join(analysis, STATEMENTS)              # the statement list
    if not os.path.isfile(path):                           # without it nothing can be read
        raise SystemExit("No statement list: " + path)
    rows = []                                              # id and offset pairs
    with open(path, "rb") as fh:                           # bytes, so the offsets are exact
        offset = 0                                         # where the current line begins
        for raw in fh:                                     # line by line
            text = raw.decode("utf-8", "replace").strip()  # a damaged byte never stops us
            if text:                                       # a blank line has no id
                head = text.split(" | ", 1)[0].strip()     # the part before the first separator
                if head.isdigit():                         # a real id
                    rows.append((int(head), offset))       # remember where it sits
            offset += len(raw)                             # the next line starts after this one
    database.executemany("INSERT OR REPLACE INTO line_index VALUES (?, ?)", rows)
    database.commit()                                      # kept for every later round


def read_statement(analysis, database, statement_id):
    """Reads one statement line by its id, through the index."""
    row = database.execute(
        "SELECT offset FROM line_index WHERE id=?", (statement_id,)).fetchone()
    if row is None:                                        # an id the list does not hold
        return None                                        # the caller says so plainly
    with open(os.path.join(analysis, STATEMENTS), "rb") as fh:  # bytes again
        fh.seek(row[0])                                    # jump straight to the line
        line = fh.readline().decode("utf-8", "replace").rstrip("\r\n")  # read just that one
    parts = line.split(" | ", 3)                           # id, file, lines, text
    if len(parts) < 4:                                     # a line of another shape
        return {"id": statement_id, "line": line}          # is handed over whole
    return {
        "id": statement_id,                                # the id
        "file": parts[1],                                  # which file it comes from
        "lines": parts[2],                                 # which lines it occupies
        "text": parts[3],                                  # and its text
    }


def get_state(database, key):
    """Reads one value out of the small state table."""
    row = database.execute(
        "SELECT value FROM traversal_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else None                         # nothing stored yet is fine


def set_state(database, key, value):
    """Writes one value into the small state table."""
    database.execute(
        "INSERT INTO traversal_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",  # write or overwrite
        (key, value),
    )


def is_visited(database, statement_id):
    """True when the traversal has already recorded this statement."""
    row = database.execute(
        "SELECT visited FROM statements WHERE id=?", (statement_id,)).fetchone()
    return bool(row and row[0])                            # missing or empty means not visited


def read_entry_points(analysis):
    """Reads the entry point list, in the order step 2 wrote it."""
    path = os.path.join(analysis, ENTRY_POINTS)            # where it is
    if not os.path.isfile(path):                           # step 2 has to be done first
        raise SystemExit("No entry point list: " + path)
    ids = []                                               # in file order
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()                            # drop the newline
            if line and line.isdigit():                    # only ids count
                ids.append(int(line))
    return ids


def read_demoted(analysis):
    """The entries the load graph demoted: directives in unimported files.

    Mirrors machine_links.read_demoted, so that the traversal never opens a
    round on a statement the walk already refused to start from."""
    path = os.path.join(analysis, "demoted-entries.txt")   # written by load_links
    demoted = set()
    if os.path.isfile(path):                               # the file is optional
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                piece = line.split("\t", 1)[0].strip()     # the id column
                if piece.isdigit():
                    demoted.add(int(piece))
    return demoted


# --------------------------------------------------------------------------

def next_statement(analysis_path):
    """Names the next statement. Three sources, in this order."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        build_line_index(analysis, database)               # built on the first round
        demoted = read_demoted(analysis)                   # directives that are not entries

        planned = get_state(database, "next")              # first: the path we are on
        if planned:                                        # the previous round named one
            statement_id = int(planned)
            if statement_id in demoted:                    # named before its demotion
                set_state(database, "next", "")            # a demoted directive is a
                database.commit()                          # finding, never a round
            elif not is_visited(database, statement_id):   # still unvisited
                show(read_statement(analysis, database, statement_id), "path")
                return 0                                   # hand it over
            else:
                set_state(database, "next", "")            # it got visited another way
                database.commit()                          # so the path is closed

        row = database.execute("SELECT MIN(id) FROM pending_queue").fetchone()
        if row and row[0] is not None:                     # second: the pending queue
            set_state(database, "next", str(row[0]))       # what record may now accept
            database.commit()                              # remembered before the answer
            show(read_statement(analysis, database, row[0]), "pending queue")
            return 0                                       # always the smallest id

        for statement_id in read_entry_points(analysis):   # third: the entry points
            if statement_id in demoted:                    # the load graph proved this
                continue                                   # directive is not an entry
            if not is_visited(database, statement_id):     # the first unvisited one
                set_state(database, "next", str(statement_id))  # what record may now accept
                database.commit()                          # remembered before the answer
                show(read_statement(analysis, database, statement_id), "entry point")
                return 0

        print(json.dumps({"end": "TRAVERSAL STOPS"}, ensure_ascii=False))  # nowhere left to go
        return 0
    finally:
        database.close()                                   # closed even if something threw


def show(statement, came_from):
    """Prints one statement as a JSON line, saying where it came from."""
    if statement is None:                                  # the id is not in the list
        print(json.dumps({"error": "this id is not in the statement list"},
                         ensure_ascii=False))
        return
    statement = dict(statement)                            # a copy, so nothing is disturbed
    statement["came_from"] = came_from                     # path, pending queue or entry point
    print(json.dumps(statement, ensure_ascii=False))       # any alphabet survives this


# --------------------------------------------------------------------------

def split_ids(text):
    """Turns "1,2" into [1, 2]. An empty string means no ids."""
    if not text:                                           # "" is a legitimate answer
        return []                                          # it means: none
    ids = []
    for piece in text.replace(";", ",").split(","):        # commas or semicolons
        piece = piece.strip()                              # spaces do not matter
        if not piece:                                      # a double comma
            continue                                       # is simply skipped
        if not piece.isdigit():                            # anything that is not a number
            raise SystemExit("Not an id: " + piece)        # is named, never guessed at
        ids.append(int(piece))
    return sorted(set(ids))                                # in order, without repeats


def record(analysis_path, statement_id, inputs_text, outputs_text, unresolved):
    """Writes down what the intelligence established, and names the next statement.

    The contract of the round is enforced here: record accepts only the id the
    last `next` handed over. The program holds the path and the queue exactly
    so that the intelligence cannot lose them; a record of some other id would
    be the intelligence choosing the path after all. Everything the record
    changes - the statement, the queue, the planned next - lands in a single
    transaction, so an interrupted record leaves no half-written state.
    """
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        build_line_index(analysis, database)               # in case this is the first call

        planned_now = get_state(database, "next")          # what the last `next` handed over
        if not planned_now:                                # no round is open
            raise SystemExit(
                "No statement has been handed over. Ask `next` first; record "
                "accepts only the id it answers with.")
        if str(statement_id) != planned_now:               # a different id than handed
            raise SystemExit(
                "The last `next` handed over statement " + planned_now
                + ", not " + str(statement_id) + ". Record accepts only the "
                "id `next` answered with - the program holds the path, not "
                "the intelligence.")

        if database.execute("SELECT 1 FROM statements WHERE id=?",
                            (statement_id,)).fetchone() is None:   # an id that does not exist
            raise SystemExit("No such statement in the database: " + str(statement_id))
        if is_visited(database, statement_id):             # a statement is recorded once
            raise SystemExit(
                "Statement " + str(statement_id)
                + " has already been visited. It is never recorded twice."
            )

        inputs = split_ids(inputs_text)                    # who sends information in
        outputs = split_ids(outputs_text)                  # who it sends information to

        for other in inputs + outputs:                     # every id named must exist
            if database.execute("SELECT 1 FROM statements WHERE id=?",
                                (other,)).fetchone() is None:
                raise SystemExit(
                    "Id " + str(other) + " is not in the database. If the statement "
                    "points at something that is not in the program, it is unresolved."
                )

        is_source = 1 if (outputs and not inputs) else None    # the definition of a source
        is_sink = 1 if not outputs else None                   # the definition of a sink

        database.execute(                                  # the record is filled in
            "UPDATE statements SET inputs=?, outputs=?, visited=1, "
            "visited_by='intelligence', "                  # who set the mark
            "is_source=?, is_sink=?, unresolved=? WHERE id=?",
            (
                ",".join(str(x) for x in inputs),          # stored as text
                ",".join(str(x) for x in outputs),         # so it can be read by eye
                is_source,                                 # the source mark
                is_sink,                                   # the sink mark
                1 if unresolved else None,                 # the unresolved mark
                statement_id,
            ),
        )
        try:                                               # the same links, as evidence rows
            database.executemany(                          # sender -> receiver, stated
                "INSERT OR IGNORE INTO links (source, target, kind, origin) "
                "VALUES (?, ?, 'STATED', 'intelligence')",
                [(other, statement_id) for other in inputs]      # who sends into it
                + [(statement_id, other) for other in outputs])  # and who it sends to
            import machine_links                           # the one place columns derive from
            machine_links.rebuild_columns(                 # both ends of every stated link
                database, set([statement_id]) | set(inputs) | set(outputs))
        except sqlite3.OperationalError:                   # a base from before the links table
            pass                                           # keeps working on its columns alone
        database.execute("DELETE FROM pending_queue WHERE id=?", (statement_id,))  # done waiting

        planned = ""                                       # where the path goes next
        queued = []                                        # what goes into the queue
        if not unresolved:                                 # an unresolved statement ends the path
            unvisited = [o for o in outputs if not is_visited(database, o)]  # where we may go
            if unvisited:
                planned = str(unvisited[0])                # the smallest id continues the path
                for other in unvisited[1:]:                # the rest wait their turn
                    database.execute(
                        "INSERT OR IGNORE INTO pending_queue (id) VALUES (?)", (other,)
                    )
                    queued.append(other)

        set_state(database, "next", planned)               # remembered for the next round
        database.commit()                                  # everything written together

        print(json.dumps({                                 # the answer of this round
            "recorded": statement_id,                      # which statement
            "is_source": bool(is_source),                  # what marks it got
            "is_sink": bool(is_sink),
            "unresolved": bool(unresolved),
            "next": int(planned) if planned else None,     # which one comes next
            "added_to_queue": queued,                      # what waits
            "path_ended": planned == "",                   # and whether the path is over
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()                                   # closed even if something threw


# --------------------------------------------------------------------------

def report(analysis_path):
    """Every number here is counted from the database, never from memory."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        count = lambda query: database.execute(query).fetchone()[0]   # one number per query
        entry_points = read_entry_points(analysis)         # from the file
        demoted = read_demoted(analysis)                   # directives that are not entries
        unvisited_entry_points = [e for e in entry_points  # which of them still wait
                                  if e not in demoted
                                  and not is_visited(database, e)]
        numbers = {
            "demoted_entries": len(demoted),               # findings, never rounds
            "statements": count("SELECT COUNT(*) FROM statements"),                    # all of them
            "visited": count("SELECT COUNT(*) FROM statements WHERE visited=1"),       # first kind
            "unvisited": count("SELECT COUNT(*) FROM statements WHERE visited IS NULL"),  # second kind
            "sources": count("SELECT COUNT(*) FROM statements WHERE is_source=1"),     # no inputs
            "sinks": count("SELECT COUNT(*) FROM statements WHERE is_sink=1"),         # no outputs
            "unresolved": count("SELECT COUNT(*) FROM statements WHERE unresolved=1"), # for step 6
            "pending_queue": count("SELECT COUNT(*) FROM pending_queue"),              # still waiting
            "entry_points": len(entry_points),                                         # from step 2
            "unvisited_entry_points": len(unvisited_entry_points),                     # still to do
        }
        for key in numbers:                                # printed in that order
            print(key + ": " + str(numbers[key]))
        return 0
    finally:
        database.close()                                   # closed even if something threw


# --------------------------------------------------------------------------

def main():
    """Three commands: next, record, report."""
    parser = argparse.ArgumentParser(prog="traverse.py",       # the program name in the help
                                     description="SPIDER - step 5")
    commands = parser.add_subparsers(dest="command", required=True)  # a command is required

    next_command = commands.add_parser("next")                 # which statement comes next
    next_command.add_argument("--analysis", required=True)     # the analysis directory

    record_command = commands.add_parser("record")             # write down what was established
    record_command.add_argument("--analysis", required=True)   # the analysis directory
    record_command.add_argument("--id", required=True, type=int)   # which statement
    record_command.add_argument("--inputs", required=True)     # who sends information in
    record_command.add_argument("--outputs", required=True)    # who it sends information to
    record_command.add_argument("--unresolved", action="store_true")  # not understood yet

    report_command = commands.add_parser("report")             # the numbers
    report_command.add_argument("--analysis", required=True)   # the analysis directory

    arguments = parser.parse_args()                            # read them
    if arguments.command == "next":                            # and do the work
        return next_statement(arguments.analysis)
    if arguments.command == "record":
        return record(arguments.analysis, arguments.id, arguments.inputs,
                      arguments.outputs, arguments.unresolved)
    return report(arguments.analysis)


if __name__ == "__main__":                                     # when run directly
    sys.exit(main())                                           # the exit code is the result
