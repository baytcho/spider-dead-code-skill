"""SPIDER - step 4: traversal and filling of the database.

The program decides nothing about the statements. It only:
  - names the next statement, following the movement rules;
  - records in the database what the intelligence has established;
  - keeps the pending queue.

Which ids go in and which go out is decided by the intelligence.

    traverse.py next   --analysis <dir>
    traverse.py record --analysis <dir> --id N --inputs "1,2" --outputs "5,7"
                       [--unresolved]
    traverse.py report --analysis <dir>
"""

import argparse
import json
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

STATEMENTS = "statements.txt"
ENTRY_POINTS = "entry-points.txt"
DATABASE = "analysis.db"

WORKING_TABLES = """
CREATE TABLE IF NOT EXISTS traversal_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS line_index (
    id     INTEGER PRIMARY KEY,
    offset INTEGER
);
"""


# --------------------------------------------------------------------------

def open_analysis(analysis):
    analysis = os.path.abspath(analysis)
    database_path = os.path.join(analysis, DATABASE)
    if not os.path.isfile(database_path):
        raise SystemExit("No database: " + database_path)
    database = sqlite3.connect(database_path)
    database.executescript(WORKING_TABLES)
    database.commit()
    return analysis, database


def build_line_index(analysis, database):
    already = database.execute("SELECT COUNT(*) FROM line_index").fetchone()[0]
    if already:
        return
    path = os.path.join(analysis, STATEMENTS)
    if not os.path.isfile(path):
        raise SystemExit("No statement list: " + path)
    rows = []
    with open(path, "rb") as fh:
        offset = 0
        for raw in fh:
            text = raw.decode("utf-8", "replace").strip()
            if text:
                head = text.split(" | ", 1)[0].strip()
                if head.isdigit():
                    rows.append((int(head), offset))
            offset += len(raw)
    database.executemany("INSERT OR REPLACE INTO line_index VALUES (?, ?)", rows)
    database.commit()


def read_statement(analysis, database, statement_id):
    row = database.execute(
        "SELECT offset FROM line_index WHERE id=?", (statement_id,)).fetchone()
    if row is None:
        return None
    with open(os.path.join(analysis, STATEMENTS), "rb") as fh:
        fh.seek(row[0])
        line = fh.readline().decode("utf-8", "replace").rstrip("\r\n")
    parts = line.split(" | ", 3)
    if len(parts) < 4:
        return {"id": statement_id, "line": line}
    return {
        "id": statement_id,
        "file": parts[1],
        "lines": parts[2],
        "text": parts[3],
    }


