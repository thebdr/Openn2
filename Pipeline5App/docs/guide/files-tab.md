# The Files tab

A tree of every file the pipeline reads or produces, grouped in sections, with a viewer on the right.

## What is listed

The sections come from the `files_tab:` block in
[config_project/app_config.yaml](src://config_project/app_config.yaml): each section names its root
folders (`${placeholder}` tokens resolve against the active project) and regex `include`/`exclude`
filters on the path relative to the root. Edit that block to reshape the tab - nothing about the
structure is baked into code. A project may carry its own `files_tab` in its app_config; without one
it inherits the app's.

## Viewers

- `.csv` opens as a grid with **in-cell editing**: double-click a data cell, Enter commits, Escape
  cancels; **Save** writes the table back in its own dialect (same delimiter, proper quoting).
  Multi-line cells refuse the single-line editor. `.xlsx` stays read-only with a sheet picker. Grid
  columns size themselves to the data - **drag a header separator** to resize one, **double-click
  the separator** to auto-fit it.
- **Text-based files edit in place**: change the text, **Save** (or `Ctrl+S`) writes atomically with
  the file's original BOM/newline style; **Revert** re-reads. Switching files with unsaved changes
  asks first. A file over the 50 MB editor cap opens read-only - use *Open externally*.
- `.yaml` / `.json` add **syntax highlighting** (live while typing), plus a **Text / Object explorer**
  toggle:
  - the Object explorer shows the document as a key/value tree,
  - double-click a value to edit it in place (Enter commits, Escape cancels),
  - keys containing `path` get a `…` file picker; `dir`/`folder`/`root` keys get a folder picker,
  - **Save** writes losslessly - comments, ordering, and quoting survive.
- Anything else shows the path strip with **Open externally** / **Open folder**.

Editing a pipeline-produced file is possible, but remember the next phase run regenerates it -
durable changes belong in the source documents or the config CSVs.

## The shipped system configuration (a read-only reference)

The **System configuration (shipped, read-only)** section lists the configuration that ships with
the active system (the `${system_config}` placeholder) - the REFERENCE a project starts from. Its
files open **read-only** in every viewer: the text view, the CSV grid (no in-place edits), and the
Object explorer (disabled here, because it saves).

What RUNS is your project's own copy: a new project is created with a copy of every one of these
files in its per-system configuration folder (`<project>/config_project/systems/<system>/`, same
relative path - under **Project configuration**), and that copy **overrides** the shipped one. So
the button on a shipped file usually reads **Open project copy** - it takes you to the file you
edit. On a project without its own copy of a file it reads **Create project copy** and makes one.
With no project open there is nowhere to put a copy (the button is disabled); then **Project
configuration** shows the app's builtin project configuration, which is what runs - and is edited
- until a project is opened. A project that carries its own `files_tab` block needs this section
added to show it.

## Template mode: chain-reaction templates

A `chain_reactions/templates.yaml` opens in the **template mode**. It is the editor for the
chain-reaction templates (see *Strict templates* in [Expressions](guide://expressions)).

- **Two-layer highlighting.** The YAML structure is highlighted as YAML. Inside a text template, the
  system's target language (Siemens: SCL - the system names it) sits underneath the template
  constructs:
  - `@use` / `@for` / `@if` / `@else` / `@end` and the `@use`'d template names;
  - `{holes}` with their expression tokens and format specs;
  - `{{ }}` literal braces.
- **Live problems.** Errors get a red squiggle and warnings an amber one. The list under the text
  shows each problem; click one to jump to it. The problems are what a chain reaction would report
  when it fires, found WITHOUT firing and in **every** branch, including an `@else` no row has taken
  yet:
  - a directive typo, an unclosed block, an unknown `@use`, a `@use` chain nested too deep;
  - a hole that does not compile, a lone brace, a format spec no value can satisfy (`{$x:03D}`).

  Warnings flag renders that succeed but probably are not what you meant:
  - a `where` that reads its own loop variable, or an `@if` that reads a loop row's missing column
    (both read blank - the branch is silently never taken);
  - a data function reading a column its table does not have - a `count(signals, $col ...)` /
    `where(` / `first(` predicate, `lookup` / `unique`'s column (it reads blank: `count` counts
    nothing) - or over a table the hook does not have at all (`before_300` has none), or inside
    another function's predicate or a `where` (it sees that row alone): it finds no rows;
  - a format spec on a JSON value - a list or an object in the rows (`{$type:>5}` - it fails on the
    rows that hold one; a JSON column that holds text is just text);
  - an empty hole `{}` (it renders nothing - write `{{}}` for literal braces);
  - `{{$x}}`, which is the literal text `{$x}` - a hole in braces is `{{{$x}}}`.

  Errors too: text a file cannot store - a `\uD83D\uDE00` escape pair in a double-quoted value is
  two lone surrogates to YAML, which UTF-8 cannot write (the fire refuses the row: write the character
  itself).

  A problem inside a multi-line PLAIN (unquoted) value, a folded `>` block, or a value holding a line
  break other than a newline (a `\r` escape, U+2028 ...) is placed on its first line and marked
  *(approximate)*: YAML joins those lines, or the render splits where the document does not, so a
  column there is not a column of the document.
- **Rule and row.** Pick a rule from your `reactions.csv`, and a source row of the table it reads at
  its hook. The rows are what that hook's fire GETS - not the Database folder (later phases re-save
  that). For `after_300` the builder runs the run's own steps, in memory - nothing is saved or
  written:
  - staging itself, over your current source documents, through the run's gate - your finding
    [treatments](guide://treatments) applied (a big project takes a moment; the preview says so while it
    builds, and the editor stays live meanwhile);
  - the `before_300` rules fired dry - every step but writing their files - and their audit rows
    and findings settled into the record, as the run settles them;
  - the hook's earlier `add_rows` rules, spawning as they do in a run.

  The checks then also cover that rule's context:
  - a field its rows do not carry;
  - a loop over a table that does not exist at that hook;
  - a column typo inside a loop;
  - the rule itself: a template of the wrong kind, a hook the run never fires, a target the fire
    refuses for every row (a `:` other than a drive's - a drive is ONE letter A-Z, `C:/`,
    `\\?\C:\`, or one holes complete, `{$_params.drive}:/out`, which the fire judges row by row - or a
    character Windows does not allow in a path, `< > " | ? *` or a control character, the drive's
    place included);
  - project params that do not load (the fire blocks every rule of the hook: `rx_params_unreadable`).

  When staging would HALT the run (a FAIL your treatments do not lift) - or cannot run at all (a
  source document that will not open) - the builder says the run stops before `after_300` fires:
  there is no fire to check or preview. So it does for a FAIL your treatments DOWNGRADE: staging then
  goes on, but the reactions never run on a raw FAIL (as no phase generates from one).

  Another button may fire the same hook over a different Database: the **310 Stage I/O List**
  button fires `after_300` over the I/O List alone - no C&E values, and no `validation_issues` table
  unless a `before_300` rule's record was settled in. Each rule is checked against every such leg too;
  a problem only that leg has reads "on the 310 Stage I/O List leg: ...". The legs stop separately:
  when the full staging stops on a finding only its second pass raises (a duplicate (script_type,
  index)), the 310 leg still fires - and is still checked.
- **Preview.** Shows what ONE fire of the rule would do for that row: the text it would append (and
  where), or the rows it would spawn, or the problem it would report. Nothing is written. When a
  row does not match the rule's condition, the preview says so and still renders (a problem it shows
  then is one the fire never meets - it skips that row). It also says when the document you are
  viewing is NOT the templates.yaml a fire uses, and that rows spawned into a staged table reach the
  saved Database, not generation (later phases re-stage from the documents).
- **Autocomplete** offers what fits at the cursor:
  - `$` offers the rule's columns (in the templates the rule renders), your loop variables,
    `_params` and `_rule`; inside a `where` - or a data function's predicate, `count(signals, $` -
    only that table's columns (all it can see); when the full staging stops, the 310 leg's
    columns (it still fires);
  - `$row.` offers that loop table's columns, and `$_params.` offers your project parameters;
  - `@use` offers template names, `@for $x in` offers table names, `@` offers the directives, and
    functions complete elsewhere.

  Up/Down choose, Enter/Tab accept, Escape closes.

**↻ Reload rules + data** re-reads the rules and rebuilds the hook databases - after editing the
rules, the params, the treatments or the source documents. A build that was still running when you
clicked is discarded, never shown. The Files tab reloads it for you after a run and on a project or
system switch.
