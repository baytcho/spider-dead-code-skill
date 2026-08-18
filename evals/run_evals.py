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
import re
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
        check("no field of the analysis is filled",
              "Analysis fields filled:        0" in out, out)
        check("every record carries its address",
              ("Records with an address:       "
               + str(expected["statement_count"])) in out, out)
        code, out, err = run("database.py", "init", "--analysis", analysis)
        check("an existing database is never overwritten", code != 0, out)

        print("\nStep 5 - traversal")
        # The contract of the round: record accepts only the id `next` handed.
        code, out, err = run("traverse.py", "record", "--analysis", analysis,
                             "--id", "3", "--inputs", "", "--outputs", "")
        check("record before any next is refused", code != 0, out)
        answer = run_json("traverse.py", "next", "--analysis", analysis)
        check("the first next hands the first entry point",
              answer.get("id") == 3, str(answer))
        code, out, err = run("traverse.py", "record", "--analysis", analysis,
                             "--id", "4", "--inputs", "", "--outputs", "")
        check("record of an id next did not hand is refused", code != 0, out)

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

        print("\nStep 6 - review")
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

        print("\nStep 5 again - the new pending queue")
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

        print("\nStep 7 - the final list")
        code, out, err = run("final_list.py", "build", "--analysis", analysis,
                             "--project", TEST_PROJECT)
        check("the final list is written when everything is closed",
              code == 0, err or out)
        check("the final list holds exactly the candidates",
              ("Candidates to check:       "
               + str(len(expected["unvisited_at_the_end"]))) in out, out)
        live_copy = tempfile.mkdtemp(prefix="spider-eval-live-")
        try:                                               # a live tree that drifted
            shutil.copytree(TEST_PROJECT, live_copy, dirs_exist_ok=True)
            drifted_file = os.path.join(live_copy, "app", "unused.module.css")
            with open(drifted_file, "a", encoding="utf-8", newline="\n") as fh:
                fh.write("\n/* drift */\n")                # a candidate's live file moves
            code, out, err = run("final_list.py", "build", "--analysis", analysis,
                                 "--project", live_copy)
            check("a drifted live file is named, not passed over",
                  code == 0 and "Live files that moved:     1" in out, err or out)
        finally:
            shutil.rmtree(live_copy, ignore_errors=True)

        print("\nStep 6 helper - the style search")
        code, out, err = run("style_links.py", "find", "--analysis", analysis)
        check("the style search runs over the open style statements",
              code == 0, err or out)
        orphan_id = None                                   # the unused rule of the project
        with open(os.path.join(analysis, "statements.txt"), encoding="utf-8") as fh:
            for line in fh:                                # find it by its own text
                if ".orphan" in line:
                    orphan_id = int(line.split(" | ", 1)[0])
        evidence = open(os.path.join(analysis, "style-candidates.tsv"),
                        encoding="utf-8").read()
        check("the unused rule comes back with no evidence, not with a verdict",
              orphan_id is not None
              and (str(orphan_id) + "\t\t\t\tnone-found") in evidence, evidence[:400])
        check("a class inside another sheet is never taken for a use",
              "\texact\tapp/unused.module.css" not in evidence, evidence[:400])
        check("the evidence file names the kind and the role of every finding",
              evidence.split("\n")[0].split("\t")[:4]
              == ["statement", "searched", "kind", "role"], evidence.split("\n")[0])
        code, out, err = run("style_links.py", "find", "--analysis", analysis,
                             "--max-rows", "1")
        capped = open(os.path.join(analysis, "style-candidates.tsv"),
                      encoding="utf-8").read()
        check("a cap is written into the file, never applied in silence",
              code == 0 and ("\tcapped\t" in capped) == ("were left out" in capped),
              capped[:300])
        run("style_links.py", "find", "--analysis", analysis)  # back to the full file

        print("\nThe refusals of the review")
        refusal_test(analysis)

    finally:
        shutil.rmtree(analysis, ignore_errors=True)

    print("\nStep 4 - the machine, on a synthetic export")
    machine_suite()

    print("\nStep 6 - the direction of the queue")
    direction_suite()

    print("\nUnit checks - the splitter and the boundaries")
    unit_suite()


FIXTURE = os.path.join(EVALS_DIR, "fixtures", "edges-front-real.tsv")


