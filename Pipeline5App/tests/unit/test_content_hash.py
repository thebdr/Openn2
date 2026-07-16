"""The universal content-hash key (core.keys.uid)."""
from _harness import run, eq, ok
from pipeline5.truth.content_hash import uid


def test_uid_is_stable_and_short():
    a = uid("300", "v_dup_ip", "NS50!C12", "duplicate IP")
    eq(a, uid("300", "v_dup_ip", "NS50!C12", "duplicate IP"), "same parts -> same uid")
    eq(len(a), 10, "10 hex chars")
    ok(all(c in "0123456789abcdef" for c in a), "lowercase hex")


def test_uid_is_content_sensitive():
    ok(uid("a", "b") != uid("a", "c"), "a changed part changes the uid")
    ok(uid("a", "b") != uid("a", "b", "x"), "an added part changes the uid")
    ok(uid("a", "b") != uid("ab",), "the '|' separator prevents part-boundary collisions")


def test_uid_normalizes_none_and_types():
    eq(uid(None, 1), uid("", "1"), "None -> '' and ints stringify")
    eq(uid(True, 2.0), uid("True", "2.0"), "any type is stringified consistently")


if __name__ == "__main__":
    import sys
    sys.exit(run("keys", [
        ("uid_is_stable_and_short", test_uid_is_stable_and_short),
        ("uid_is_content_sensitive", test_uid_is_content_sensitive),
        ("uid_normalizes_none_and_types", test_uid_normalizes_none_and_types),
    ]))
