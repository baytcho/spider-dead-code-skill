"""SPIDER - step 5: review of the unresolved statements.

The program decides nothing about the statements. It only:
  - lists the unresolved ones and names the order;
  - records in the database what the intelligence has proved;
  - reopens a statement whose case is not settled yet;
  - keeps the new pending queue;
  - writes the file of suspected errors at the end.

The result has two kinds of statements. There is no third:
  - visited and working in the program - needed;
  - unvisited - not needed.

"Pending" is not a result but a state during the work. A statement that is
found to work in the program, while its links cannot be recorded, is reopened:
it becomes unvisited and is placed where it belongs - among the entry points or
in the pending queue. After that the traversal runs again.

    review.py list    --analysis <dir>
    review.py next    --analysis <dir>
    review.py resolve --analysis <dir> --id N --inputs "1,2" --outputs "5"
    review.py reopen  --analysis <dir> --id N --place entry|queue|none
    review.py finish  --analysis <dir>
    review.py report  --analysis <dir>
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
REVIEW = "review.md"
SUSPECTED_ERRORS = "suspected-errors.txt"

WORKING_TABLES = """
CREATE TABLE IF NOT EXISTS review_state (
    id    INTEGER PRIMARY KEY,
    state TEXT
);

CREATE TABLE IF NOT EXISTS line_index (
    id     INTEGER PRIMARY KEY,
    offset INTEGER
);
"""


def open_analysis(analysis):
    analysis = os.path.abspath(analysis)
    database_path = os.path.join(analysis, DATABASE)
    if not os.path.isfile(database_path):
        raise SystemExit("No database: " + database_path)
    database = sqlite3.connect(database_path)
    database.executescript(WORKING_TABLES)
    database.commit()
    return analysis, database


def read_statement(analysis, database, statement_id):
    row = database.execute(
        "SELECT offset FROM line_index WHERE id=?", (statement_id,)).fetchone()
    if row is None:
        return {"id": statement_id}
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


def unresolved_ids(database):
    return [row[0] for row in database.execute(
        "SELECT id FROM statements WHERE unresolved=1 ORDER BY id")]


def state_of(database, statement_id):
    row = database.execute(
        "SELECT state FROM review_state WHERE id=?", (statement_id,)).fetchone()
    return row[0] if row else None


def already_resolved(database, statement_id):
    """A resolved statement is never touched again. A reopened one is reviewed anew."""
    return state_of(database, statement_id) == "resolved"


def has_review_entry(analysis, statement_id):
    path = os.path.join(analysis, REVIEW)
    if not os.path.isfile(path):
        return False
    heading = "## Statement " + str(statement_id)
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped == heading or stripped.startswith(heading + " "):
                return True
    return False


def split_ids(text):
    if not text:
        return []
    ids = []
    for piece in text.replace(";", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if not piece.isdigit():
            raise SystemExit("Not an id: " + piece)
        ids.append(int(piece))
    return sorted(set(ids))


def read_entry_points(analysis):
    path = os.path.join(analysis, ENTRY_POINTS)
    if not os.path.isfile(path):
        return []
    ids = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line.isdigit():
                ids.append(int(line))
    return ids


def is_entry_point(analysis, statement_id):
    return statement_id in set(read_entry_points(analysis))


def append_entry_point(analysis, statement_id):
    """Appends the id at the end of the entry point list.

    The file may not end with a newline. Then the last old id and the new one
    would merge into a single number that does not exist. That is why the
    ending is checked and a newline is added when needed.
    """
    path = os.path.join(analysis, ENTRY_POINTS)
    if not os.path.isfile(path):
        raise SystemExit("No entry point list: " + path)

    with open(path, "rb") as fh:
        content = fh.read()

    present = set()
    for line in content.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.isdigit():
            present.add(int(line))
    if statement_id in present:
        return False

    with open(path, "ab") as fh:
        if content and not content.endswith(b"\n"):
            fh.write(b"\n")
        fh.write((str(statement_id) + "\n").encode("utf-8"))
    return True


# --------------------------------------------------------------------------

def list_unresolved(analysis_path):
    analysis, database = open_analysis(analysis_path)
    try:
        rows = []
        for statement_id in unresolved_ids(database):
            data = read_statement(analysis, database, statement_id)
            data["state"] = state_of(database, statement_id) or "waiting"
            rows.append(data)
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    finally:
        database.close()


def next_unresolved(analysis_path):
    analysis, database = open_analysis(analysis_path)
    try:
        for statement_id in unresolved_ids(database):
            if not already_resolved(database, statement_id):
                print(json.dumps(read_statement(analysis, database, statement_id),
                                 ensure_ascii=False))
                return 0
        print(json.dumps({"end": "EVERY UNRESOLVED STATEMENT HAS BEEN REVIEWED"},
                         ensure_ascii=False))
        return 0
    finally:
        database.close()


def guard(analysis, database, statement_id):
    if statement_id not in unresolved_ids(database):
        raise SystemExit("Statement " + str(statement_id) + " is not marked unresolved.")
    if already_resolved(database, statement_id):
        raise SystemExit("Statement " + str(statement_id) + " has already been resolved.")
    if not has_review_entry(analysis, statement_id):
        raise SystemExit(
            "The review file has no entry '## Statement " + str(statement_id) + "'.\n"
            "The entry is written before the decision."
        )


def resolve(analysis_path, statement_id, inputs_text, outputs_text):
    analysis, database = open_analysis(analysis_path)
    try:
        guard(analysis, database, statement_id)

        inputs = split_ids(inputs_text)
        outputs = split_ids(outputs_text)
        for other in inputs + outputs:
            if database.execute("SELECT 1 FROM statements WHERE id=?",
                                (other,)).fetchone() is None:
                raise SystemExit("Id " + str(other) + " is not in the database.")

        database.execute(
            "UPDATE statements SET inputs=?, outputs=?, unresolved=NULL, "
            "is_source=?, is_sink=? WHERE id=?",
            (
                ",".join(str(x) for x in inputs),
                ",".join(str(x) for x in outputs),
                1 if (outputs and not inputs) else None,
                1 if not outputs else None,
                statement_id,
            ),
        )

        queued = []
        for other in sorted(set(inputs + outputs)):
            row = database.execute(
                "SELECT visited FROM statements WHERE id=?", (other,)).fetchone()
            if row and row[0]:
                continue
            database.execute(
                "INSERT OR IGNORE INTO pending_queue (id) VALUES (?)", (other,))
            queued.append(other)

        database.execute(
            "INSERT OR REPLACE INTO review_state (id, state) VALUES (?, 'resolved')",
            (statement_id,),
        )
        database.commit()
        print(json.dumps({
            "id": statement_id,
            "state": "resolved",
            "added_to_queue": queued,
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()


def reopen(analysis_path, statement_id, place):
    """Settles the case of an unresolved statement.

    Only two marks fall: "unresolved" and "visited". The statement becomes
    unvisited. Its record is left untouched - the links and the other marks stay
    as the traversal left them.

    Then:
      entry - it works in the program and is an entry point; the id is appended
              to the entry point list;
      queue - it works in the program but is not an entry point; the id goes
              into the pending queue;
      none  - it does not work in the program; it stays unvisited and stays
              there. Nothing is put back. It belongs to the second kind.
    """
    analysis, database = open_analysis(analysis_path)
    try:
        guard(analysis, database, statement_id)

        if place == "none" and is_entry_point(analysis, statement_id):
            raise SystemExit(
                "Statement " + str(statement_id) + " is in the entry point list.\n"
                "Being an entry point means something outside reaches it, which "
                "contradicts 'does not work in the program'.\n"
                "The traversal would hand it back as an entry point and the round "
                "would never end. Decide which of the two is true."
            )

        database.execute(
            "UPDATE statements SET visited=NULL, unresolved=NULL WHERE id=?",
            (statement_id,),
        )

        if place == "entry":
            appended = append_entry_point(analysis, statement_id)
            placed = ("added to the entry point list" if appended
                      else "already in the entry point list")
            state = "reopened"
        elif place == "queue":
            database.execute(
                "INSERT OR IGNORE INTO pending_queue (id) VALUES (?)", (statement_id,))
            placed = "added to the pending queue"
            state = "reopened"
        else:
            placed = "nowhere - it does not work in the program; second kind"
            state = "unvisited"

        database.execute(
            "INSERT OR REPLACE INTO review_state (id, state) VALUES (?, ?)",
            (statement_id, state),
        )
        database.commit()
        print(json.dumps({
            "id": statement_id,
            "state": state,
            "placed": placed,
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()


def finish(analysis_path):
    analysis, database = open_analysis(analysis_path)
    try:
        waiting = [i for i in unresolved_ids(database)
                   if not already_resolved(database, i)]
        if waiting:
            raise SystemExit(
                "Still not reviewed: " + str(len(waiting)) + " unresolved statements: "
                + ", ".join(str(x) for x in waiting[:20])
            )

        reopened = [row[0] for row in database.execute(
            "SELECT id FROM review_state WHERE state='reopened' ORDER BY id")]
        left_unvisited = [row[0] for row in database.execute(
            "SELECT id FROM review_state WHERE state='unvisited' ORDER BY id")]
        resolved = [row[0] for row in database.execute(
            "SELECT id FROM review_state WHERE state='resolved' ORDER BY id")]
        queued = [row[0] for row in database.execute(
            "SELECT id FROM pending_queue ORDER BY id")]

        # Only the reopened statements go into the file. They are the places
        # where the previous traversal read the code wrongly. A statement found
        # not to work in the program is not an error: it belongs to the second
        # kind and the work on it is done.
        path = os.path.join(analysis, SUSPECTED_ERRORS)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for statement_id in reopened:
                data = read_statement(analysis, database, statement_id)
                fh.write(
                    str(statement_id) + " | " + data.get("file", "") + " | "
                    + data.get("lines", "") + " | " + data.get("text", "") + "\n"
                )

        database.execute(
            "DELETE FROM review_state WHERE state IN ('reopened', 'unvisited')")
        database.commit()

        still_unresolved = database.execute(
            "SELECT COUNT(*) FROM statements WHERE unresolved=1").fetchone()[0]
        unvisited_entry_points = [
            e for e in read_entry_points(analysis)
            if not database.execute(
                "SELECT visited FROM statements WHERE id=?", (e,)).fetchone()[0]
        ]

        # The work is done only when there is nowhere left to go: no unresolved
        # statement, nothing reopened, nothing in the pending queue and no
        # unvisited entry point. If one of those remains, the traversal still
        # has work and the step is not the end.
        done = (
            still_unresolved == 0
            and not reopened
            and not queued
            and not unvisited_entry_points
        )

        print(json.dumps({
            "resolved": len(resolved),
            "reopened": len(reopened),
            "left_unvisited_this_pass": len(left_unvisited),
            "statements_still_unresolved": still_unresolved,
            "pending_queue": len(queued),
            "unvisited_entry_points": len(unvisited_entry_points),
            "work_is_done": done,
            "file": path,
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()


def report(analysis_path):
    analysis, database = open_analysis(analysis_path)
    try:
        count = lambda query: database.execute(query).fetchone()[0]
        numbers = {
            "statements": count("SELECT COUNT(*) FROM statements"),
            "first_kind_visited_and_working": count(
                "SELECT COUNT(*) FROM statements WHERE visited=1"),
            "second_kind_unvisited": count(
                "SELECT COUNT(*) FROM statements WHERE visited IS NULL"),
            "statements_still_unresolved": count(
                "SELECT COUNT(*) FROM statements WHERE unresolved=1"),
            "resolved": count(
                "SELECT COUNT(*) FROM review_state WHERE state='resolved'"),
            "reopened_this_pass": count(
                "SELECT COUNT(*) FROM review_state WHERE state='reopened'"),
            "pending_queue": count("SELECT COUNT(*) FROM pending_queue"),
        }
        for key in numbers:
            print(key + ": " + str(numbers[key]))
        return 0
    finally:
        database.close()


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="review.py", description="SPIDER - step 5")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("list", "next", "finish", "report"):
        command = commands.add_parser(name)
        command.add_argument("--analysis", required=True)

    resolve_command = commands.add_parser("resolve")
    resolve_command.add_argument("--analysis", required=True)
    resolve_command.add_argument("--id", required=True, type=int)
    resolve_command.add_argument("--inputs", required=True)
    resolve_command.add_argument("--outputs", required=True)

    reopen_command = commands.add_parser("reopen")
    reopen_command.add_argument("--analysis", required=True)
    reopen_command.add_argument("--id", required=True, type=int)
    reopen_command.add_argument("--place", required=True,
                                choices=["entry", "queue", "none"])

    arguments = parser.parse_args()
    if arguments.command == "list":
        return list_unresolved(arguments.analysis)
    if arguments.command == "next":
        return next_unresolved(arguments.analysis)
    if arguments.command == "resolve":
        return resolve(arguments.analysis, arguments.id, arguments.inputs,
                       arguments.outputs)
    if arguments.command == "reopen":
        return reopen(arguments.analysis, arguments.id, arguments.place)
    if arguments.command == "finish":
        return finish(arguments.analysis)
    return report(arguments.analysis)


if __name__ == "__main__":
    sys.exit(main())
