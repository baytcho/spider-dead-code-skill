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

Every line below carries a comment. Nothing here can halt the analysis. The
refusals guard the record, not the work: a decision without a written review
entry, a second decision on a statement already resolved, an id that is not in
the database, closing the step while an unresolved statement is still waiting,
and the one contradiction - calling a listed entry point "does not work in the
program", which would make the rounds circle for ever.
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
ENTRY_POINTS = "entry-points.txt"                 # made by step 2, added to here
DATABASE = "analysis.db"                          # made by step 3
REVIEW = "review.md"                              # written by the intelligence, read here
SUSPECTED_ERRORS = "suspected-errors.txt"         # the result of this step

WORKING_TABLES = """
CREATE TABLE IF NOT EXISTS review_state (
    id    INTEGER PRIMARY KEY,                    -- the statement
    state TEXT                                    -- resolved, reopened or unvisited
);

CREATE TABLE IF NOT EXISTS line_index (
    id     INTEGER PRIMARY KEY,                   -- built by step 4
    offset INTEGER                                -- created here too, in case step 4 never ran
);
"""


def open_analysis(analysis):
    """Opens the database and makes sure the working tables exist."""
    analysis = os.path.abspath(analysis)                   # full path only
    database_path = os.path.join(analysis, DATABASE)       # where the database is
    if not os.path.isfile(database_path):                  # step 3 has to be done first
        raise SystemExit("No database: " + database_path)
    database = sqlite3.connect(database_path)              # open it
    database.executescript(WORKING_TABLES)                 # create the working tables if new
    database.commit()                                      # and keep them
    return analysis, database                              # both are needed everywhere


def read_statement(analysis, database, statement_id):
    """Reads one statement line by its id, through the index step 4 built."""
    row = database.execute(
        "SELECT offset FROM line_index WHERE id=?", (statement_id,)).fetchone()
    if row is None:                                        # no index entry for this id
        return {"id": statement_id}                        # the id alone is still useful
    with open(os.path.join(analysis, STATEMENTS), "rb") as fh:  # bytes, so the offset is exact
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


def unresolved_ids(database):
    """Every statement still carrying the unresolved mark, smallest id first."""
    return [row[0] for row in database.execute(
        "SELECT id FROM statements WHERE unresolved=1 ORDER BY id")]


def state_of(database, statement_id):
    """What this step has already decided about the statement, if anything."""
    row = database.execute(
        "SELECT state FROM review_state WHERE id=?", (statement_id,)).fetchone()
    return row[0] if row else None                         # nothing yet is fine


def already_resolved(database, statement_id):
    """A resolved statement is never touched again. A reopened one is reviewed anew."""
    return state_of(database, statement_id) == "resolved"


def has_review_entry(analysis, statement_id):
    """True when the review file holds an entry for this statement."""
    path = os.path.join(analysis, REVIEW)                  # the review file
    if not os.path.isfile(path):                           # nothing written yet
        return False
    heading = "## Statement " + str(statement_id)          # the line that opens an entry
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()                        # spaces do not matter
            if stripped == heading or stripped.startswith(heading + " "):  # exact, or with a title
                return True
    return False                                           # no entry for this id


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


def read_entry_points(analysis):
    """Reads the entry point list. A missing file is treated as an empty list."""
    path = os.path.join(analysis, ENTRY_POINTS)            # where it is
    if not os.path.isfile(path):                           # this step can run without it
        return []
    ids = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:  # a damaged byte stops nothing
        for line in fh:
            line = line.strip()                            # drop the newline
            if line.isdigit():                             # only ids count
                ids.append(int(line))
    return ids


def is_entry_point(analysis, statement_id):
    """True when this id already stands in the entry point list."""
    return statement_id in set(read_entry_points(analysis))