def joern_suite(joern_dir):
    """The real border: a pinned Joern against the stored real export.

    This is the test the synthetic export cannot replace. It builds the graph
    of the eval project with the actual tool, exports every link with the
    skill's own exporter, and compares the result line for line with the
    stored fixture. Then it feeds the fixture through the real translation
    and proves that every addressed end lands in a statement.
    """
    joern_dir = os.path.abspath(joern_dir)                 # where joern-cli lives
    launcher = os.path.join(joern_dir, "joern.bat")        # the tool on Windows
    frontend = os.path.join(joern_dir, "jssrc2cpg.bat")    # the TypeScript frontend
    if not os.path.isfile(launcher):                       # or on everything else
        launcher = os.path.join(joern_dir, "joern")
        frontend = os.path.join(joern_dir, "jssrc2cpg")
    if not os.path.isfile(launcher):                       # no tool, no suite
        check("joern is present at the given directory", False, joern_dir)
        return
    if not os.path.isfile(FIXTURE):                        # no fixture, nothing to hold against
        check("the real-export fixture exists", False, FIXTURE)
        return

    base = tempfile.mkdtemp(prefix="spider-eval-joern-")
    try:
        # The frontend looks upwards for the nearest package.json and zips that
        # whole directory next to it. Run over a copy with nothing above it, so
        # no archive ever lands inside the skill.
        project_copy = os.path.join(base, "project")       # the input, isolated
        shutil.copytree(TEST_PROJECT, project_copy)        # a plain copy
        cpg = os.path.join(base, "front.cpg.bin")          # the graph of the eval project
        result = subprocess.run([frontend, project_copy, "-o", cpg],
                                capture_output=True, text=True, cwd=base)
        check("the frontend builds the graph", result.returncode == 0,
              (result.stderr or result.stdout)[-300:])
        environment = dict(os.environ)                     # the exporter reads these two
        environment["SPIDER_CPG"] = cpg.replace("\\", "/")
        environment["SPIDER_OUT"] = os.path.join(base, "edges.tsv").replace("\\", "/")
        result = subprocess.run([launcher, "--script",
                                 os.path.join(SCRIPTS, "joern_export.sc")],
                                capture_output=True, text=True,
                                env=environment, cwd=base)
        check("the exporter runs to the end", result.returncode == 0
              and "SPIDER_WRITTEN" in result.stdout,
              (result.stderr or result.stdout)[-300:])

        exported = sorted(line.replace("\\", "/") for line in
                          open(os.path.join(base, "edges.tsv"), encoding="utf-8")
                          .read().split("\n") if line.strip())
        stored = sorted(line for line in
                        open(FIXTURE, encoding="utf-8").read().split("\n")
                        if line.strip())
        check("the real export matches the stored fixture line for line",
              exported == stored,
              "exported " + str(len(exported)) + " lines, stored "
              + str(len(stored)))

        analysis = tempfile.mkdtemp(prefix="spider-eval-joern-an-")
        try:                                               # the fixture through the translation
            with open(os.path.join(analysis, "source-files.txt"), "w",
                      encoding="utf-8", newline="\n") as fh:
                for name in SOURCE_FILES:                  # the whole eval project
                    fh.write(name + "\n")
            code, out, err = run("statements.py", "copy",
                                 "--project", TEST_PROJECT, "--analysis", analysis)
            check("the fixture analysis copies", code == 0, err or out)
            code, out, err = run("statements.py", "split",
                                 "--analysis", analysis, "--project", TEST_PROJECT)
            check("the fixture analysis splits", code == 0, err or out)
            code, out, err = run("name_links.py", "derive", "--analysis", analysis)
            check("the fixture name graph derives - REF landings need it",
                  code == 0, err or out)
            os.makedirs(os.path.join(analysis, "machine"))
            shutil.copyfile(FIXTURE, os.path.join(analysis, "machine",
                                                  "edges-front.tsv"))
            code, out, err = run("machine_links.py", "merge", "--analysis", analysis)
            check("the real links merge and translate", code == 0, err or out)
            landed = re.search(r"an address in no statement\s+0\b", out)
            check("every addressed end of the real export lands in a statement",
                  landed is not None, out)
        finally:
            shutil.rmtree(analysis, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def write_lines(path, lines):
    """Writes a small file, one line per entry, always UTF-8."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def machine_suite():
    """Step 4 on a synthetic export: directions, the isolated pair, the guards."""
    base = tempfile.mkdtemp(prefix="spider-eval-machine-")
    try:
        os.makedirs(os.path.join(base, "machine"))
        write_lines(os.path.join(base, "statements.txt"), [
            "1 | app/a.py | 1-2 | entry uses value",       # the entry point
            "2 | app/a.py | 4-5 | definition of value",    # reached through the flipped kind
            "3 | app/b.py | 1-3 | dead caller",            # the isolated pair,
            "4 | app/b.py | 5-8 | dead callee",            # linked only to each other
            "5 | app/c.css | 1-4 | a style rule",          # a file the graph cannot read
            "6 | app/a.py | 7-9 | called from entry",      # reached through a call
        ])
        write_lines(os.path.join(base, "entry-points.txt"), ["1"])
        write_lines(os.path.join(base, "read-progress.txt"), ["6"])
        code, out, err = run("database.py", "init", "--analysis", base)
        check("the synthetic base is created", code == 0, err or out)

        code, out, err = run("machine_links.py", "walk", "--analysis", base)
        check("the walk refuses before the fill", code != 0, out)

        RICH = "\t\t\t"                                    # method, label, code: empty
        write_lines(os.path.join(base, "machine", "edges-main.tsv"), [
            "CALL\tapp/a.py\t1\tapp/a.py\t7",              # the entry calls 6
            "REACHING_DEF\tapp/a.py\t4\tapp/a.py\t1",      # module-body wiring; structural
            "CALL\tapp/b.py\t1\tapp/b.py\t5",              # the isolated pair 3 -> 4
            "AST\tapp/a.py\t1\tapp/a.py\t2",               # structure; never enters the base
            "CALL\tapp/a.py\t1\t\t",                       # an end without an address
            "REF\tapp/a.py\t7\tapp/a.py\t4",               # lands on a defining statement
            "REF\tapp/a.py\t7\tapp/a.py\t1",               # scope wiring: 1 defines nothing
            # the rich twelve-column shape, in the same file: a REF whose
            # target node the graph itself calls LOCAL is scope wiring and
            # is cut by that record alone
            "REF\tapp/a.py\t7\t<m>\tCALL\tuse"
            "\tapp/a.py\t4\t<m>\tLOCAL\tvalue\t",
        ])
        write_lines(os.path.join(base, "defined-names.tsv"), [
            "2\tvalue",                                    # statement 2 defines a name
        ])
        code, out, err = run("machine_links.py", "merge", "--analysis", base)
        check("the merge translates the causal links", code == 0, err or out)
        translated = open(os.path.join(base, "links-by-id.tsv"),
                          encoding="utf-8").read()
        check("the data-flow kind is module-body wiring and stays out",
              "REACHING_DEF" not in translated, translated)
        check("the structural kind never enters the translated file",
              "AST" not in translated, translated)
        check("a REF onto a defining statement enters",
              "6\t2\tREF" in translated, translated)
        check("a REF onto a statement that defines nothing stays out",
              "6\t1\tREF" not in translated
              and re.search(r"REF into no definition - scope wiring\s+1\b",
                            out) is not None, out)
        check("a REF the graph itself lands on a LOCAL node is cut by "
              "the node label",
              re.search(r"REF into scope wiring - node label\s+1\b",
                        out) is not None, out)

        code, out, err = run("machine_links.py", "fill", "--analysis", base)
        check("the fill stores the links and sets no mark", code == 0
              and "No visited mark was set" in out, err or out)
        code, out, err = run("machine_links.py", "fill", "--analysis", base)
        check("a second fill is refused", code != 0, out)

        code, out, err = run("machine_links.py", "walk", "--analysis", base)
        check("the walk runs after the fill", code == 0, err or out)
        database = database_of(base)
        try:
            visited = sorted(row[0] for row in database.execute(
                "SELECT id FROM statements WHERE visited=1"))
            states = dict(database.execute(
                "SELECT id, machine_state FROM statements"))
        finally:
            database.close()
        check("the walk reaches the entry, its callee, and the definition "
              "through its user's REF - not through neighbourhood",
              visited == [1, 2, 6], str(visited))
        check("the isolated dead pair stays unvisited",
              states.get(3) == "unreached" and states.get(4) == "unreached",
              str(states))
        check("the style rule is unsupported, never unreached",
              states.get(5) == "unsupported", str(states))

        answer = run_json("review.py", "sweep", "--analysis", base, "--dry")
        check("the sweep names only the never-examined statements",
              answer.get("would_sweep") == 1
              and answer.get("first_twenty") == [5], str(answer))
        answer = run_json("review.py", "sweep", "--analysis", base)
        check("the sweep hands the blind spot to the review",
              answer.get("swept") == 1 and answer.get("now_unresolved") == 1,
              str(answer))

        code, out, err = run("machine_links.py", "reset", "--analysis", base)
        check("the reset refuses without the explicit key", code != 0, out)
        # One statement carries a real review decision and one carries only the
        # sweep's mark. The first must survive the reset; the second must fall
        # with the machine states it was derived from, or a later walk that
        # reaches it would leave it visited AND unresolved at once.
        database = database_of(base)
        try:
            database.execute("UPDATE statements SET unresolved=1, reviewed=1 "
                             "WHERE id=2")
            database.commit()
        finally:
            database.close()
        code, out, err = run("machine_links.py", "reset", "--analysis", base,
                             "--confirm")
        check("the reset clears the machine and nothing else", code == 0
              and "Machine links left:             0" in out, err or out)
        database = database_of(base)
        try:
            visited = database.execute(
                "SELECT COUNT(*) FROM statements WHERE visited=1").fetchone()[0]
            swept_left = database.execute(
                "SELECT COUNT(*) FROM statements WHERE unresolved=1 "
                "AND reviewed IS NULL").fetchone()[0]
            reviewed_left = database.execute(
                "SELECT COUNT(*) FROM statements WHERE unresolved=1 "
                "AND reviewed=1").fetchone()[0]
        finally:
            database.close()
        check("after the reset no machine mark remains", visited == 0, str(visited))
        check("the sweep's marks fall with the machine states they came from",
              swept_left == 0, str(swept_left))
        check("a real review decision survives the reset", reviewed_left == 1,
              str(reviewed_left))

        write_lines(os.path.join(base, "machine", "edges-bad.tsv"),
                    ["CALL\tonly\tthree"])                 # a malformed export line
        code, out, err = run("machine_links.py", "merge", "--analysis", base)
        check("a malformed export line is a named error, never a silent skip",
              code != 0 and "neither five nor twelve columns" in (out + err),
              out + err)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def direction_suite():
    """A dead caller of a living statement is never brought back to life."""
    base = tempfile.mkdtemp(prefix="spider-eval-direction-")
    try:
        write_lines(os.path.join(base, "statements.txt"), [
            "1 | app/a.py | 1-2 | the entry, name assembled at runtime",
            "2 | app/a.py | 4-5 | a dead caller of the entry",
            "3 | app/a.py | 7-8 | never reached by anything",
        ])
        write_lines(os.path.join(base, "entry-points.txt"), ["1"])
        write_lines(os.path.join(base, "read-progress.txt"), ["3"])
        code, out, err = run("database.py", "init", "--analysis", base)
        check("the direction base is created", code == 0, err or out)

        answer = run_json("traverse.py", "next", "--analysis", base)
        check("the entry is handed over", answer.get("id") == 1, str(answer))
        answer = run_json("traverse.py", "record", "--analysis", base,
                          "--id", "1", "--inputs", "2", "--outputs", "",
                          "--unresolved")
        check("the entry is recorded unresolved", answer.get("unresolved") is True,
              str(answer))

        write_lines(os.path.join(base, "review.md"), [
            "## Statement 1", "",
            "The name is assembled at runtime; the dead caller 2 names it, "
            "but nothing executes 2 itself.",
        ])
        answer = run_json("review.py", "resolve", "--analysis", base,
                          "--id", "1", "--inputs", "2", "--outputs", "")
        check("resolving queues nothing from the inputs",
              answer.get("added_to_queue") == [], str(answer))
        database = database_of(base)
        try:
            queued = database.execute(
                "SELECT COUNT(*) FROM pending_queue").fetchone()[0]
            dead = database.execute(
                "SELECT visited FROM statements WHERE id=2").fetchone()[0]
        finally:
            database.close()
        check("the queue stays empty", queued == 0, str(queued))
        check("the dead caller stays unvisited", not dead, str(dead))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def unit_suite():
    """The splitter and the boundaries, called directly."""
    sys.path.insert(0, SCRIPTS)                            # import the programs themselves
    import statements as st                                # the splitter
    import style_links as sl                               # the boundaries

    joined = st.join_lines(['x = "a  b" +', '  "c"'], 1, 2)
    check("the inside of a string keeps its spaces",
          '"a  b"' in joined, joined)
    check("whitespace outside strings still collapses",
          '+ "c"' in joined, joined)

    try:
        st.css_statements("a { color: red;")               # an unclosed block
        check("an unclosed style block is refused", False, "no error raised")
    except ValueError as error:
        check("an unclosed style block is refused", "unclosed" in str(error),
              str(error))

    kids = st.css_rule_selectors([".alive,", ".dead {", "  color: red;", "}"], 1, 4)
    check("every name of a rule is addressable on its own",
          [(k[0], k[1]) for k in kids] == [(1, ".alive"), (2, ".dead")], str(kids))
    check("each name knows its own line",
          kids[0][2] == 1 and kids[1][2] == 2, str(kids))

    exact = sl.exact_pattern("btn")                        # the identifier boundaries
    check("exact search does not cross an identifier boundary",
          exact.search("class btn here") is not None
          and exact.search("button") is None
          and exact.search("btn-primary") is None, "boundary test")
    prefix = sl.prefix_pattern("btn")                      # the assembled schemes
    check("prefix search follows only the named joiners",
          prefix.search("btn-primary") is not None
          and prefix.search("btn__icon") is not None
          and prefix.search("btnx") is None, "joiner test")

    base = tempfile.mkdtemp(prefix="spider-eval-paths-")
    try:                                                   # the path refusals
        write_lines(os.path.join(base, "source-files.txt"), ["../outside.py"])
        try:
            st.read_source_list(base)
            check("a path climbing out of the project is refused", False,
                  "no error raised")
        except SystemExit as error:
            check("a path climbing out of the project is refused",
                  "climbs" in str(error), str(error))
        write_lines(os.path.join(base, "source-files.txt"), ["C:/windows/x.py"])
        try:
            st.read_source_list(base)
            check("an absolute path is refused", False, "no error raised")
        except SystemExit as error:
            check("an absolute path is refused", "absolute" in str(error),
                  str(error))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    typescript = st.find_typescript(SKILL_DIR)             # the skill's own parser
    check("the parser comes from the skill directory alone",
          typescript is not None and "spider" in typescript.replace("\\", "/"),
          str(typescript))
    bad = tempfile.mkdtemp(prefix="spider-eval-ts-")
    try:                                                   # broken syntax is named
        bad_file = os.path.join(bad, "broken.ts").replace("\\", "/")
        write_lines(bad_file, ["const x = = 1;"])          # a real syntax error
        helper = os.path.join(SCRIPTS, "ts_statements.js") # the helper itself
        answer = st.typescript_statements([bad_file], typescript, helper)
        entry = answer.get(bad_file, {})
        check("broken TypeScript syntax is an error, never a clean split",
              "error" in entry and "syntax" in entry["error"], str(entry))
    finally:
        shutil.rmtree(bad, ignore_errors=True)


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
# The load graph - the half of reaching that no call graph can express
# --------------------------------------------------------------------------

# A made-up project with exactly the shapes that decide the matter: a live
# chain of imports, an orphan nothing imports, a sheet loaded by the markup,
# and a sheet loaded by that sheet. Written as statements directly, so the
# suite needs neither Node nor Java and tests the load graph alone.
LOAD_FILES = {
    "backend/apps/live/entry.py": [
        "from apps.live import used",
        "SETTING = 1",
        "configure_logging(used.helper)",
        "class LiveConfig(AppConfig): name = 'live'",
    ],
    "backend/apps/live/used.py": [
        "from __future__ import annotations",
        "def helper(): return SHARED",
        "SHARED = 1",
        "UNREAD = 2",
        "def wrapper():\\n    from apps.live.deep import INNER, Box\\n"
        "    return Box(INNER)",
    ],
    "backend/apps/live/deep.py": [
        "INNER = 5",
        "@dataclass(frozen=True)\\nclass Box:\\n    kind: int = 0",
    ],
    "backend/apps/dead/orphan.py": [
        "from __future__ import annotations",
        "def never_called(): return 2",
    ],
    "frontend/app/layout.tsx": [
        'import "./globals.css";',
        'import { used } from "@/lib/used";',
        "export default function Root() { return used(); }",
    ],
    "frontend/app/globals.css": [
        '@import "./theme.css";',
        ".live-class { color: red; }",
        "html { min-height: 100%; }",
    ],
    "frontend/app/theme.css": [
        ".theme-rule { color: blue; }",
    ],
    "frontend/lib/used.ts": [
        "export function used() { return 3; }",
    ],
    "frontend/lib/deepdef.ts": [
        "export function realThing() { return 1; }",
    ],
    "frontend/lib/barrel.ts": [
        'export * from "./deepdef.js";',
    ],
    "frontend/lib/consumer.ts": [
        'import { realThing } from "./barrel.js";',
        "export function useIt() { return realThing(); }",
    ],
    "frontend/lib/featdef.ts": [
        "export function feat() { return 7; }",
    ],
    "frontend/lib/ns.feat.ts": [
        'export * from "./featdef.js";',
    ],
    "frontend/lib/nsroot.ts": [
        'import * as Feat from "./ns.feat.js";',
        "export { Feat };",
    ],
    "frontend/lib/nsuser.ts": [
        'import { Feat } from "./nsroot.js";',
        "export function drive() { return Feat.feat(); }",
    ],
    "frontend/lib/orphan.ts": [
        "export function orphaned() { return 4; }",
    ],
    "frontend/lib/shadow.ts": [
        "function sameName() { return 0; }",
        "export function shadowKeeper() { return sameName(); }",
    ],
    "frontend/lib/pub.ts": [
        "export function sameName() { return 1; }",
    ],
    "frontend/lib/barrel2.ts": [
        'export * from "./shadow.js";',
        'export * from "./pub.js";',
    ],
    "frontend/lib/barrel2user.ts": [
        'import { sameName } from "./barrel2.js";',
        "export function callSame() { return sameName(); }",
    ],
    "frontend/lib/over.ts": [
        "export function pick(a: string): string;",
        "export function pick(a: number): number;",
        "export function pick(a: any): any { return a; }",
    ],
    "frontend/lib/overuser.ts": [
        'import { pick } from "./over.js";',
        "export function callPick() { return pick(1); }",
    ],
    "frontend/lib/registry.ts": [
        "export function register(x: number) { return x; }",
        "register(9);",
    ],
    "frontend/lib/regbarrel.ts": [
        'export * from "./registry.js";',
    ],
    "frontend/lib/api.ts": [
        "export function surfaceOnly() { return 5; }",
    ],
    "frontend/lib/face.ts": [
        'import "./regbarrel.js";',
        'export * from "./api.js";',
    ],
    "frontend/components/Island.tsx": [
        '"use client";',
        "export function Lonely() { return null; }",
    ],
}
LOAD_ENTRIES = (("backend/apps/live/entry.py", 4),
                ("frontend/app/layout.tsx", 3),
                ("frontend/components/Island.tsx", 1),
                ("frontend/lib/face.ts", 1),
                ("frontend/lib/face.ts", 2))


def build_load_project(analysis):
    """Writes the made-up project as a snapshot, a statement list and entries."""
    numbering = {}                                     # (file, ordinal) -> id
    lines = []                                         # the statement list itself
    next_id = 1
    for name in sorted(LOAD_FILES):                    # a fixed order, so ids are stable
        path = os.path.join(analysis, "source", *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(LOAD_FILES[name]) + "\n")
        for ordinal, text in enumerate(LOAD_FILES[name], 1):
            numbering[(name, ordinal)] = next_id
            lines.append("%d | %s | %d-%d | %s" % (next_id, name, ordinal, ordinal, text))
            next_id += 1
    with open(os.path.join(analysis, "statements.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(analysis, "entry-points.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        for name, ordinal in LOAD_ENTRIES:
            fh.write(str(numbering[(name, ordinal)]) + "\n")
    with open(os.path.join(analysis, "read-progress.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(str(next_id - 1) + "\n")
    # The names of the style rules, as step 1 records them. The load graph
    # reads them to tell a rule that names something from one that names
    # nothing and so acts by being present.
    with open(os.path.join(analysis, "css-selectors.tsv"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("statement_id\tordinal\tselector\tline\n")
        for name in sorted(LOAD_FILES):
            if not name.endswith(".css"):
                continue
            for ordinal, text in enumerate(LOAD_FILES[name], 1):
                head = text.split("{", 1)[0].strip()
                if head and not head.startswith("@"):
                    fh.write("%d\t1\t%s\t%d\n"
                             % (numbering[(name, ordinal)], head, ordinal))
    # The manifest and the split report, so that step 7 gets past its own
    # snapshot checks and reaches the one this suite is about.
    import hashlib
    checksums = {}                                     # path -> sha256 of the copy
    for name in sorted(LOAD_FILES):
        path = os.path.join(analysis, "source", *name.split("/"))
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            digest.update(fh.read())
        checksums[name] = digest.hexdigest()
    with open(os.path.join(analysis, "manifest.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump({"files": checksums}, fh)
    with open(os.path.join(analysis, "split-report.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump({"files_not_split": []}, fh)
    return numbering


def load_graph_suite():
    """The load graph, the asymmetry at the sheet door, and the coverage gate."""
    analysis = tempfile.mkdtemp(prefix="spider-load-")
    try:
        numbering = build_load_project(analysis)
        code, out, err = run("database.py", "init", "--analysis", analysis)
        check("the load-graph base is created", code == 0, err)

        code, out, err = run("load_links.py", "derive", "--analysis", analysis)
        check("derive succeeds", code == 0, err)

        pairs = set()                                  # every derived link
        with open(os.path.join(analysis, "load-links.tsv"), encoding="utf-8") as fh:
            for line in fh:
                columns = line.strip().split("\t")
                if len(columns) == 3:
                    pairs.add((int(columns[0]), int(columns[1]), columns[2]))
        every_kind = set(k for _, _, k in pairs)
        check("every derived link is of kind LOADS", every_kind == {"LOADS"},
              str(every_kind))

        entry_import = numbering[("backend/apps/live/entry.py", 1)]  # the import line
        used_future = numbering[("backend/apps/live/used.py", 1)]    # from __future__
        used_def = numbering[("backend/apps/live/used.py", 2)]       # def helper
        used_unread = numbering[("backend/apps/live/used.py", 4)]    # UNREAD = 2
        check("an import does NOT reach the naming statements of the loaded file",
              (entry_import, used_def, "LOADS") not in pairs
              and (entry_import, used_unread, "LOADS") not in pairs)
        check("an import DOES reach the side effects of the loaded file",
              (entry_import, used_future, "LOADS") in pairs)

        layout_css = numbering[("frontend/app/layout.tsx", 1)]       # import "./globals.css"
        sheet_import = numbering[("frontend/app/globals.css", 1)]    # the @import in it
        sheet_rule = numbering[("frontend/app/globals.css", 2)]      # .live-class
        sheet_unnamed = numbering[("frontend/app/globals.css", 3)]   # html { ... }
        check("loading a sheet reaches its own at-rule",
              (layout_css, sheet_import, "LOADS") in pairs)
        check("loading a sheet does NOT reach its named rules",
              (layout_css, sheet_rule, "LOADS") not in pairs)
        check("loading a sheet DOES reach a rule that names nothing",
              (layout_css, sheet_unnamed, "LOADS") in pairs)

        theme_rule = numbering[("frontend/app/theme.css", 1)]
        check("a sheet loading a sheet does not reach its rules either",
              (sheet_import, theme_rule, "LOADS") not in pairs)

        entry_call = numbering[("backend/apps/live/entry.py", 3)]    # configure_logging()
        entry_statement = numbering[("backend/apps/live/entry.py", 4)]
        setting = numbering[("backend/apps/live/entry.py", 2)]
        check("an entry point reaches only the side effects of its own file",
              (entry_statement, entry_call, "LOADS") in pairs
              and (entry_statement, setting, "LOADS") not in pairs)

        island_directive = numbering[("frontend/components/Island.tsx", 1)]
        demoted_text = open(os.path.join(analysis, "demoted-entries.txt"),
                            encoding="utf-8").read()
        check("a directive in a file nothing imports is demoted",
              str(island_directive) in demoted_text, demoted_text)

        orphan_py = numbering[("backend/apps/dead/orphan.py", 2)]
        orphan_ts = numbering[("frontend/lib/orphan.ts", 1)]
        check("nothing reaches a file nobody imports",
              not any(target in (orphan_py, orphan_ts) for _, target, _ in pairs))

        code, out, err = run("name_links.py", "derive", "--analysis", analysis)
        check("the name graph derives", code == 0, err)
        name_pairs = set()
        with open(os.path.join(analysis, "name-links.tsv"), encoding="utf-8") as fh:
            for line in fh:
                columns = line.strip().split("\t")
                if len(columns) == 3:
                    name_pairs.add((int(columns[0]), int(columns[1])))
        used_shared = numbering[("backend/apps/live/used.py", 3)]    # SHARED = 1
        alias_used = numbering[("frontend/lib/used.ts", 1)]
        layout_root = numbering[("frontend/app/layout.tsx", 3)]
        layout_alias = numbering[("frontend/app/layout.tsx", 2)]
        check("a used name links its user to the definition, across files",
              (layout_root, alias_used) in name_pairs)
        check("an aliased import is resolved against the snapshot roots",
              (layout_root, layout_alias) in name_pairs)
        check("a name used in its own file is linked there",
              (used_def, used_shared) in name_pairs)
        check("an unread name gets no link",
              not any(target == used_unread for _, target in name_pairs))
        wrapper_def = numbering[("backend/apps/live/used.py", 5)]
        deep_inner = numbering[("backend/apps/live/deep.py", 1)]
        deep_box = numbering[("backend/apps/live/deep.py", 2)]
        check("an import inside a function body links its statement "
              "to the definition it reaches for",
              (wrapper_def, deep_inner) in name_pairs)
        check("a decorated class is a definition all the same",
              (wrapper_def, deep_box) in name_pairs)
        consumer_import = numbering[("frontend/lib/consumer.ts", 1)]
        consumer_use = numbering[("frontend/lib/consumer.ts", 2)]
        barrel_star = numbering[("frontend/lib/barrel.ts", 1)]
        real_def = numbering[("frontend/lib/deepdef.ts", 1)]
        check("a name imported through a barrel links its user to the "
              "true definition",
              (consumer_use, real_def) in name_pairs)
        check("and to the re-export the name flows through",
              (consumer_use, barrel_star) in name_pairs
              and (consumer_use, consumer_import) in name_pairs)
        drive_use = numbering[("frontend/lib/nsuser.ts", 2)]
        feat_def = numbering[("frontend/lib/featdef.ts", 1)]
        ns_star = numbering[("frontend/lib/ns.feat.ts", 1)]
        ns_import = numbering[("frontend/lib/nsroot.ts", 1)]
        ns_export = numbering[("frontend/lib/nsroot.ts", 2)]
        check("an emulated namespace - import * as X, export { X } - walks "
              "to the definition of X.feat",
              (drive_use, feat_def) in name_pairs)
        check("and needs the whole chain the name rides through",
              (drive_use, ns_import) in name_pairs
              and (drive_use, ns_export) in name_pairs
              and (drive_use, ns_star) in name_pairs)
        call_pick = numbering[("frontend/lib/overuser.ts", 2)]
        over_one = numbering[("frontend/lib/over.ts", 1)]
        over_two = numbering[("frontend/lib/over.ts", 2)]
        over_impl = numbering[("frontend/lib/over.ts", 3)]
        check("an overloaded function is three statements of one name, and "
              "its user needs all three",
              (call_pick, over_one) in name_pairs
              and (call_pick, over_two) in name_pairs
              and (call_pick, over_impl) in name_pairs)
        call_same = numbering[("frontend/lib/barrel2user.ts", 2)]
        shadow_local = numbering[("frontend/lib/shadow.ts", 1)]
        pub_def = numbering[("frontend/lib/pub.ts", 1)]
        check("a module-local of an earlier barrel member never shadows "
              "the exported name of a later one",
              (call_same, pub_def) in name_pairs
              and (call_same, shadow_local) not in name_pairs)

        code, out, err = run("machine_links.py", "fill", "--analysis", analysis)
        check("fill accepts both derived graphs", code == 0, err)
        check("fill says where the links came from",
              "the load graph" in out and "the name graph" in out, out)

        code, out, err = run("machine_links.py", "walk", "--analysis", analysis)
        check("walk succeeds on the derived graphs", code == 0, err)
        check("walk reports its own coverage", "Coverage of this walk" in out, out)
        check("walk skips the demoted entries", "Demoted entries skipped" in out, out)

        database = database_of(analysis)
        try:
            reached = set(row[0] for row in database.execute(
                "SELECT id FROM statements WHERE machine_state='reached'"))
            meta = dict(database.execute("SELECT key, value FROM meta"))
        finally:
            database.close()
        check("the used definition and its constant are reached",
              used_def in reached and used_shared in reached)
        check("the unread constant is NOT reached", used_unread not in reached)
        check("the island's statements are not reached",
              island_directive not in reached)
        check("the orphan files are not reached",
              orphan_py not in reached and orphan_ts not in reached)
        check("a loaded sheet's at-rule is reached", sheet_import in reached)
        check("a loaded sheet's ordinary rule is not", sheet_rule not in reached)
        register_call = numbering[("frontend/lib/registry.ts", 2)]
        register_def = numbering[("frontend/lib/registry.ts", 1)]
        reg_star = numbering[("frontend/lib/regbarrel.ts", 1)]
        check("a self-registering module is reached through the barrel "
              "that detonates it",
              reg_star in reached and register_call in reached
              and register_def in reached)
        surface_def = numbering[("frontend/lib/api.ts", 1)]
        face_export = numbering[("frontend/lib/face.ts", 2)]
        check("the published surface of an entry re-export is reached",
              face_export in reached and surface_def in reached)
        check("the walk recorded both graphs",
              meta.get("walk_had_load_graph") == "yes"
              and meta.get("walk_had_name_graph") == "yes", str(meta))

        # The gate: the same base, walked with the call graph alone, must stop
        # step 7 instead of passing its blindness off as a finding.
        code, out, err = run("machine_links.py", "reset", "--analysis", analysis,
                             "--confirm")
        check("reset clears the machine work", code == 0, err)
        os.remove(os.path.join(analysis, "load-links.tsv"))
        os.remove(os.path.join(analysis, "name-links.tsv"))
        orphan_py_first = numbering[("backend/apps/dead/orphan.py", 1)]
        with open(os.path.join(analysis, "links-by-id.tsv"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("%d\t%d\tCALL\n" % (entry_statement, entry_call))
            # A call between two statements no entry point reaches: linked, and
            # unreached. This is the shape that walked straight into the final
            # list in 2.1 - the shape the gate exists to stop.
            fh.write("%d\t%d\tCALL\n" % (orphan_py_first, orphan_py))
        code, out, err = run("machine_links.py", "fill", "--analysis", analysis)
        check("fill accepts a graph export on its own", code == 0, err)
        code, out, err = run("machine_links.py", "walk", "--analysis", analysis)
        check("walk without the derived graphs says so",
              "A MACHINE GRAPH IS MISSING" in out, out)
        os.makedirs(os.path.join(analysis, "machine"), exist_ok=True)
        code, out, err = run("final_list.py", "build", "--analysis", analysis,
                             "--project", os.path.join(analysis, "source"))
        check("step 7 refuses a list built on a call graph alone", code != 0,
              out + err)
        check("and says why", "machine walked without" in (out + err), out + err)
    finally:
        shutil.rmtree(analysis, ignore_errors=True)


# --------------------------------------------------------------------------
# The pieces taken from the colleague's 3.0: shell, quarantine, the scope
# register, the fill sums and the never-seen live files - end to end
# --------------------------------------------------------------------------

def takeover_suite():
    """Shell reading, quarantine, register, sums, and the never-seen files."""
    project = tempfile.mkdtemp(prefix="spider-eval-sh-proj-")
    analysis = tempfile.mkdtemp(prefix="spider-eval-sh-an-")
    try:
        with open(os.path.join(project, "deploy.sh"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("#!/usr/bin/env bash\nset -euo pipefail\n"
                     "source lib.sh\nmain() {\n    helper_one\n}\n"
                     'main "$@"\n')
        with open(os.path.join(project, "lib.sh"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("helper_one() {\n    echo one\n}\n"
                     "helper_two() {\n    echo two\n}\n")
        with open(os.path.join(project, "bad.sh"), "wb") as fh:
            fh.write(b"\xff\xfe broken bytes\n")           # not UTF-8 on purpose
        write_lines(os.path.join(analysis, "source-files.txt"),
                    ["bad.sh", "deploy.sh", "lib.sh"])

        # the register: a listed file with a wrong role is refused
        write_lines(os.path.join(analysis, "source-scope.tsv"), [
            "bad.sh\tapplication\tdeploy helper named by deploy.sh",
            "deploy.sh\ttest\twrongly registered on purpose",
            "lib.sh\tapplication\tfunctions deploy.sh sources",
        ])
        code, out, err = run("statements.py", "copy",
                             "--project", project, "--analysis", analysis)
        check("a listed file registered under another role is refused",
              code != 0 and "registered as test" in (out + err), out + err)
        write_lines(os.path.join(analysis, "source-scope.tsv"), [
            "bad.sh\tapplication\tdeploy helper named by deploy.sh",
            "deploy.sh\tapplication\tthe deploy program itself",
            "lib.sh\tapplication\tfunctions deploy.sh sources",
            "tests/extra.py\ttest\ta test file, rule 1 of the owner",
        ])
        code, out, err = run("statements.py", "copy",
                             "--project", project, "--analysis", analysis)
        check("the copy quarantines the non-UTF-8 file and goes on",
              code == 0 and "Quarantined (not UTF-8): 1" in out, out + err)
        manifest = json.load(open(os.path.join(analysis, "manifest.json"),
                                  encoding="utf-8"))
        check("the quarantined file is named in the manifest",
              [q["file"] for q in manifest.get("quarantined", [])] == ["bad.sh"]
              and "bad.sh" not in manifest["files"], str(manifest)[:200])

        code, out, err = run("statements.py", "split",
                             "--analysis", analysis, "--project", project)
        check("the shell files split", code == 0, err or out)
        listed = open(os.path.join(analysis, "statements.txt"),
                      encoding="utf-8").read().splitlines()
        check("a shell file splits into its functions and commands",
              len(listed) == 7, "\n".join(listed))
        write_lines(os.path.join(analysis, "entry-points.txt"), ["1", "5"])
        write_lines(os.path.join(analysis, "read-progress.txt"), ["7"])

        code, out, err = run("database.py", "init", "--analysis", analysis)
        check("the shell base is created", code == 0, err or out)
        code, out, err = run("load_links.py", "derive", "--analysis", analysis)
        check("the load graph reads `source` as loading", code == 0, err or out)
        code, out, err = run("name_links.py", "derive", "--analysis", analysis)
        check("the name graph reads shell functions", code == 0, err or out)
        code, out, err = run("machine_links.py", "fill", "--analysis", analysis)
        check("the fill accepts the shell graphs", code == 0, err or out)
        code, out, err = run("machine_links.py", "walk", "--analysis", analysis)
        check("the walk runs over the shell project", code == 0, err or out)
        database = database_of(analysis)
        try:
            visited = sorted(row[0] for row in database.execute(
                "SELECT id FROM statements WHERE visited=1"))
        finally:
            database.close()
        check("the sourced function that is called is reached, the one "
              "nobody calls is not",
              visited == [1, 2, 3, 4, 5, 6], str(visited))

        # the fill sums: a derived graph edited after the fill is loud
        name_links_path = os.path.join(analysis, "name-links.tsv")
        original = open(name_links_path, encoding="utf-8").read()
        with open(name_links_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("1\t7\tUSES\n")                       # a forged link
        code, out, err = run("final_list.py", "build", "--analysis", analysis,
                             "--project", project)
        check("a derived graph edited after the fill stops step 7",
              code != 0 and "changed after the fill" in (out + err), out + err)
        with open(name_links_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(original)                             # restored exactly

        # settle the one open statement, then build for real
        with open(os.path.join(analysis, "review.md"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("## Statement 7\nShell function helper_two: no statement "
                     "in the snapshot writes its name; the finder searched "
                     "every file.\nDecision: second kind.\n")
        code, out, err = run("review.py", "sweep", "--analysis", analysis)
        check("the sweep hands over the unlinked shell function", code == 0, out + err)
        code, out, err = run("review.py", "reopen", "--analysis", analysis,
                             "--id", "7", "--place", "none")
        check("the review settles it as the second kind", code == 0, out + err)
        with open(os.path.join(project, "extra.py"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("print('born after the snapshot')\n")
        code, out, err = run("final_list.py", "build", "--analysis", analysis,
                             "--project", project)
        check("the final list builds over the shell project", code == 0,
              out + err)
        document = open(os.path.join(analysis, "to-check-in-live-code.md"),
                        encoding="utf-8").read()
        check("the quarantined file stands in the document as a finding",
              "bad.sh" in document and "quarantined" in document.lower(),
              document[:400])
        check("a live file the snapshot never saw is named",
              "extra.py" in document, document[:400])
        check("a registered test file is not called never-seen",
              "tests/extra.py" not in document, document[:400])
        check("the document checksum is printed",
              "Document SHA-256:" in out, out)
    finally:
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(analysis, ignore_errors=True)


# --------------------------------------------------------------------------
# The style finder - the three defects the real run uncovered
# --------------------------------------------------------------------------

def style_suite():
    """At-rule names, the subject of a selector, and the cap that is never silent."""
    sys.path.insert(0, SCRIPTS)
    import statements as statements_module
    import style_links

    media = ["@media (max-width: 640px) {",
             "  .live-flow { width: 100%; }",
             "  .dead-grid { gap: 1px; }",
             "}"]
    names = statements_module.css_rule_selectors(media, 1, len(media))
    check("an at-rule records the names inside it",
          [row[1] for row in names] == [".live-flow", ".dead-grid"], str(names))
    check("each name inside an at-rule keeps its own line",
          [row[2] for row in names] == [2, 3], str(names))

    commented = ["/* .not-a-rule { } */", ".real { a: b; }"]
    check("a name inside a comment is not a name",
          [row[1] for row in statements_module.css_rule_selectors(
              commented, 1, len(commented))] == [".real"])

    quoted = ['.q::before { content: "{"; }']
    check("a brace inside a string does not shift the nesting",
          [row[1] for row in statements_module.css_rule_selectors(
              quoted, 1, len(quoted))] == [".q::before"])

    subjects, context = style_links.subject_and_context(".wrapper .grid")
    check("a descendant selector styles its last class",
          subjects == ["grid"] and context == ["wrapper"],
          str(subjects) + " / " + str(context))
    subjects, context = style_links.subject_and_context(".card.is-open")
    check("a compound selector styles every class on the same element",
          subjects == ["card", "is-open"] and context == [], str(subjects))
    subjects, context = style_links.subject_and_context(".list > .item:hover")
    check("a pseudo-class is not mistaken for a class",
          subjects == ["item"] and context == ["list"], str(subjects))

    roles = dict((name, role) for kind, name, role
                 in style_links.names_of(".wrapper .grid { a: b; }",
                                         [".wrapper .grid"]))
    check("the finder marks the subject and the context apart",
          roles == {"grid": "subject", "wrapper": "context"}, str(roles))


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
    parser.add_argument("--with-joern", default=None,
                        help="path to joern-cli; runs the real-graph suite. "
                             "Required before any publication.")
    arguments = parser.parse_args()

    if arguments.check:
        print("Checking a real run against expected.json")
        check_result(os.path.abspath(arguments.check))
    elif getattr(arguments, "self_test"):
        self_test()
        print("\nThe load graph - the half of reaching a call graph cannot express")
        load_graph_suite()
        print("\nThe style finder - the three defects the real run uncovered")
        style_suite()
        print("\nThe pieces taken from 3.0 - shell, quarantine, register, sums")
        takeover_suite()
        if arguments.with_joern:                           # the real border, when asked for
            print("\nThe real graph - pinned Joern against the fixture")
            joern_suite(arguments.with_joern)
        else:                                              # skipped is said out loud
            print("\nThe real-graph suite was SKIPPED (no --with-joern). "
                  "It is required before any publication.")
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
