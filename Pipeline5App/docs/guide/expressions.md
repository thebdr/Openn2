# Expressions (the ƒx language)

One expression engine backs every config surface - script-type rules, DB `for_each`, diagnosis and
interface templates, validation predicates. The **ƒx** toolbar button opens the Expression Builder:
live highlighting, error squiggles, autocomplete, and a preview evaluated against a real database row.

## Field references

- `$name` reads a field of the current row (`""` when missing - but see *Strict templates* below).
- `$obj.key` drills into a JSON-object cell, e.g. `$type.type_id` (`""` when the key is absent, or
  when the cell is empty - `type` is empty on node rows).
- Barewords are only function names, table names, and `and` / `or` / `not` / `in`.

## Operators (no arithmetic - by design)

```
$f ~ /regex/       case-insensitive regex search
$f = "text"        string equality        $f != "text"
$f in ["a","b"]    membership
$f > 5             numeric compare (also >= < <=)
P and Q or not R   boolean composition, ( ) groups
```

## Functions

- Strings: `clean($f)` `strip($f)` `concat(a,b,…)` `join(sep,a,…)`
- Tests: `present($f)` `blank($f)` `numeric(x)` `isdigit(x)` `startswith($f,"p")` `len(x)`
- Control: `if(cond, then, else)` `coalesce(a,b,…)` `let(a := e1; body)`
- Extraction: `extract($f, /re/ [, slice])` - group(1) if the regex captures, else the whole match;
  the optional slice (`-1:` `:3` `1:3` `2`) then applies.
- Data (over the SSOT tables): `where(table, pred)` `first(table, pred)`
  `lookup(table, key_col, key_val, val_col)` `unique(col, table)` `count(table[, pred])`
  `node_of($bit, table)`

## Render templates

A template is literal text with `{expr}` holes: `{$n:03d}` formats with a Python spec (numeric
coercion; a blank value stays blank). Text without holes is copied verbatim - a literal sentinel like
`<input required>` is never parsed.

## Strict templates

The pipeline's own templates - DB member templates, interface and diagnosis SCL lines, and the
chain-reaction templates - render **strict**: a missing top-level `$field` is an error (a phase FAIL,
or an `rx_bad_template` reaction finding), never a silent blank - a data function's predicate
(`count(signals, $script_type = "PEC")`) reads the table's rows, so its `$col` is not a field of the
template, and neither is a `let` name. Sub-keys stay optional: guard them
with `present(...)` / `coalesce(...)`. In a chain-reaction `@for $row in <table>` loop, `$row.column`
must name a real column of that table. Predicates (conditions, `where`, `@if`) stay lenient: a
misspelled name there simply reads blank. A malformed `/regex/` is always reported as an error.

In the chain-reaction templates (text lines, row-template values and file targets) a **literal
brace is written doubled**: `{{ S7_Optimized_Access := 'TRUE' }}` renders the TIA pragma
`{ S7_Optimized_Access := 'TRUE' }`, a hole still works inside it (`{{ Name := '{$name}' }}`), and
`{{{$x}}}` puts a brace around a hole. A single brace that opens or closes no hole is an error, and
so is a brace inside a hole (write a regex quantifier out: `/\d\d/`, not `/\d{2}/`). The other
templates keep copying a stray brace verbatim.

The full syntax reference lives at the top of
[pipeline5/language/expr/\_\_init\_\_.py](src://pipeline5/language/expr/__init__.py).
