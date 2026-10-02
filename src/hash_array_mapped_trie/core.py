from __future__ import annotations

from typing import Iterator, Tuple


_BITS = 5
_MASK = (1 << _BITS) - 1  # 0b11111 -> 31
BRANCH = 1 << _BITS       # 32


def _default_hash(key: object) -> int:
    return hash(key)


def _default_eq(a: object, b: object) -> bool:
    return a == b


class _EmptyNode:
    """Sentinel empty subtree. Singleton; interned via the module-level `_EMPTY`."""

    __slots__ = ()

    def get(self, key, hash_value, shift, eq):
        return _MISSING

    def set(self, key, value, hash_value, shift, eq):
        return _LeafNode(key, value, hash_value)

    def remove(self, key, hash_value, shift, eq):
        return self, False

    def entries(self):
        yield from ()


_EMPTY = _EmptyNode()
_MISSING = object()


class _LeafNode:
    """A single key/value pair, tagged with its (precomputed) hash."""

    __slots__ = ("key", "value", "hash")

    def __init__(self, key, value, hash_value):
        self.key = key
        self.value = value
        self.hash = hash_value

    def get(self, key, hash_value, shift, eq):
        if hash_value == self.hash and eq(self.key, key):
            return self.value
        return _MISSING

    def set(self, key, value, hash_value, shift, eq):
        if hash_value == self.hash and eq(self.key, key):
            # Same key -> replace value.
            if eq(value, self.value):
                return self
            return _LeafNode(key, value, hash_value)
        if hash_value == self.hash:
            # Full hash collision on two distinct keys -> collapse into a
            # CollisionNode rather than spinning off identical shift slices.
            return _CollisionNode(hash_value, [(self.key, self.value), (key, value)])
        return _split(_LeafNode(key, value, hash_value), self, shift)

    def remove(self, key, hash_value, shift, eq):
        if hash_value == self.hash and eq(self.key, key):
            return _EMPTY, True
        return self, False

    def entries(self):
        yield (self.key, self.value)


class _CollisionNode:
    """Bucket for keys whose full hashes are identical but which are unequal.

    Hashing being finite, there is no other correct option: descending the
    trie any further would keep selecting the same child index forever.
    """

    __slots__ = ("hash", "pairs")

    def __init__(self, hash_value, pairs):
        self.hash = hash_value
        self.pairs = pairs

    def _index(self, key, eq):
        for i, (k, _) in enumerate(self.pairs):
            if eq(k, key):
                return i
        return -1

    def get(self, key, hash_value, shift, eq):
        if hash_value != self.hash:
            return _MISSING
        i = self._index(key, eq)
        if i < 0:
            return _MISSING
        return self.pairs[i][1]

    def set(self, key, value, hash_value, shift, eq):
        if hash_value != self.hash:
            # New key hashes differently; split it out into the trie proper.
            branch = _BranchNode()
            self_idx = (self.hash >> shift) & _MASK
            branch.children[self_idx] = self
            return branch.set(key, value, hash_value, shift, eq)
        i = self._index(key, eq)
        if i < 0:
            new_pairs = self.pairs + [(key, value)]
            return _CollisionNode(self.hash, new_pairs)
        if eq(value, self.pairs[i][1]):
            return self
        new_pairs = list(self.pairs)
        new_pairs[i] = (key, value)
        return _CollisionNode(self.hash, new_pairs)

    def remove(self, key, hash_value, shift, eq):
        if hash_value != self.hash:
            return self, False
        i = self._index(key, eq)
        if i < 0:
            return self, False
        remaining = self.pairs[:i] + self.pairs[i + 1:]
        if len(remaining) == 0:
            return _EMPTY, True
        if len(remaining) == 1:
            k, v = remaining[0]
            return _LeafNode(k, v, self.hash), True
        return _CollisionNode(self.hash, remaining), True

    def entries(self):
        yield from self.pairs


class _BranchNode:
    """Internal trie node. `children` is a dense list of length 32.

    We deliberately avoid a bitmap + sparse array. It costs more memory per
    node but keeps the code short, obviously correct, and fast enough in
    Python — the constant factor of bit-twiddling rarely beats the cost of
    Python-level arithmetic for small-to-medium maps.
    """

    __slots__ = ("children",)

    def __init__(self):
        self.children = [_EMPTY] * BRANCH

    def _idx(self, hash_value, shift):
        return (hash_value >> shift) & _MASK

    def get(self, key, hash_value, shift, eq):
        idx = self._idx(hash_value, shift)
        child = self.children[idx]
        return child.get(key, hash_value, shift + _BITS, eq)

    def set(self, key, value, hash_value, shift, eq):
        idx = self._idx(hash_value, shift)
        child = self.children[idx]
        new_child = child.set(key, value, hash_value, shift + _BITS, eq)
        if new_child is child:
            return self
        node = _BranchNode()
        node.children = list(self.children)
        node.children[idx] = new_child
        return node

    def remove(self, key, hash_value, shift, eq):
        idx = self._idx(hash_value, shift)
        child = self.children[idx]
        new_child, removed = child.remove(key, hash_value, shift + _BITS, eq)
        if not removed:
            return self, False
        # Collapse a branch with a single remaining leaf child into that leaf.
        # This keeps lookups shallow and ensures equivalent maps have the same
        # trie shape regardless of insertion order.
        non_empty = [c for c in self.children if not isinstance(c, _EmptyNode)]
        if len(non_empty) == 1 and isinstance(new_child, _LeafNode):
            return new_child, True
        node = _BranchNode()
        node.children = list(self.children)
        if isinstance(new_child, _EmptyNode):
            node.children[idx] = _EMPTY
        else:
            node.children[idx] = new_child
        return node, True

    def entries(self):
        for child in self.children:
            yield from child.entries()


