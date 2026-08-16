"""SPIDER - step 3: create the analysis database.

    database.py init --analysis <analysis directory>

Reads the statement list and creates analysis.db in the same directory: one
record per statement, with only the id filled in. Everything else stays empty
and is filled during the traversal.

The database is created only after both the statement list and the entry point
list are ready.
"""

import argparse
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

STATEMENTS = "statements.txt"
ENTRY_POINTS = "entry-points.txt"
DATABASE = "analysis.db"

SCHEMA = """
CREATE TABLE statements (
    id          INTEGER PRIMARY KEY,
    inputs      TEXT,
    outputs     TEXT,
    visited     INTEGER,
    is_source   INTEGER,
    is_sink     INTEGER,
    unresolved  INTEGER
);

CREATE TABLE pending_queue (
    id INTEGER PRIMARY KEY
);
"""


def read_ids(path):
    ids = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            head = line.split(" | ", 1)[0].strip()
            if not head.isdigit():
                raise SystemExit(
                    "Line " + str(line_number)
                    + " of the statement list does not start with an id: "
                    + line[:60]
                )
            ids.append(int(head))
    return ids


def init(analysis):
    analysis = os.path.abspath(analysis)
    statements_path = os.path.join(analysis, STATEMENTS)
    entry_points_path = os.path.join(analysis, ENTRY_POINTS)
    database_path = os.path.join(analysis, DATABASE)

    if not os.path.isfile(statements_path):
        raise SystemExit("No statement list: " + statements_path)
    if not os.path.isfile(entry_points_path):
        raise SystemExit("No entry point list: " + entry_points_path)
    if os.path.exists(database_path):
        raise SystemExit(
            "The database already exists: " + database_path + "\n"
            "It is never overwritten. Removing it is the owner's decision."
        )

    ids = read_ids(statements_path)
    if not ids:
        raise SystemExit("The statement list is empty: " + statements_path)

    duplicates = len(ids) - len(set(ids))
    if duplicates:
        raise SystemExit("The statement list has duplicate ids: " + str(duplicates))

    database = sqlite3.connect(database_path)
    try:
        database.executescript(SCHEMA)
        database.executemany(
            "INSERT INTO statements (id) VALUES (?)", [(i,) for i in ids]
        )
        database.commit()
        in_database = database.execute(
            "SELECT COUNT(*) FROM statements").fetchone()[0]
        in_queue = database.execute(
            "SELECT COUNT(*) FROM pending_queue").fetchone()[0]
        filled = database.execute(
            "SELECT COUNT(*) FROM statements WHERE inputs IS NOT NULL "
            "OR outputs IS NOT NULL OR visited IS NOT NULL "
            "OR is_source IS NOT NULL OR is_sink IS NOT NULL "
            "OR unresolved IS NOT NULL"
        ).fetchone()[0]
    finally:
        database.close()

    if in_database != len(ids):
        raise SystemExit(
            "The counts do not match: in the list " + str(len(ids))
            + ", in the database " + str(in_database)
        )

    entry_point_count = 0
    with open(entry_points_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                entry_point_count += 1

    print("Statements in the list:        " + str(len(ids)))
    print("Records in the database:       " + str(in_database))
    print("Fields filled besides the id:  " + str(filled))
    print("Records in the pending queue:  " + str(in_queue))
    print("Entry points listed:           " + str(entry_point_count))
    print("Database: " + database_path)
    return 0


def main():
    parser = argparse.ArgumentParser(prog="database.py",
                                     description="SPIDER - step 3")
    commands = parser.add_subparsers(dest="command", required=True)
    init_command = commands.add_parser("init")
    init_command.add_argument("--analysis", required=True)
    arguments = parser.parse_args()
    return init(arguments.analysis)


if __name__ == "__main__":
    sys.exit(main())
