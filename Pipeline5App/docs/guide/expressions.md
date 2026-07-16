# Expressions (the ƒx language)

One expression engine backs every config surface - script-type rules, DB `for_each`, diagnosis and
interface templates, validation predicates. The **ƒx** toolbar button opens the Expression Builder:
live highlighting, error squiggles, autocomplete, and a preview evaluated against a real database row.

## Field references

- `$name` reads a field of the current row (`""` when missing).
- `$obj.key` drills into a JSON-object cell, e.g. `$type.type_id`.
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

The full syntax reference lives at the top of
[pipeline5/core/expr/\_\_init\_\_.py](src://pipeline5/core/expr/__init__.py).
