import unittest

from hash_array_mapped_trie import HAMT, hamt


class TestHAMT(unittest.TestCase):
    def test_empty(self):
        h = hamt()
        self.assertEqual(len(h), 0)
        self.assertIsNone(h.get("missing"))
        self.assertEqual(h.get("missing", 42), 42)
        self.assertNotIn("anything", h)
        self.assertEqual(h.to_dict(), {})

    def test_set_get(self):
        h = hamt().set("a", 1).set("b", 2)
        self.assertEqual(h.get("a"), 1)
        self.assertEqual(h.get("b"), 2)
        self.assertEqual(len(h), 2)
        self.assertIn("a", h)
        self.assertIn("b", h)

    def test_get_missing(self):
        h = hamt().set("a", 1)
        self.assertIsNone(h.get("b"))
        self.assertEqual(h.get("b", "def"), "def")

    def test_set_replace(self):
        h = hamt().set("a", 1)
        h2 = h.set("a", 2)
        self.assertEqual(h.get("a"), 1)  # original unchanged
        self.assertEqual(h2.get("a"), 2)
        self.assertEqual(len(h), 1)
        self.assertEqual(len(h2), 1)

    def test_set_same_value_is_identity(self):
        h = hamt().set("a", 1)
        h2 = h.set("a", 1)
        self.assertIs(h, h2)

    def test_persistence(self):
        h0 = hamt()
        h1 = h0.set("a", 1)
        h2 = h1.set("b", 2)
        h3 = h2.set("a", 99)
        self.assertEqual(h0.to_dict(), {})
        self.assertEqual(h1.to_dict(), {"a": 1})
        self.assertEqual(h2.to_dict(), {"a": 1, "b": 2})
        self.assertEqual(h3.to_dict(), {"a": 99, "b": 2})

    def test_remove(self):
        h = hamt().set("a", 1).set("b", 2)
        h2 = h.remove("a")
        self.assertEqual(h2.to_dict(), {"b": 2})
        self.assertEqual(h.to_dict(), {"a": 1, "b": 2})
        self.assertEqual(len(h2), 1)

    def test_remove_missing_raises(self):
        h = hamt().set("a", 1)
        with self.assertRaises(KeyError):
            h.remove("zzz")

    def test_remove_last(self):
        h = hamt().set("a", 1)
        h2 = h.remove("a")
        self.assertEqual(len(h2), 0)
        self.assertEqual(h2.to_dict(), {})

    def test_remove_then_reinsert(self):
        h = hamt().set("a", 1).set("b", 2)
        h2 = h.remove("a")
        h3 = h2.set("a", 100)
        self.assertEqual(h3.to_dict(), {"a": 100, "b": 2})

    def test_hash_collision_distinct_keys(self):
        class Bad:
            __slots__ = ("tag",)
            def __init__(self, tag):
                self.tag = tag
            def __hash__(self):
                return 7
            def __eq__(self, other):
                return isinstance(other, Bad) and self.tag == other.tag

        k1, k2, k3 = Bad("x"), Bad("y"), Bad("z")
        h = hamt().set(k1, 1).set(k2, 2).set(k3, 3)
        self.assertEqual(h.get(k1), 1)
        self.assertEqual(h.get(k2), 2)
        self.assertEqual(h.get(k3), 3)
        self.assertEqual(len(h), 3)

        h2 = h.remove(k2)
        self.assertEqual(h2.get(k1), 1)
        self.assertIsNone(h2.get(k2))
        self.assertEqual(h2.get(k3), 3)
        self.assertEqual(len(h2), 2)

        h3 = h2.set(k2, 22)
        self.assertEqual(h3.get(k2), 22)

    def test_full_hash_collision_collapse_to_single(self):
        class K:
            __slots__ = ("tag",)
            def __init__(self, tag):
                self.tag = tag
            def __hash__(self):
                return 7
            def __eq__(self, other):
                return isinstance(other, K) and self.tag == other.tag

        k1, k2 = K("a"), K("b")
        h = hamt().set(k1, 1).set(k2, 2)
        self.assertEqual(h.get(k1), 1)
        h2 = h.remove(k2)
        self.assertEqual(h2.get(k1), 1)
        self.assertEqual(len(h2), 1)

    def test_collision_with_different_hash_inserted_after(self):
        class K:
            __slots__ = ("tag",)
            def __init__(self, tag):
                self.tag = tag
            def __hash__(self):
                return 7
            def __eq__(self, other):
                return isinstance(other, K) and self.tag == other.tag

        k1, k2 = K("a"), K("b")
        h = hamt().set(k1, 1).set(k2, 2)
        h2 = h.set("normal", 99)
        self.assertEqual(h2.get(k1), 1)
        self.assertEqual(h2.get(k2), 2)
        self.assertEqual(h2.get("normal"), 99)

    def test_large_random(self):
        import random
        random.seed(12345)
        pairs = [(f"k{i}", i) for i in range(500)]
        random.shuffle(pairs)
        h = hamt()
        for k, v in pairs:
            h = h.set(k, v)
        for k, v in pairs:
            self.assertEqual(h.get(k), v, f"failed for {k}")
        self.assertEqual(len(h), 500)
        for k, _ in pairs[:250]:
            h = h.remove(k)
        for k, _ in pairs[:250]:
            self.assertNotIn(k, h)
        for k, v in pairs[250:]:
            self.assertEqual(h.get(k), v)
        self.assertEqual(len(h), 250)

    def test_deep_chain(self):
        h = hamt()
        keys = [f"deep-key-{i:04d}" for i in range(2000)]
        for k in keys:
            h = h.set(k, k.upper())
        for k in keys:
            self.assertEqual(h.get(k), k.upper())
        self.assertEqual(len(h), 2000)

    def test_int_keys(self):
        h = hamt()
        for i in range(100):
            h = h.set(i, i * i)
        for i in range(100):
            self.assertEqual(h.get(i), i * i)
        self.assertEqual(len(h), 100)

    def test_none_value(self):
        h = hamt().set("a", None)
        self.assertEqual(h.get("a"), None)
        self.assertIn("a", h)

    def test_none_key(self):
        h = hamt().set(None, 42)
        self.assertEqual(h.get(None), 42)
        h2 = h.set(None, 99)
        self.assertEqual(h2.get(None), 99)

    def test_iteration(self):
        h = hamt([(i, i * 10) for i in range(20)])
        keys = sorted(h.keys())
        self.assertEqual(keys, list(range(20)))
        values = sorted(h.values())
        self.assertEqual(values, [i * 10 for i in range(20)])
        items = sorted(h.items())
        self.assertEqual(items, [(i, i * 10) for i in range(20)])

    def test_eq(self):
        a = hamt([(i, i) for i in range(10)])
        b = hamt([(i, i) for i in range(10)])
        self.assertEqual(a, b)
        c = a.set(0, 999)
        self.assertNotEqual(a, c)

    def test_from_iterable(self):
        h = hamt([("a", 1), ("b", 2), ("c", 3)])
        self.assertEqual(h.to_dict(), {"a": 1, "b": 2, "c": 3})
        self.assertEqual(h.get("b"), 2)

    def test_repr(self):
        h = hamt().set("a", 1)
        s = repr(h)
        self.assertIn("'a'", s)
        self.assertIn("1", s)

    def test_getitem_raises(self):
        h = hamt().set("a", 1)
        self.assertEqual(h["a"], 1)
        with self.assertRaises(KeyError):
            h["missing"]

    def test_custom_hash_fn(self):
        calls = {"n": 0}
        def myhash(k):
            calls["n"] += 1
            return hash(k) & 0xFF  # small hash space forces trie depth
        h = hamt(hash_fn=myhash)
        for i in range(50):
            h = h.set(i, i)
        self.assertGreater(calls["n"], 0)
        for i in range(50):
            self.assertEqual(h.get(i), i)

    def test_identity_eq_fn(self):
        class O:
            __slots__ = ("tag",)
            def __init__(self, tag):
                self.tag = tag
        a, b = O("x"), O("x")
        # Default __eq__ on instances of a class without __eq__ is identity.
        self.assertNotEqual(a, b)
        h = hamt(eq_fn=lambda x, y: x is y).set(a, 1)
        self.assertEqual(h.get(a), 1)
        self.assertNotIn(b, h)
        h2 = h.set(b, 2)
        self.assertEqual(h2.get(a), 1)
        self.assertEqual(h2.get(b), 2)
        self.assertEqual(len(h2), 2)

    def test_collisions_with_custom_hash(self):
        h = hamt(hash_fn=lambda k: 5)
        h = h.set("a", 1).set("b", 2).set("c", 3)
        self.assertEqual(h.get("a"), 1)
        self.assertEqual(h.get("b"), 2)
        self.assertEqual(h.get("c"), 3)
        self.assertEqual(len(h), 3)
        h2 = h.remove("b")
        self.assertEqual(h2.get("a"), 1)
        self.assertIsNone(h2.get("b"))
        self.assertEqual(h2.get("c"), 3)
        self.assertEqual(len(h2), 2)

    def test_churn(self):
        h = hamt()
        for i in range(300):
            h = h.set(i, i)
        for i in range(0, 300, 2):
            h = h.remove(i)
        for i in range(300):
            if i % 2 == 0:
                self.assertNotIn(i, h)
            else:
                self.assertEqual(h.get(i), i)
        self.assertEqual(len(h), 150)

    def test_remove_all(self):
        h = hamt()
        for i in range(100):
            h = h.set(i, i)
        for i in range(100):
            h = h.remove(i)
        self.assertEqual(len(h), 0)
        self.assertEqual(h.to_dict(), {})


if __name__ == "__main__":
    unittest.main()
