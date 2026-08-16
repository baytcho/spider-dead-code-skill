"""SPIDER - step 3: create the analysis database.

    database.py init --analysis <analysis directory>

Reads the statement list and creates analysis.db in the same directory: one
record per statement, with only the id filled in. Everything else stays empty
and is filled during the traversal.

The database is created only after both the statement list and the entry point
list are ready.

Every line below carries a comment. Nothing in this file can halt the analysis:
the refusals here all fire before any record is written, and each of them names
the exact file that is missing or wrong.
"""

import argparse                                   # reads the command line
import os                                         # joins paths, checks files
import sqlite3                                    # the database itself
import sys                                        # exit code and stdout

if hasattr(sys.stdout, "reconfigure"):            # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")      # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")      # so non-Latin text never breaks it

STATEMENTS = "statements.txt"                     # made by step 1
ENTRY_POINTS = "entry-points.txt"                 # made by step 2
DATABASE = "analysis.db"                          # made here, in step 3

SCHEMA = """
CREATE TABLE statements (
    id          INTEGER PRIMARY KEY,              -- the id from the statement list
    inputs      TEXT,                             -- which ids send information in
    outputs     TEXT,                             -- which ids it sends information to
    visited     INTEGER,                          -- 1 once the traversal recorded it
    is_source   INTEGER,                          -- 1 when it has outputs and no inputs
    is_sink     INTEGER,                          -- 1 when it has no outputs
    unresolved  INTEGER                           -- 1 when it is not understood yet
);

CREATE TABLE pending_queue (
    id INTEGER PRIMARY KEY                        -- ids waiting to be visited
);
"""


def read_ids(path):
    """Reads the id at the start of every line of the statement list."""
    ids = []                                                   # collected here
    with open(path, "r", encoding="utf-8") as fh:              # the list is UTF-8
        for line_number, line in enumerate(fh, 1):             # count from 1 for the message
            line = line.strip()                                # drop the newline
            if not line:                                       # a blank line
                continue                                       # is skipped
            head = line.split(" | ", 1)[0].strip()             # everything before the first separator
            if not head.isdigit():                             # it has to be an id
                raise SystemExit(                              # a broken list is named, not guessed at
                    "Line " + str(line_number)                 # which line
                    + " of the statement list does not start with an id: "
                    + line[:60]                                # and what it holds
                )
            ids.append(int(head))                              # keep the id
    return ids                                                 # in file order


def init(analysis):
    """Creates the database: one empty record per statement."""
    analysis = os.path.abspath(analysis)                       # a full path, never a relative one
    statements_path = os.path.join(analysis, STATEMENTS)       # where the list is
    entry_points_path = os.path.join(analysis, ENTRY_POINTS)   # where the entry points are
    database_path = os.path.join(analysis, DATABASE)           # where the database will be

    if not os.path.isfile(statements_path):                    # step 1 has to be done
        raise SystemExit("No statement list: " + statements_path)
    if not os.path.isfile(entry_points_path):                  # step 2 has to be done
        raise SystemExit("No entry point list: " + entry_points_path)
    if os.path.exists(database_path):                          # never destroy finished work
        raise SystemExit(
            "The database already exists: " + database_path + "\n"
            "It is never overwritten. Removing it is the owner's decision."
        )

    ids = read_ids(statements_path)                            # every id, in order
    if not ids:                                                # an empty list means step 1 failed
        raise SystemExit("The statement list is empty: " + statements_path)

    duplicates = len(ids) - len(set(ids))                      # the same id twice would break the base
    if duplicates:                                             # so it is caught here
        raise SystemExit("The statement list has duplicate ids: " + str(duplicates))

    database = sqlite3.connect(database_path)                  # creates the file
    try:
        database.executescript(SCHEMA)                         # the two tables
        database.executemany(                                  # one row per statement
            "INSERT INTO statements (id) VALUES (?)", [(i,) for i in ids]
        )
        database.commit()                                      # written to disk
        in_database = database.execute(                        # count the rows back
            "SELECT COUNT(*) FROM statements").fetchone()[0]   # from the database itself
        in_queue = database.execute(                           # the queue must start empty
            "SELECT COUNT(*) FROM pending_queue").fetchone()[0]
        filled = database.execute(                             # and no field may be filled
            "SELECT COUNT(*) FROM statements WHERE inputs IS NOT NULL "
            "OR outputs IS NOT NULL OR visited IS NOT NULL "
            "OR is_source IS NOT NULL OR is_sink IS NOT NULL "
            "OR unresolved IS NOT NULL"
        ).fetchone()[0]
    finally:
        database.close()                                       # closed even if something threw

    if in_database != len(ids):                                # the counts have to agree
        raise SystemExit(
            "The counts do not match: in the list " + str(len(ids))
            + ", in the database " + str(in_database)
        )

    entry_point_count = 0                                      # counted for the report
    with open(entry_points_path, "r", encoding="utf-8") as fh: # from the file, never from memory
        for line in fh:
            if line.strip():                                   # blank lines do not count
                entry_point_count += 1

    print("Statements in the list:        " + str(len(ids)))       # what step 1 produced
    print("Records in the database:       " + str(in_database))    # what this step produced
    print("Fields filled besides the id:  " + str(filled))         # must be zero
    print("Records in the pending queue:  " + str(in_queue))       # must be zero
    print("Entry points listed:           " + str(entry_point_count))  # what step 2 produced
    print("Database: " + database_path)                            # where it is
    return 0                                                       # success


def main():
    """One command only: init."""
    parser = argparse.ArgumentParser(prog="database.py",       # the program name in the help
                                     description="SPIDER - step 3")
    commands = parser.add_subparsers(dest="command", required=True)  # a command is required
    init_command = commands.add_parser("init")                 # the only one
    init_command.add_argument("--analysis", required=True)     # the analysis directory
    arguments = parser.parse_args()                            # read them
    return init(arguments.analysis)                            # and do the work


if __name__ == "__main__":                                     # when run directly
    sys.exit(main())                                           # the exit code is the result
