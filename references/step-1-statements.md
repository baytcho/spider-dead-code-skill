# SPIDER - step 1: the statement list

Read this file before you begin step 1.

---

## 1. Starting

**The first thing the skill does is ask two questions:**

1. In which directory should the files that carry out the analysis be placed?
2. Which directory is going to be analysed?

After the two questions the work **stops** and waits for an answer. Nothing is
done until both answers arrive. Paths are never invented and never assumed.

Once both answers are in, the work begins.

---

## 2. Terms

**Project** - the directory that is going to be analysed. The code lives in it.

**Application code** - the files that do the work of the site. These are not
application code: tests, build and configuration files, third-party code, build
output, non-code files, machine-generated manifests.

**Analysis directory** - the directory named by the owner, where the files that
carry out the analysis are placed.

**Statement** - a complete logical unit of code.

**Top-level statement** - a statement that does not sit inside another
statement.

**Statement list** - a file in which every line is one top-level statement with
an id and an address.

**Address of a statement** - the name of the file it comes from and the line
numbers it occupies in that file.

---

## 3. What the skill does

The intelligence reads the project directory: which folders exist, which files,
how it is laid out. It establishes which files are application code and which
are not.

The intelligence copies into the analysis directory every file it has decided is
application code, keeping the same names and the same folder layout.

From that moment the project is not touched. All work happens inside the
analysis directory.

Every file in the analysis directory is split into statements. Comments and
blank lines drop out.

The top-level statements are taken. Statements contained inside them stay
inside, are written on their line and get no id of their own.

Every top-level statement is written on its own line of the statement list.
Every line gets an id: the first line is 1, the second is 2, and so on to the
last.

Every line of the statement list holds: id, file, first-last line, text.

---

## 4. What comes out

An analysis directory holding nothing but the application code, and a statement
list in which every line is one top-level statement with an id and an address.

---

## 5. Order of execution

### Move 1. The two questions

Ask them and wait for the answer. See section 1.

### Move 2. Looking through the project

The intelligence reads the project directory - which folders exist, which files,
how it is laid out. The structure is looked at, not assumed.

### Move 3. Separating out the application code

The intelligence writes `source-files.txt` into the analysis directory - one
path per line, relative to the project root, one line for every file it has
decided is application code.

The list is made by the intelligence, following the definition of application
code. It is not made by a program and it is not made by guesswork.

### Move 4. Copying

    python SKILL/scripts/statements.py copy --project "PROJECT" --analysis "ANALYSIS"

The program reads `source-files.txt` from the analysis directory and copies the
listed files, keeping the same names and the same folder layout. The project is
only read.

### Move 5. Splitting into statements

    python SKILL/scripts/statements.py split --analysis "ANALYSIS" --project "PROJECT"

The program splits every copied file into statements and writes `statements.txt`
into the analysis directory. The path to the project is optional - it only helps
to locate the TypeScript parser if it is not inside the skill directory.

### Move 6. Report

The numbers in the report are computed from the files, never from memory.

---

## 6. The splitter

It lives in `scripts/statements.py` and handles these languages:

| Files | Split by |
| --- | --- |
| `.py` | the Python parser itself (`ast`) |
| `.ts .tsx .js .jsx .mjs .cjs` | the TypeScript parser itself |
| `.css` | a splitter of its own, following the rules of the language |

A file that cannot be split is **never dropped silently** - it goes into the
report with the reason. A file lost in silence would be counted as covered while
nobody has read it.

The TypeScript parser is looked for in this order: inside the skill directory,
then in the project. If it is missing, run `npm install typescript@5` inside the
skill directory. Version 5 is required; version 6 and later do not expose the
same parser.

### What a line of the statement list looks like

    id | file | first-last | text

The text comes last. A statement that spans many lines in its own file is
written on a single line here: the line is read through its address, which
points at the exact place in the copied file.

---

## 7. Forbidden

- Modifying the project. The project is only read.
- Executing or building the project.
- Working before both answers have arrived.
- A number in the report written from memory.
- A verdict of needed or not needed. That is not part of step 1.
