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

- `.csv` opens as a read-only grid; `.xlsx` adds a sheet picker. Grid columns size themselves to the
  data - **drag a header separator** to resize one, **double-click the separator** to auto-fit it.
- **Text-based files edit in place**: change the text, **Save** (or `Ctrl+S`) writes atomically with
  the file's original BOM/newline style; **Revert** re-reads. Switching files with unsaved changes
  asks first. A file over the editor cap opens read-only - use *Open externally*.
- `.yaml` / `.json` add **syntax highlighting** (live while typing), plus a **Text / Object explorer**
  toggle:
  - the Object explorer shows the document as a key/value tree,
  - double-click a value to edit it in place (Enter commits, Escape cancels),
  - keys containing `path` get a `…` file picker; `dir`/`folder`/`root` keys get a folder picker,
  - **Save** writes losslessly - comments, ordering, and quoting survive.
- Anything else shows the path strip with **Open externally** / **Open folder**.

Editing a pipeline-produced file is possible, but remember the next phase run regenerates it -
durable changes belong in the source documents or the config CSVs.
