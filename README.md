# hash_array_mapped_trie

A persistent (immutable) associative array for Python, implemented as a hash
array mapped trie with 32-way branching. `set` and `remove` return new HAMTs
that share structure with the original; the original is never mutated.

```python
from hash_array_mapped_trie import HAMT, hamt

h = hamt().set("one", 1).set("two", 2)
print(h.get("one"))        # 1
print(len(h))             # 2

h2 = h.remove("one")
print(h.get("one"))       # 1  — original unchanged
print(h2.get("one"))      # None
print(h2.to_dict())       # {'two': 2}
```

The exported names are `HAMT` (the class) and `hamt` (a builder that accepts
an iterable of `(key, value)` pairs, plus optional `hash_fn` / `eq_fn`
keyword arguments). On a `HAMT` instance the public surface is:

- `get(key, default=None)`
- `set(key, value)` -> new `HAMT`
- `remove(key)` -> new `HAMT`; raises `KeyError` if absent
- `__getitem__`, `__contains__`, `__iter__` (over keys), `__len__`, `__eq__`,
  `__repr__`
- `keys()`, `values()`, `items()`, `to_dict()`

## Why

Python's built-in `dict` is mutable; copying it for every revision is
O(n). This library exists for the narrow case where you want dict-like
semantics and need every "update" to be a cheap, shared-structure snapshot —
undo stacks, functional state, concurrent readers with an evolving value.

The trade-off: lookups and updates carry the cost of walking a trie and
allocating a few nodes per write, and per-node memory overhead is higher than
a flat `dict`. For a hot inner loop with a small map, just use a `dict`.

## Design choices worth stating plainly

- **Branching factor 32, dense children list.** Each internal node holds a
  length-32 list. The classic HAMT uses a bitmap plus a compacted array; we
  skip that. It costs memory per node but the code stays short and obviously
  correct, and in Python the bitmap arithmetic rarely wins the constant
  factor fight anyway.
- **Hash collisions collapse into a bucket.** Two keys with identical full
  hashes cannot be separated further down the trie. We collect them into a
  `CollisionNode` list. Without this the trie would loop forever; with it,
  any hashable key set has a finite, well-defined representation.
- **`set` with an identical value returns the same object.** This lets callers
  treat `set` as idempotent for free. (Two keys that compare unequal but hash
  equal still create a new node.)
- **Custom `hash_fn` / `eq_fn`.** Pass these to `hamt(...)` if you want
  identity-based keys, hash-space reduction for testing, or keys whose
  `__hash__`/`__eq__` you don't control. Once chosen they are fixed for the
  lifetime of that HAMT and its descendants.

## Edge you will hit

`hamt().set(k1, v).set(k2, v2)` where `k1` and `k2` are unequal but
`hash(k1) == hash(k2)` is handled by the collision bucket. It works. But:
if you supply a `hash_fn` that maps everything to a single integer, every
key ends up in one bucket and the structure degenerates into a list —
correct, but no longer trie-shaped. This is by design; sanity-check your
hash function if it matters.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