class _Node:
    __slots__ = ()

    def get(self, key, hash_value, shift, eq):
        raise NotImplementedError

    def set(self, key, value, hash_value, shift, eq):
        raise NotImplementedError

    def remove(self, key, hash_value, shift, eq):
        raise NotImplementedError

    def entries(self):
        raise NotImplementedError


def _split(a, b, shift):
    """Build a branch holding two leaves, distributing them by hash slice."""
    node = _BranchNode()
    ia = (a.hash >> shift) & _MASK
    ib = (b.hash >> shift) & _MASK
    if shift >= 64 or ia != ib:
        node.children[ia] = a
        node.children[ib] = b
        return node
    # Same index at this level -> nest. Guarded against infinite loop by the
    # hash-collision shortcut in _LeafNode.set, but kept for safety.
    inner = _split(a, b, shift + _BITS)
    node.children[ia] = inner
    return node


class HAMT:
    """Persistent associative array backed by a hash array mapped trie.

    All mutating operations return a new HAMT; the receiver is never changed.
    Lookup, insertion and removal are O(log32 n) expected — i.e. effectively
    constant for any realistic map size.

    Parameters
    ----------
    root : internal
        Root node of the trie. The public constructor is `hamt()`; passing a
        root directly is for internal use by the persistent operations.
    hash_fn : callable, optional
        Hash function. Defaults to the built-in `hash`.
    eq_fn : callable, optional
        Equality predicate. Defaults to `operator.eq` (i.e. `==`).
    """

    __slots__ = ("_root", "_hash_fn", "_eq_fn", "_size")

    def __init__(self, root=_EMPTY, hash_fn=None, eq_fn=None, size=0):
        self._root = root
        self._hash_fn = _default_hash if hash_fn is None else hash_fn
        self._eq_fn = _default_eq if eq_fn is None else eq_fn
        self._size = size

    # --- primitive ops -------------------------------------------------

    def _h(self, key):
        return self._hash_fn(key)

    def get(self, key, default=None):
        """Return value for `key`, or `default` if absent."""
        v = self._root.get(key, self._h(key), 0, self._eq_fn)
        if v is _MISSING:
            return default
        return v

    def set(self, key, value):
        """Return a new HAMT with `key` mapped to `value`."""
        h = self._h(key)
        new_root = self._root.set(key, value, h, 0, self._eq_fn)
        if new_root is self._root:
            return self
        if self._root.get(key, h, 0, self._eq_fn) is _MISSING:
            new_size = self._size + 1
        else:
            new_size = self._size
        return HAMT(new_root, self._hash_fn, self._eq_fn, new_size)

    def remove(self, key):
        """Return a new HAMT without `key`. Raises `KeyError` if absent."""
        h = self._h(key)
        new_root, removed = self._root.remove(key, h, 0, self._eq_fn)
        if not removed:
            raise KeyError(key)
        return HAMT(new_root, self._hash_fn, self._eq_fn, self._size - 1)

    # --- convenience --------------------------------------------------

    def __getitem__(self, key):
        v = self._root.get(key, self._h(key), 0, self._eq_fn)
        if v is _MISSING:
            raise KeyError(key)
        return v

    def __contains__(self, key):
        return self._root.get(key, self._h(key), 0, self._eq_fn) is not _MISSING

    def __iter__(self):
        return (k for k, _ in self._root.entries())

    def __len__(self):
        return self._size

    def __eq__(self, other):
        if not isinstance(other, HAMT):
            return NotImplemented
        if self._size != other._size:
            return False
        for k, v in self._root.entries():
            ov = other._root.get(k, other._h(k), 0, other._eq_fn)
            if ov is _MISSING:
                return False
            if not self._eq_fn(v, ov):
                return False
        return True

    def __repr__(self):
        body = ", ".join(f"{k!r}: {v!r}" for k, v in self._root.entries())
        return f"hamt({{{body}}})"

    def keys(self):
        return list(k for k, _ in self._root.entries())

    def values(self):
        return list(v for _, v in self._root.entries())

    def items(self):
        return list(self._root.entries())

    def to_dict(self):
        return dict(self._root.entries())


def hamt(initial=None, *, hash_fn=None, eq_fn=None):
    """Build a HAMT from an iterable of ``(key, value)`` pairs.

    `hash_fn` and `eq_fn` override the hash and equality functions. Use this
    when keys are objects whose `__hash__`/`__eq__` you do not control, or to
    build a HAMT keyed by identity rather than equality.
    """
    h = HAMT(_EMPTY, hash_fn=hash_fn, eq_fn=eq_fn, size=0)
    if initial is None:
        return h
    for k, v in initial:
        h = h.set(k, v)
    return h
