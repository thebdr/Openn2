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
  - an empty hole `{}` (it renders nothing - write `{{}}` for literal braces);
  - `{{$x}}`, which is the literal text `{$x}` - a hole in braces is `{{{$x}}}`.
- **Rule and row.** Pick a rule from your `reactions.csv`, and a source row of the table it reads at
  its hook. The rows are what that hook's fire GETS - not the Database folder (later phases re-save
  that): for `after_300`, staging itself runs in memory over your current source documents (nothing
  is saved - a big project takes a moment; the preview says so while it builds), then an earlier
  `before_300` rule's record is settled in and the hook's earlier `add_rows` rules spawn - as a run
  would. The checks then also cover that rule's context:
  - a field its rows do not carry;
  - a loop over a table that does not exist at that hook;
  - a column typo inside a loop;
  - the rule itself (a template of the wrong kind, a hook the run never fires, a target with a `:`).
- **Preview.** Shows what ONE fire of the rule would do for that row: the text it would append (and
  where), or the rows it would spawn, or the problem it would report. Nothing is written. When a
  row does not match the rule's condition, the preview says so and still renders (a problem it shows
  then is one the fire never meets - it skips that row). It also says when the document you are
  viewing is NOT the templates.yaml a fire uses, and that rows spawned into a staged table reach the
  saved Database, not generation (later phases re-stage from the documents).
- **Autocomplete** offers what fits at the cursor:
  - `$` offers the rule's columns (in the templates the rule renders), your loop variables,
    `_params` and `_rule`; inside a `where`, only the loop table's columns (all it can see);
  - `$row.` offers that loop table's columns, and `$_params.` offers your project parameters;
  - `@use` offers template names, `@for $x in` offers table names, `@` offers the directives, and
    functions complete elsewhere.

  Up/Down choose, Enter/Tab accept, Escape closes.

**↻ Reload rules + data** re-reads the rules and rebuilds the hook databases - after editing the
rules or the source documents.
