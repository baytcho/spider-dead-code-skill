"""SPIDER - step 3: create the analysis database.

    database.py init --analysis <analysis directory>

Reads the statement list and creates analysis.db in the same directory: one
record per statement, carrying the id and the address - the file the statement
comes from and the line numbers it occupies in that file. Everything the
analysis establishes stays empty and is filled by the steps that follow.

The database is created only after both the statement list and the entry point
list are ready. The entry points are validated here: an empty list, an id that
is no statement and a duplicated id are all refused by name.

Every line below carries a comment. Nothing in this file can halt the analysis:
the refusals here all fire before any record is written, and each of them names
the exact file that is missing or wrong.
"""

import argparse                                   # reads the command line
import os                                         # joins paths, checks files
import sqlite3                                    # the database itself
import sys                                        # exit code and stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the scripts directory itself
from version import VERSION, SCHEMA as SCHEMA_VERSION  # the one place the numbers live

if hasattr(sys.stdout, "reconfigure"):            # modern Python has this
    sys.stdout.reconfigure(encoding="utf-8")      # force UTF-8 out
    sys.stderr.reconfigure(encoding="utf-8")      # so non-Latin text never breaks it

STATEMENTS = "statements.txt"                     # made by step 1
ENTRY_POINTS = "entry-points.txt"                 # made by step 2
DATABASE = "analysis.db"                          # made here, in step 3
CSS_SELECTORS = "css-selectors.tsv"               # made by step 1 for style sheets, when any exist

SCHEMA = """
CREATE TABLE statements (
    id            INTEGER PRIMARY KEY,            -- the id from the statement list
    file          TEXT,                           -- the file the statement comes from
    first_line    INTEGER,                        -- the first line it occupies in that file
    last_line     INTEGER,                        -- the last line it occupies in that file
    inputs        TEXT,                           -- which ids send information in
    outputs       TEXT,                           -- which ids it sends information to
    visited       INTEGER,                        -- 1 once a walk or a record filled it in
    visited_by    TEXT,                           -- who set the mark: machine or intelligence
    machine_state TEXT,                           -- the machine axis: reached, unreached, untouched, unsupported
    reviewed      INTEGER,                        -- 1 once step 6 wrote a decision for it
    is_source     INTEGER,                        -- 1 when it has outputs and no inputs
    is_sink       INTEGER,                        -- 1 when it has no outputs
    unresolved    INTEGER                         -- 1 when it is not understood yet
);

CREATE TABLE pending_queue (
    id INTEGER PRIMARY KEY                        -- ids waiting to be visited
);

CREATE TABLE links (
    source INTEGER,                               -- the statement that needs the other one
    target INTEGER,                               -- the statement it needs
    kind   TEXT,                                  -- what proved the link: CALL, REF, REACHING_DEF, STATED, ...
    origin TEXT,                                  -- who recorded it: machine or intelligence
    PRIMARY KEY (source, target, kind, origin)    -- the same proof is never written twice
);

CREATE TABLE css_selectors (
    statement_id INTEGER,                         -- the parent rule in the statement list
    ordinal      INTEGER,                         -- which name in the rule, counted from 1
    selector     TEXT,                            -- the name itself, as written
    line         INTEGER,                         -- the line the name starts on
    PRIMARY KEY (statement_id, ordinal)           -- one row per name of the rule
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,                       -- the name of the fact
    value TEXT                                    -- the fact itself
);

CREATE INDEX statements_by_file ON statements (file);      -- for the address look-ups
CREATE INDEX statements_by_visited ON statements (visited);-- for the reports
CREATE INDEX links_by_source ON links (source);            -- for the walks
CREATE INDEX links_by_target ON links (target);            -- for the reverse checks
"""