def append_entry_point(analysis, statement_id):
    """Appends the id at the end of the entry point list.

    The file may not end with a newline. Then the last old id and the new one
    would merge into a single number that does not exist. That is why the
    ending is checked and a newline is added when needed.
    """
    path = os.path.join(analysis, ENTRY_POINTS)            # where it is
    if not os.path.isfile(path):                           # nowhere to append to
        raise SystemExit("No entry point list: " + path)

    with open(path, "rb") as fh:                           # bytes, to see the last one
        content = fh.read()

    present = set()                                        # what is already there
    for line in content.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.isdigit():
            present.add(int(line))
    if statement_id in present:                            # already an entry point
        return False                                       # nothing to do

    with open(path, "ab") as fh:                           # append, never rewrite
        if content and not content.endswith(b"\n"):        # the trap: no closing newline
            fh.write(b"\n")                                # so the ids never merge
        fh.write((str(statement_id) + "\n").encode("utf-8"))  # the new id on its own line
    return True                                            # it was added


# --------------------------------------------------------------------------

def list_unresolved(analysis_path):
    """Shows every unresolved statement and what this step has decided so far."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        rows = []                                          # one entry per statement
        for statement_id in unresolved_ids(database):      # smallest id first
            data = read_statement(analysis, database, statement_id)  # address and text
            data["state"] = state_of(database, statement_id) or "waiting"  # and its state
            rows.append(data)
        print(json.dumps(rows, ensure_ascii=False, indent=1))  # readable, any alphabet
        return 0
    finally:
        database.close()                                   # closed even if something threw


def next_unresolved(analysis_path):
    """Names the next unresolved statement that has not been decided yet."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        for statement_id in unresolved_ids(database):      # smallest id first
            if not already_resolved(database, statement_id):   # not finished with
                print(json.dumps(read_statement(analysis, database, statement_id),
                                 ensure_ascii=False))      # hand it over
                return 0
        print(json.dumps({"end": "EVERY UNRESOLVED STATEMENT HAS BEEN REVIEWED"},
                         ensure_ascii=False))              # nothing left in this pass
        return 0
    finally:
        database.close()                                   # closed even if something threw


def guard(analysis, database, statement_id):
    """The three checks every decision has to pass."""
    if statement_id not in unresolved_ids(database):       # only unresolved ones are decided here
        raise SystemExit("Statement " + str(statement_id) + " is not marked unresolved.")
    if already_resolved(database, statement_id):           # a resolved one is never touched again
        raise SystemExit("Statement " + str(statement_id) + " has already been resolved.")
    if not has_review_entry(analysis, statement_id):       # the evidence comes before the decision
        raise SystemExit(
            "The review file has no entry '## Statement " + str(statement_id) + "'.\n"
            "The entry is written before the decision."
        )


