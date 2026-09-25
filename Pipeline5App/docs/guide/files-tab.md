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

## The shipped system configuration (read-only)

The **System configuration (shipped, read-only)** section lists the configuration that ships with
the active system (the `${system_config}` placeholder). Its files open **read-only**. To change one for
your project, press **Create project copy**. The copy lands in your project's per-system
configuration folder (`<project>/config_project/systems/<system>/`, same relative path), and from
then on it **overrides** the shipped file for that project. Once a copy exists the button reads
**Open project copy**. With no project open there is nowhere to put a copy, so the button is
disabled. A project that carries its own `files_tab` block needs this section added to show it.

## Template mode: chain-reaction templates

A `chain_reactions/templates.yaml` opens in the **template mode**. It is the editor for the
chain-reaction templates (see *Strict templates* in [Expressions](guide://expressions)).

- **Two-layer highlighting.** The YAML structure is highlighted as YAML. Inside a text template, the
  target language (SCL) sits underneath the template constructs:
  - `@use` / `@for` / `@if` / `@else` / `@end` and the `@use`'d template names;
  - `{holes}` with their expression tokens and format specs;
  - `{{ }}` literal braces.
- **Live problems.** Errors get a red squiggle and warnings an amber one. The list under the text
  shows each problem; click one to jump to it. The problems are what a chain reaction would report
  when it fires, found WITHOUT firing and in **every** branch, including an `@else` no row has taken
  yet:
  - a directive typo, an unclosed block, an unknown `@use`;
  - a hole that does not compile, a lone brace.

  Warnings flag renders that succeed but probably are not what you meant:
  - a `where` that reads its own loop variable;
  - an empty hole `{}` (it renders nothing - write `{{}}` for literal braces);
  - `{{$x}}`, which is the literal text `{$x}` - a hole in braces is `{{{$x}}}`.
- **Rule and row.** Pick a rule from your `reactions.csv`, and a source row of the table it reads at
  its hook. The checks then also cover that rule's context:
  - a field its rows do not carry;
  - a loop over a table that does not exist at that hook;
  - a column typo inside a loop;
  - the rule itself (a template of the wrong kind, a hook the run never fires).
- **Preview.** Shows what ONE fire of the rule would do for that row: the text it would append (and
  where), or the rows it would spawn, or the problem it would report. Nothing is written. When a
  row does not match the rule's condition, the preview says so and still renders.
- **Autocomplete** offers what fits at the cursor:
  - `$` offers the rule's columns, your loop variables, `_params` and `_rule`;
  - `$row.` offers that loop table's columns, and `$_params.` offers your project parameters;
  - `@use` offers template names, `@for $x in` offers table names, `@` offers the directives, and
    functions complete elsewhere.

  Up/Down choose, Enter/Tab accept, Escape closes.

**↻ Reload rules + data** re-reads the rules and the hook databases, for example after a phase run.