def get_state(database, key):
    row = database.execute(
        "SELECT value FROM traversal_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_state(database, key, value):
    database.execute(
        "INSERT INTO traversal_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def is_visited(database, statement_id):
    row = database.execute(
        "SELECT visited FROM statements WHERE id=?", (statement_id,)).fetchone()
    return bool(row and row[0])


def read_entry_points(analysis):
    path = os.path.join(analysis, ENTRY_POINTS)
    if not os.path.isfile(path):
        raise SystemExit("No entry point list: " + path)
    ids = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and line.isdigit():
                ids.append(int(line))
    return ids


# --------------------------------------------------------------------------

def next_statement(analysis_path):
    analysis, database = open_analysis(analysis_path)
    try:
        build_line_index(analysis, database)

        planned = get_state(database, "next")
        if planned:
            statement_id = int(planned)
            if not is_visited(database, statement_id):
                show(read_statement(analysis, database, statement_id), "path")
                return 0
            set_state(database, "next", "")
            database.commit()

        row = database.execute("SELECT MIN(id) FROM pending_queue").fetchone()
        if row and row[0] is not None:
            show(read_statement(analysis, database, row[0]), "pending queue")
            return 0

        for statement_id in read_entry_points(analysis):
            if not is_visited(database, statement_id):
                show(read_statement(analysis, database, statement_id), "entry point")
                return 0

        print(json.dumps({"end": "TRAVERSAL STOPS"}, ensure_ascii=False))
        return 0
    finally:
        database.close()


def show(statement, came_from):
    if statement is None:
        print(json.dumps({"error": "this id is not in the statement list"},
                         ensure_ascii=False))
        return
    statement = dict(statement)
    statement["came_from"] = came_from
    print(json.dumps(statement, ensure_ascii=False))


# --------------------------------------------------------------------------

def split_ids(text):
    if not text:
        return []
    ids = []
    for piece in text.replace(";", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if not piece.lstrip("-").isdigit():
            raise SystemExit("Not an id: " + piece)
        ids.append(int(piece))
    return sorted(set(ids))


def record(analysis_path, statement_id, inputs_text, outputs_text, unresolved):
    analysis, database = open_analysis(analysis_path)
    try:
        build_line_index(analysis, database)

        if database.execute("SELECT 1 FROM statements WHERE id=?",
                            (statement_id,)).fetchone() is None:
            raise SystemExit("No such statement in the database: " + str(statement_id))
        if is_visited(database, statement_id):
            raise SystemExit(
                "Statement " + str(statement_id)
                + " has already been visited. It is never recorded twice."
            )

        inputs = split_ids(inputs_text)
        outputs = split_ids(outputs_text)

        for other in inputs + outputs:
            if database.execute("SELECT 1 FROM statements WHERE id=?",
                                (other,)).fetchone() is None:
                raise SystemExit(
                    "Id " + str(other) + " is not in the database. If the statement "
                    "points at something that is not in the program, it is unresolved."
                )

        is_source = 1 if (outputs and not inputs) else None
        is_sink = 1 if not outputs else None

        database.execute(
            "UPDATE statements SET inputs=?, outputs=?, visited=1, "
            "is_source=?, is_sink=?, unresolved=? WHERE id=?",
            (
                ",".join(str(x) for x in inputs),
                ",".join(str(x) for x in outputs),
                is_source,
                is_sink,
                1 if unresolved else None,
                statement_id,
            ),
        )
        database.execute("DELETE FROM pending_queue WHERE id=?", (statement_id,))

        planned = ""
        queued = []
        if not unresolved:
            unvisited = [o for o in outputs if not is_visited(database, o)]
            if unvisited:
                planned = str(unvisited[0])
                for other in unvisited[1:]:
                    database.execute(
                        "INSERT OR IGNORE INTO pending_queue (id) VALUES (?)", (other,)
                    )
                    queued.append(other)

        set_state(database, "next", planned)
        database.commit()

        print(json.dumps({
            "recorded": statement_id,
            "is_source": bool(is_source),
            "is_sink": bool(is_sink),
            "unresolved": bool(unresolved),
            "next": int(planned) if planned else None,
            "added_to_queue": queued,
            "path_ended": planned == "",
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()


# --------------------------------------------------------------------------

def report(analysis_path):
    analysis, database = open_analysis(analysis_path)
    try:
        count = lambda query: database.execute(query).fetchone()[0]
        entry_points = read_entry_points(analysis)
        unvisited_entry_points = [e for e in entry_points
                                  if not is_visited(database, e)]
        numbers = {
            "statements": count("SELECT COUNT(*) FROM statements"),
            "visited": count("SELECT COUNT(*) FROM statements WHERE visited=1"),
            "unvisited": count("SELECT COUNT(*) FROM statements WHERE visited IS NULL"),
            "sources": count("SELECT COUNT(*) FROM statements WHERE is_source=1"),
            "sinks": count("SELECT COUNT(*) FROM statements WHERE is_sink=1"),
            "unresolved": count("SELECT COUNT(*) FROM statements WHERE unresolved=1"),
            "pending_queue": count("SELECT COUNT(*) FROM pending_queue"),
            "entry_points": len(entry_points),
            "unvisited_entry_points": len(unvisited_entry_points),
        }
        for key in numbers:
            print(key + ": " + str(numbers[key]))
        return 0
    finally:
        database.close()


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="traverse.py",
                                     description="SPIDER - step 4")
    commands = parser.add_subparsers(dest="command", required=True)

    next_command = commands.add_parser("next")
    next_command.add_argument("--analysis", required=True)

    record_command = commands.add_parser("record")
    record_command.add_argument("--analysis", required=True)
    record_command.add_argument("--id", required=True, type=int)
    record_command.add_argument("--inputs", required=True)
    record_command.add_argument("--outputs", required=True)
    record_command.add_argument("--unresolved", action="store_true")

    report_command = commands.add_parser("report")
    report_command.add_argument("--analysis", required=True)

    arguments = parser.parse_args()
    if arguments.command == "next":
        return next_statement(arguments.analysis)
    if arguments.command == "record":
        return record(arguments.analysis, arguments.id, arguments.inputs,
                      arguments.outputs, arguments.unresolved)
    return report(arguments.analysis)


if __name__ == "__main__":
    sys.exit(main())