def resolve(analysis_path, statement_id, inputs_text, outputs_text):
    """The statement is understood: its links are recorded and the mark falls."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        guard(analysis, database, statement_id)            # the three checks

        inputs = split_ids(inputs_text)                    # who sends information in
        outputs = split_ids(outputs_text)                  # who it sends information to
        for other in inputs + outputs:                     # every id named must exist
            if database.execute("SELECT 1 FROM statements WHERE id=?",
                                (other,)).fetchone() is None:
                raise SystemExit("Id " + str(other) + " is not in the database.")

        database.execute(                                  # the record is completed
            "UPDATE statements SET inputs=?, outputs=?, unresolved=NULL, "
            "is_source=?, is_sink=? WHERE id=?",
            (
                ",".join(str(x) for x in inputs),          # stored as text
                ",".join(str(x) for x in outputs),         # so it can be read by eye
                1 if (outputs and not inputs) else None,   # the source mark, set anew
                1 if not outputs else None,                # the sink mark, set anew
                statement_id,
            ),
        )

        queued = []                                        # what this decision opens up
        for other in sorted(set(inputs + outputs)):        # every id the links name
            row = database.execute(
                "SELECT visited FROM statements WHERE id=?", (other,)).fetchone()
            if row and row[0]:                             # already visited
                continue                                   # nothing to do
            database.execute(                              # not visited yet
                "INSERT OR IGNORE INTO pending_queue (id) VALUES (?)", (other,))
            queued.append(other)                           # so it waits its turn

        database.execute(                                  # this statement is finished with
            "INSERT OR REPLACE INTO review_state (id, state) VALUES (?, 'resolved')",
            (statement_id,),
        )
        database.commit()                                  # everything written together
        print(json.dumps({
            "id": statement_id,                            # which statement
            "state": "resolved",                           # what became of it
            "added_to_queue": queued,                      # and what it opened up
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()                                   # closed even if something threw


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
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        guard(analysis, database, statement_id)            # the three checks

        if place == "none" and is_entry_point(analysis, statement_id):  # the one contradiction
            raise SystemExit(
                "Statement " + str(statement_id) + " is in the entry point list.\n"
                "Being an entry point means something outside reaches it, which "
                "contradicts 'does not work in the program'.\n"
                "The traversal would hand it back as an entry point and the round "
                "would never end. Decide which of the two is true."
            )

        database.execute(                                  # only the two marks fall
            "UPDATE statements SET visited=NULL, unresolved=NULL WHERE id=?",
            (statement_id,),                               # the links are left alone
        )

        if place == "entry":                               # it is an entry point
            appended = append_entry_point(analysis, statement_id)   # into the list
            placed = ("added to the entry point list" if appended
                      else "already in the entry point list")
            state = "reopened"                             # the traversal will reach it
        elif place == "queue":                             # it works, but is not an entry point
            database.execute(
                "INSERT OR IGNORE INTO pending_queue (id) VALUES (?)", (statement_id,))
            placed = "added to the pending queue"
            state = "reopened"                             # the traversal will reach it
        else:                                              # it does not work in the program
            placed = "nowhere - it does not work in the program; second kind"
            state = "unvisited"                            # and stays there

        database.execute(                                  # remembered for this pass
            "INSERT OR REPLACE INTO review_state (id, state) VALUES (?, ?)",
            (statement_id, state),
        )
        database.commit()                                  # everything written together
        print(json.dumps({
            "id": statement_id,                            # which statement
            "state": state,                                # what became of it
            "placed": placed,                              # and where it went
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()                                   # closed even if something threw


def finish(analysis_path):
    """Closes the pass: writes the suspected errors and says whether the work is done."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        waiting = [i for i in unresolved_ids(database)     # anything still undecided
                   if not already_resolved(database, i)]
        if waiting:                                        # the pass is not over
            raise SystemExit(
                "Still not reviewed: " + str(len(waiting)) + " unresolved statements: "
                + ", ".join(str(x) for x in waiting[:20])  # the first twenty are named
            )

        reopened = [row[0] for row in database.execute(    # sent back for another round
            "SELECT id FROM review_state WHERE state='reopened' ORDER BY id")]
        left_unvisited = [row[0] for row in database.execute(  # settled into the second kind
            "SELECT id FROM review_state WHERE state='unvisited' ORDER BY id")]
        resolved = [row[0] for row in database.execute(    # understood and recorded
            "SELECT id FROM review_state WHERE state='resolved' ORDER BY id")]
        queued = [row[0] for row in database.execute(      # waiting for the traversal
            "SELECT id FROM pending_queue ORDER BY id")]

        # Only the reopened statements go into the file. They are the places
        # where the previous traversal read the code wrongly. A statement found
        # not to work in the program is not an error: it belongs to the second
        # kind and the work on it is done.
        path = os.path.join(analysis, SUSPECTED_ERRORS)    # where the file goes
        with open(path, "w", encoding="utf-8", newline="\n") as fh:  # rewritten every pass
            for statement_id in reopened:
                data = read_statement(analysis, database, statement_id)  # address and text
                fh.write(
                    str(statement_id) + " | " + data.get("file", "") + " | "
                    + data.get("lines", "") + " | " + data.get("text", "") + "\n"
                )

        database.execute(                                  # the pass is closed
            "DELETE FROM review_state WHERE state IN ('reopened', 'unvisited')")
        database.commit()                                  # so those may be reviewed again later

        still_unresolved = database.execute(               # counted from the database
            "SELECT COUNT(*) FROM statements WHERE unresolved=1").fetchone()[0]
        unvisited_entry_points = [                         # and from the entry point list
            e for e in read_entry_points(analysis)
            if not database.execute(
                "SELECT visited FROM statements WHERE id=?", (e,)).fetchone()[0]
        ]

        # The work is done only when there is nowhere left to go: no unresolved
        # statement, nothing reopened, nothing in the pending queue and no
        # unvisited entry point. If one of those remains, the traversal still
        # has work and the step is not the end.
        done = (
            still_unresolved == 0                          # nothing left unresolved
            and not reopened                               # nothing sent back this pass
            and not queued                                 # nothing waiting
            and not unvisited_entry_points                 # and every entry point visited
        )

        print(json.dumps({
            "resolved": len(resolved),                     # understood in this pass
            "reopened": len(reopened),                     # sent back for another round
            "left_unvisited_this_pass": len(left_unvisited),   # settled into the second kind
            "statements_still_unresolved": still_unresolved,   # must reach zero
            "pending_queue": len(queued),                  # must reach zero
            "unvisited_entry_points": len(unvisited_entry_points),  # must reach zero
            "work_is_done": done,                          # all four at zero
            "file": path,                                  # where the suspected errors are
        }, ensure_ascii=False))
        return 0
    finally:
        database.close()                                   # closed even if something threw