def read_statements(path):
    """Reads the id and the address from every line of the statement list."""
    rows = []                                                  # collected here
    with open(path, "r", encoding="utf-8") as fh:              # the list is UTF-8
        for line_number, line in enumerate(fh, 1):             # count from 1 for the message
            line = line.rstrip("\r\n")                         # drop the newline, keep the text
            if not line.strip():                               # a blank line
                continue                                       # is skipped
            columns = line.split(" | ", 3)                     # id, file, first-last, text
            head = columns[0].strip()                          # everything before the first separator
            if not head.isdigit():                             # it has to be an id
                raise SystemExit(                              # a broken list is named, not guessed at
                    "Line " + str(line_number)                 # which line
                    + " of the statement list does not start with an id: "
                    + line[:60]                                # and what it holds
                )
            if len(columns) < 3:                               # the address has to be there as well
                raise SystemExit(                              # without it the record cannot be filled
                    "Line " + str(line_number)                 # which line
                    + " of the statement list carries no address: "
                    + line[:60]                                # and what it holds
                )
            source_file = columns[1].strip()                   # the file the statement comes from
            span = columns[2].strip().split("-")               # first-last, the original line numbers
            if len(span) != 2 or not span[0].isdigit() or not span[1].isdigit():
                raise SystemExit(                              # a damaged address is named, not guessed at
                    "Line " + str(line_number)                 # which line
                    + " of the statement list has a broken address: "
                    + columns[2][:40]                          # and what stands in its place
                )
            rows.append((int(head), source_file,               # the id and the file
                         int(span[0]), int(span[1])))          # the first and the last line
    return rows                                                # in file order


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

    rows = read_statements(statements_path)                    # every id with its address, in order
    ids = [row[0] for row in rows]                             # the ids alone, for the checks below
    if not ids:                                                # an empty list means step 1 failed
        raise SystemExit("The statement list is empty: " + statements_path)

    duplicates = len(ids) - len(set(ids))                      # the same id twice would break the base
    if duplicates:                                             # so it is caught here
        raise SystemExit("The statement list has duplicate ids: " + str(duplicates))

    known = set(ids)                                           # for validating the entry points
    entries = []                                               # the entry point ids, in file order
    with open(entry_points_path, "r", encoding="utf-8") as fh: # the list step 2 wrote
        for line_number, line in enumerate(fh, 1):             # count from 1 for the message
            piece = line.strip()                               # one id per line
            if not piece:                                      # a blank line
                continue                                       # is skipped
            if not piece.isdigit():                            # anything that is not an id
                raise SystemExit(                              # is named, never guessed at
                    "Line " + str(line_number) + " of the entry point list is "
                    "not an id: " + piece[:40])
            number = int(piece)                                # the id itself
            if number not in known:                            # an entry that is no statement
                raise SystemExit(                              # would derail the traversal
                    "Entry point " + str(number) + " on line " + str(line_number)
                    + " is not in the statement list.")
            if number in entries:                              # the same entry twice
                raise SystemExit(                              # is a damaged list, not a wish
                    "Entry point " + str(number) + " appears twice, the second "
                    "time on line " + str(line_number) + ".")
            entries.append(number)                             # keep it
    if not entries:                                            # an empty entry list
        raise SystemExit(                                      # means step 2 did not happen
            "The entry point list is empty: " + entry_points_path + "\n"
            "A traversal with no entry points proves nothing. Finish step 2.")

    selector_rows = []                                         # the names of the style rules
    selectors_path = os.path.join(analysis, CSS_SELECTORS)     # written by step 1, when any
    if os.path.isfile(selectors_path):                         # a project with no styles has none
        with open(selectors_path, "r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, 1):         # count from 1 for the message
                line = line.rstrip("\n")                       # drop the newline
                if not line.strip() or line.startswith("statement_id"):  # blank or heading
                    continue                                   # is skipped
                columns = line.split("\t")                     # id, ordinal, selector, line
                if len(columns) != 4 or not columns[0].isdigit() \
                        or not columns[1].isdigit() or not columns[3].isdigit():
                    raise SystemExit(                          # a damaged row is named
                        "Line " + str(line_number) + " of " + CSS_SELECTORS
                        + " is broken: " + line[:60])
                if int(columns[0]) not in known:               # a name of no statement
                    raise SystemExit(
                        "Line " + str(line_number) + " of " + CSS_SELECTORS
                        + " names statement " + columns[0] + " which does not exist.")
                selector_rows.append((int(columns[0]), int(columns[1]),
                                      columns[2], int(columns[3])))

    database = sqlite3.connect(database_path)                  # creates the file
    try:
        database.executescript(SCHEMA)                         # the tables and the indexes
        database.executemany(                                  # one row per statement
            "INSERT INTO statements (id, file, first_line, last_line) "  # the id and the address
            "VALUES (?, ?, ?, ?)", rows                        # exactly as the list holds them
        )
        database.executemany(                                  # one row per style-rule name
            "INSERT INTO css_selectors (statement_id, ordinal, selector, line) "
            "VALUES (?, ?, ?, ?)", selector_rows               # exactly as step 1 wrote them
        )
        database.executemany(                                  # the facts every later step checks
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [("created_by", "spider"),                         # only a base made here is trusted
             ("spider_version", VERSION),                      # which code wrote it
             ("schema_version", str(SCHEMA_VERSION))],         # which layout it has
        )
        database.commit()                                      # written to disk
        in_database = database.execute(                        # count the rows back
            "SELECT COUNT(*) FROM statements").fetchone()[0]   # from the database itself
        with_address = database.execute(                       # every record must carry its address
            "SELECT COUNT(*) FROM statements WHERE file IS NOT NULL "
            "AND first_line IS NOT NULL AND last_line IS NOT NULL"
        ).fetchone()[0]                                        # counted from the database, not from memory
        in_queue = database.execute(                           # the queue must start empty
            "SELECT COUNT(*) FROM pending_queue").fetchone()[0]
        filled = database.execute(                             # no field of the analysis may be filled
            "SELECT COUNT(*) FROM statements WHERE inputs IS NOT NULL "
            "OR outputs IS NOT NULL OR visited IS NOT NULL "
            "OR visited_by IS NOT NULL OR machine_state IS NOT NULL "
            "OR reviewed IS NOT NULL "
            "OR is_source IS NOT NULL OR is_sink IS NOT NULL "
            "OR unresolved IS NOT NULL"
        ).fetchone()[0]
        selector_count = database.execute(                     # counted back for the report
            "SELECT COUNT(*) FROM css_selectors").fetchone()[0]
    finally:
        database.close()                                       # closed even if something threw

    if in_database != len(ids):                                # the counts have to agree
        raise SystemExit(
            "The counts do not match: in the list " + str(len(ids))
            + ", in the database " + str(in_database)
        )
    if with_address != in_database:                            # not one record may be left without one
        raise SystemExit(
            "Records without an address: " + str(in_database - with_address)
            + ". Every record carries the file and the line numbers the "
            "statement occupies in it."
        )

    print("Statements in the list:        " + str(len(ids)))       # what step 1 produced
    print("Records in the database:       " + str(in_database))    # what this step produced
    print("Records with an address:       " + str(with_address))   # must equal the records
    print("Analysis fields filled:        " + str(filled))         # must be zero
    print("Records in the pending queue:  " + str(in_queue))       # must be zero
    print("Entry points listed:           " + str(len(entries)))   # validated against the statements
    print("Style rule names recorded:     " + str(selector_count)) # what step 1 found in the styles
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
