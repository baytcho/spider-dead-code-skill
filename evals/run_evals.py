"""SPIDER evaluation runner.

Two modes.

    python evals/run_evals.py --self-test
        Runs the whole pipeline over evals/project with a scripted set of
        correct decisions and checks that the programs behave exactly as the
        skill describes: the marks, the traversal order, the refusals, the end
        of the work. This tests the machinery, not a model.

    python evals/run_evals.py --check <analysis directory>
        Compares the result an intelligence actually produced against
        expected.json. Use it after a real run of the skill over evals/project.
        This is the test that catches an invented classification: a run that
        declares every style rule an entry point fails here.

Exit code 0 means every check passed.
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(EVALS_DIR)
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
TEST_PROJECT = os.path.join(EVALS_DIR, "project")
EXPECTED = os.path.join(EVALS_DIR, "expected.json")

SOURCE_FILES = [
    "app/layout.tsx",
    "app/page.module.css",
    "app/page.tsx",
    "app/ui/Navbar.tsx",
    "app/unused.module.css",
    "lib/helpers.ts",
]

failures = []
passes = 0


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print("  ok    " + name)
    else:
        failures.append(name + (("  -> " + detail) if detail else ""))
        print("  FAIL  " + name + (("  -> " + detail) if detail else ""))


def run(script, *arguments):
    command = [sys.executable, os.path.join(SCRIPTS, script)] + list(arguments)
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8")
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def run_json(script, *arguments):
    code, out, err = run(script, *arguments)
    if code != 0:
        raise SystemExit(script + " failed: " + (err or out))
    return json.loads(out)


def load_expected():
    with open(EXPECTED, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ids_in_file(path):
    if not os.path.isfile(path):
        return []
    ids = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line.isdigit():
                ids.append(int(line))
    return ids


def database_of(analysis):
    return sqlite3.connect(os.path.join(analysis, "analysis.db"))


# --------------------------------------------------------------------------
# Mode 1: self test of the machinery
# --------------------------------------------------------------------------

def self_test():
    expected = load_expected()
    analysis = tempfile.mkdtemp(prefix="spider-eval-")
    print("Analysis directory: " + analysis)
    try:
        with open(os.path.join(analysis, "source-files.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            for name in SOURCE_FILES:
                fh.write(name + "\n")

        print("\nStep 1 - statement list")
        code, out, err = run("statements.py", "copy",
                             "--project", TEST_PROJECT, "--analysis", analysis)
        check("copy succeeds", code == 0, err)
        check("copy reports no missing file", "Missing files:  0" in out, out)

        code, out, err = run("statements.py", "split",
                             "--analysis", analysis, "--project", TEST_PROJECT)
        check("split succeeds", code == 0, err)
        statements_path = os.path.join(analysis, "statements.txt")
        lines = [l for l in open(statements_path, encoding="utf-8").read().split("\n") if l]
        check("statement count", len(lines) == expected["statement_count"],
              "got " + str(len(lines)))

        report = json.load(open(os.path.join(analysis, "split-report.json"),
                                encoding="utf-8"))
        check("no file was left unsplit", report["files_not_split"] == [],
              str(report["files_not_split"]))
        check("statements by extension",
              report["statements_by_extension"] == expected["statements_by_extension"],
              str(report["statements_by_extension"]))

        print("\nStep 2 - entry points")
        with open(os.path.join(analysis, "entry-points.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            for entry in expected["entry_points"]:
                fh.write(str(entry) + "\n")
        with open(os.path.join(analysis, "read-progress.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(str(expected["statement_count"]) + "\n")

        print("\nStep 3 - database")
        code, out, err = run("database.py", "init", "--analysis", analysis)
        check("database is created", code == 0, err)
        check("no field is filled besides the id",
              "Fields filled besides the id:  0" in out, out)
        code, out, err = run("database.py", "init", "--analysis", analysis)
        check("an existing database is never overwritten", code != 0, out)

        print("\nStep 4 - traversal")
        # The decisions below are the correct ones for this project. Each one
        # follows a definition in SKILL.md; none of them invents a rule.
        decisions = {
            3: ("", "1", False),
            1: ("3", "", False),
            4: ("", "2", False),
            2: ("4", "15", False),
            15: ("2", "", False),
            9: ("", "", False),
            12: ("", "10,11", True),
        }
        order = []
        while True:
            answer = run_json("traverse.py", "next", "--analysis", analysis)
            if "end" in answer:
                break
            statement_id = answer["id"]
            order.append(statement_id)
            if statement_id not in decisions:
                check("the traversal asked only about known statements", False,
                      "unexpected id " + str(statement_id))
                break
            inputs, outputs, unresolved = decisions[statement_id]
            arguments = ["record", "--analysis", analysis, "--id", str(statement_id),
                         "--inputs", inputs, "--outputs", outputs]
            if unresolved:
                arguments.append("--unresolved")
            written = run_json("traverse.py", *arguments)
            if statement_id == 3:
                check("a statement with outputs and no inputs is a source",
                      written["is_source"] is True, str(written))
            if statement_id == 1:
                check("a statement with no outputs is a sink",
                      written["is_sink"] is True, str(written))
            if statement_id == 9:
                check("the directive is a sink", written["is_sink"] is True,
                      str(written))
            if statement_id == 12:
                check("the runtime-assembled name is marked unresolved",
                      written["unresolved"] is True, str(written))
                check("an unresolved statement ends the path",
                      written["path_ended"] is True, str(written))

        check("the traversal visited exactly the expected statements",
              sorted(order) == sorted(decisions.keys()), str(order))

        code, out, err = run("traverse.py", "record", "--analysis", analysis,
                             "--id", "3", "--inputs", "", "--outputs", "")
        check("a visited statement is never recorded twice", code != 0, out)

        code, out, err = run("traverse.py", "record", "--analysis", analysis,
                             "--id", "999", "--inputs", "", "--outputs", "")
        check("an id that is not in the database is refused", code != 0, out)

        print("\nStep 5 - review")
        code, out, err = run("review.py", "resolve", "--analysis", analysis,
                             "--id", "12", "--inputs", "", "--outputs", "5,6,7,10,11")
        check("a decision without a review entry is refused", code != 0, out)

        with open(os.path.join(analysis, "review.md"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("## Statement 12\n\n"
                     "It carries a name assembled at runtime. The values the name "
                     "can take are written in the same file: done and pending.\n")

        answer = run_json("review.py", "next", "--analysis", analysis)
        check("the review hands over the unresolved statement",
              answer.get("id") == 12, str(answer))

        answer = run_json("review.py", "resolve", "--analysis", analysis,
                          "--id", "12", "--inputs", "", "--outputs", "5,6,7,10,11")
        check("resolving queues the unvisited links",
              sorted(answer["added_to_queue"]) == [5, 6, 7, 10, 11],
              str(answer))

        answer = run_json("review.py", "finish", "--analysis", analysis)
        check("the work is not done while the queue is full",
              answer["work_is_done"] is False, str(answer))

        print("\nStep 4 again - the new pending queue")
        second_round = {
            5: ("12", "", False),
            6: ("12", "", False),
            7: ("12", "", False),
            10: ("12", "", False),
            11: ("12", "16", False),
            16: ("11", "", False),
        }
        while True:
            answer = run_json("traverse.py", "next", "--analysis", analysis)
            if "end" in answer:
                break
            statement_id = answer["id"]
            if statement_id not in second_round:
                check("the second round asked only about known statements", False,
                      "unexpected id " + str(statement_id))
                break
            inputs, outputs, unresolved = second_round[statement_id]
            run_json("traverse.py", "record", "--analysis", analysis,
                     "--id", str(statement_id), "--inputs", inputs,
                     "--outputs", outputs)

        answer = run_json("review.py", "finish", "--analysis", analysis)
        check("the work is done when there is nowhere left to go",
              answer["work_is_done"] is True, str(answer))
        check("no statement is left unresolved",
              answer["statements_still_unresolved"] == 0, str(answer))

        print("\nThe result")
        check_result(analysis, expected)

        print("\nThe refusals of the review")
        refusal_test(analysis)

    finally:
        shutil.rmtree(analysis, ignore_errors=True)


def refusal_test(analysis):
    """An entry point cannot be declared 'does not work in the program'."""
    database = database_of(analysis)
    try:
        database.execute("UPDATE statements SET unresolved=1 WHERE id=9")
        database.commit()
    finally:
        database.close()
    with open(os.path.join(analysis, "review.md"), "a",
              encoding="utf-8", newline="\n") as fh:
        fh.write("\n## Statement 9\n\ntest entry\n")
    code, out, err = run("review.py", "reopen", "--analysis", analysis,
                         "--id", "9", "--place", "none")
    check("an entry point cannot be declared not working", code != 0, out)


# --------------------------------------------------------------------------
# Mode 2: check a real run
# --------------------------------------------------------------------------

def check_result(analysis, expected=None):
    expected = expected or load_expected()

    entry_points = sorted(set(ids_in_file(os.path.join(analysis, "entry-points.txt"))))
    check("the entry point list is exactly the expected one",
          entry_points == sorted(expected["entry_points"]),
          "got " + str(entry_points))

    database = database_of(analysis)
    try:
        visited = set(row[0] for row in database.execute(
            "SELECT id FROM statements WHERE visited=1"))
        unvisited = set(row[0] for row in database.execute(
            "SELECT id FROM statements WHERE visited IS NULL"))
        unresolved = database.execute(
            "SELECT COUNT(*) FROM statements WHERE unresolved=1").fetchone()[0]
    finally:
        database.close()

    check("the statements that must stay unvisited did",
          set(expected["unvisited_at_the_end"]) <= unvisited,
          "missing " + str(sorted(set(expected["unvisited_at_the_end"]) - unvisited)))
    check("nothing else was left unvisited",
          unvisited <= set(expected["unvisited_at_the_end"]),
          "extra " + str(sorted(unvisited - set(expected["unvisited_at_the_end"]))))
    check("the statements that must be visited were",
          set(expected["must_be_visited_at_the_end"]) <= visited,
          "missing " + str(sorted(set(expected["must_be_visited_at_the_end"]) - visited)))
    check("no statement is left unresolved",
          unresolved == expected["unresolved_at_the_end"], "got " + str(unresolved))


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="run_evals.py")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", default=None)
    arguments = parser.parse_args()

    if arguments.check:
        print("Checking a real run against expected.json")
        check_result(os.path.abspath(arguments.check))
    elif getattr(arguments, "self_test"):
        self_test()
    else:
        parser.print_help()
        return 1

    print()
    print("passed: " + str(passes) + "   failed: " + str(len(failures)))
    for failure in failures:
        print("   " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