def report(analysis_path):
    """Every number here is counted from the database, never from memory."""
    analysis, database = open_analysis(analysis_path)      # open everything
    try:
        count = lambda query: database.execute(query).fetchone()[0]   # one number per query
        numbers = {
            "statements": count("SELECT COUNT(*) FROM statements"),   # all of them
            "first_kind_visited_and_working": count(                  # needed by the program
                "SELECT COUNT(*) FROM statements WHERE visited=1"),
            "second_kind_unvisited": count(                           # not needed
                "SELECT COUNT(*) FROM statements WHERE visited IS NULL"),
            "statements_still_unresolved": count(                     # must reach zero
                "SELECT COUNT(*) FROM statements WHERE unresolved=1"),
            "resolved": count(                                        # understood in this pass
                "SELECT COUNT(*) FROM review_state WHERE state='resolved'"),
            "reopened_this_pass": count(                              # sent back this pass
                "SELECT COUNT(*) FROM review_state WHERE state='reopened'"),
            "pending_queue": count("SELECT COUNT(*) FROM pending_queue"),  # still waiting
        }
        for key in numbers:                                # printed in that order
            print(key + ": " + str(numbers[key]))
        return 0
    finally:
        database.close()                                   # closed even if something threw


# --------------------------------------------------------------------------

def main():
    """Six commands: list, next, resolve, reopen, finish, report."""
    parser = argparse.ArgumentParser(prog="review.py", description="SPIDER - step 5")
    commands = parser.add_subparsers(dest="command", required=True)  # a command is required

    for name in ("list", "next", "finish", "report"):      # these four take only the directory
        command = commands.add_parser(name)
        command.add_argument("--analysis", required=True)

    resolve_command = commands.add_parser("resolve")           # the statement is understood
    resolve_command.add_argument("--analysis", required=True)  # the analysis directory
    resolve_command.add_argument("--id", required=True, type=int)   # which statement
    resolve_command.add_argument("--inputs", required=True)    # who sends information in
    resolve_command.add_argument("--outputs", required=True)   # who it sends information to

    reopen_command = commands.add_parser("reopen")             # the case is settled another way
    reopen_command.add_argument("--analysis", required=True)   # the analysis directory
    reopen_command.add_argument("--id", required=True, type=int)    # which statement
    reopen_command.add_argument("--place", required=True,      # and where it goes
                                choices=["entry", "queue", "none"])

    arguments = parser.parse_args()                            # read them
    if arguments.command == "list":                            # and do the work
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


if __name__ == "__main__":                                     # when run directly
    sys.exit(main())                                           # the exit code is the result
