"""
Approximate, mergeable data structures for distributed mining.
==============================================================

Every structure here satisfies three properties that make it usable as the
``zeroValue`` of a Spark ``treeAggregate``:

  1. **Mergeable**  – ``a.merge(b)`` is associative and commutative, so partial
     sketches built independently on every partition combine into exactly the
     sketch that a single-machine pass would have produced.
  2. **Deterministic** – all hashing goes through :func:`hash64`, a fixed
     polynomial hash over 64-bit integers.  Python's built-in ``hash()`` is
     salted per interpreter (``PYTHONHASHSEED``) and therefore produces
     *different* buckets on every executor, which silently corrupts any
     hash-partitioned sketch.  We never use it.
  3. **Bounded memory** – size is a function of the accuracy parameters only,
     never of the number of distinct keys.

Structures
----------
CountMinSketch   frequency estimation, one-sided error (never underestimates)
BloomFilter      set membership, one-sided error (never a false negative)
HyperLogLog      distinct-count estimation, ~1.04/sqrt(m) relative error

References
----------
Cormode & Muthukrishnan (2005), *An improved data stream summary: the
count-min sketch and its applications*.
Bloom (1970), *Space/time trade-offs in hash coding with allowable errors*.
Flajolet et al. (2007), *HyperLogLog: the analysis of a near-optimal
cardinality estimation algorithm*.
"""

from __future__ import annotations

import math
from array import array

try:                                    # numpy makes merges ~100x faster but is
    import numpy as _np                 # never required for correctness
except Exception:                       # pragma: no cover
    _np = None


# ─────────────────────────────────────────────────────────────────────────────
#  Deterministic hashing
# ─────────────────────────────────────────────────────────────────────────────
#  Mersenne prime 2^61 - 1.  Polynomial hashing modulo a Mersenne prime is the
#  standard construction for a (near) universal hash family and is fast enough
#  to run on hundreds of millions of n-grams.
_MERSENNE = (1 << 61) - 1
_BASE = 1_000_003


def hash64(key) -> int:
    """Deterministic 61-bit hash of an int, a str, or a tuple/list of either.

    Unlike ``hash()`` this is stable across processes, machines and Python
    versions, which is what lets partial sketches built on different executors
    be merged.
    """
    h = 0
    if isinstance(key, (tuple, list)):
        for part in key:
            h = (h * _BASE + _as_int(part) + 0x9E3779B9) % _MERSENNE
    else:
        h = _as_int(key) % _MERSENNE
    # Final avalanche so that low bits are well mixed (we take `% width`).
    h ^= (h >> 31)
    h = (h * 0xFF51AFD7ED558CCD) % _MERSENNE
    h ^= (h >> 29)
    return h


def _as_int(part) -> int:
    if isinstance(part, int):
        return part
    if isinstance(part, str):
        acc = 0
        for ch in part:
            acc = (acc * 131 + ord(ch)) % _MERSENNE
        return acc
    return _as_int(str(part))


def _pair(h: int, i: int, modulus: int) -> int:
    """Kirsch-Mitzenmacher double hashing: derive the i-th index from one hash.

    Using ``h1 + i*h2`` instead of i independent hash functions is provably as
    good asymptotically and costs one hash instead of k.
    """
    h1 = h & 0xFFFFFFFF
    h2 = (h >> 32) | 1              # force odd so the stride is coprime with 2^n
    return (h1 + i * h2) % modulus


# ─────────────────────────────────────────────────────────────────────────────
#  Count-Min Sketch
# ─────────────────────────────────────────────────────────────────────────────
class CountMinSketch:
    """Frequency table in sub-linear space.

    Guarantee: for every key ``x``, with probability ``1 - delta``

        true(x)  <=  estimate(x)  <=  true(x) + eps * N

    where ``N`` is the total mass added.  The error is **one-sided**: the sketch
    never underestimates, so filtering on ``estimate(x) >= t`` produces **no
    false negatives** -- every genuinely frequent key survives.  That is the
    property that makes it safe as a pre-filter.

    Sizing follows the standard bounds ``w = ceil(e/eps)``, ``d = ceil(ln(1/delta))``.
    """

    __slots__ = ("width", "depth", "table", "total", "_np")

    def __init__(self, eps: float = 1e-4, delta: float = 1e-3,
                 width: int | None = None, depth: int | None = None):
        self.width = int(width if width else math.ceil(math.e / eps))
        self.depth = int(depth if depth else math.ceil(math.log(1.0 / delta)))
        self._np = _np is not None
        if self._np:
            self.table = _np.zeros((self.depth, self.width), dtype=_np.int64)
        else:
            self.table = [array("l", [0]) * self.width for _ in range(self.depth)]
        self.total = 0

    # -- construction ------------------------------------------------------
    @classmethod
    def for_budget(cls, expected_mass: int, min_support: int,
                   max_memory_mb: float = 32.0, depth: int = 5) -> "CountMinSketch":
        """Size the sketch to a fixed memory budget, then report what that buys.

        The textbook sizing ``w = ceil(e/eps)`` runs the wrong way round for a
        Spark job: every partition builds its own sketch, so a "just make eps
        tiny" choice quietly allocates hundreds of megabytes per task and the
        executors die.  Here the memory budget is the fixed input and the error
        is the derived output.

        The error that matters is the additive one, ``eps * N``, expressed as a
        fraction of ``min_support``: it is the amount by which an infrequent
        key could be over-counted, and therefore how many extra candidates slip
        past the filter.  Since the error is one-sided this can never *lose* a
        frequent key -- a looser sketch only means more false positives for the
        exact second pass to remove.  :meth:`error_report` prints the trade.
        """
        max_cells = int(max_memory_mb * 1024 * 1024 / 8 / depth)
        ideal_eps = max(1e-9, (0.1 * min_support) / max(expected_mass, 1))
        width = min(max_cells, int(math.ceil(math.e / ideal_eps)))
        return cls(width=max(1024, width), depth=depth)

    def error_report(self, min_support: int) -> dict:
        """What this geometry costs and what accuracy it delivers."""
        eps = math.e / self.width
        additive = eps * max(self.total, 1)
        return {
            "geometry": f"{self.depth} x {self.width}",
            "memory_mb": round(self.memory_bytes() / 1024 / 1024, 2),
            "epsilon": float(f"{eps:.3g}"),
            "delta": float(f"{math.exp(-self.depth):.3g}"),
            "total_mass": self.total,
            "additive_error_estimate": int(additive),
            "additive_error_pct_of_support": round(100.0 * additive / max(min_support, 1), 3),
        }

    def memory_bytes(self) -> int:
        return self.width * self.depth * 8

    # -- operations --------------------------------------------------------
    def add(self, key, count: int = 1) -> None:
        h = hash64(key)
        w = self.width
        if self._np:
            t = self.table
            for i in range(self.depth):
                t[i, _pair(h, i, w)] += count
        else:
            for i in range(self.depth):
                self.table[i][_pair(h, i, w)] += count
        self.total += count

    def add_hashed(self, h: int, count: int = 1) -> None:
        """Add a key whose :func:`hash64` was already computed (hot loops)."""
        w = self.width
        if self._np:
            t = self.table
            for i in range(self.depth):
                t[i, _pair(h, i, w)] += count
        else:
            for i in range(self.depth):
                self.table[i][_pair(h, i, w)] += count
        self.total += count

    def estimate(self, key) -> int:
        return self.estimate_hashed(hash64(key))

    def estimate_hashed(self, h: int) -> int:
        w = self.width
        if self._np:
            t = self.table
            return int(min(t[i, _pair(h, i, w)] for i in range(self.depth)))
        return min(self.table[i][_pair(h, i, w)] for i in range(self.depth))

    def merge(self, other: "CountMinSketch") -> "CountMinSketch":
        if (self.width, self.depth) != (other.width, other.depth):
            raise ValueError("cannot merge sketches with different geometry")
        if self._np and other._np:
            self.table += other.table
        else:
            for i in range(self.depth):
                row, orow = self.table[i], other.table[i]
                for j in range(self.width):
                    row[j] += orow[j]
        self.total += other.total
        return self

    # Spark ships the object by pickle; numpy arrays pickle fine.
    def __getstate__(self):
        tab = self.table.tolist() if self._np else [list(r) for r in self.table]
        return (self.width, self.depth, tab, self.total)

    def __setstate__(self, state):
        self.width, self.depth, tab, self.total = state
        self._np = _np is not None
        if self._np:
            self.table = _np.asarray(tab, dtype=_np.int64)
        else:
            self.table = [array("l", row) for row in tab]

    def __repr__(self):
        return (f"CountMinSketch(w={self.width}, d={self.depth}, "
                f"{self.memory_bytes()/1024/1024:.2f} MB, N={self.total})")


# ─────────────────────────────────────────────────────────────────────────────
#  Bloom Filter
# ─────────────────────────────────────────────────────────────────────────────
class BloomFilter:
    """Membership test in a bit array.

    Guarantee: no false negatives.  ``x in bf`` is ``True`` for every ``x`` that
    was added; it may also be ``True`` for a fraction ``p`` of keys that were
    not.

    We use it to shrink a *broadcast* set.  Broadcasting 500K H3 transitions as
    strings costs tens of megabytes per executor; the same set at p=1% costs
    under a megabyte, and the false positives only make the downstream filter
    slightly less selective -- they never drop a real match.
    """

    __slots__ = ("m", "k", "bits", "n")

    def __init__(self, capacity: int, error_rate: float = 0.01):
        capacity = max(int(capacity), 1)
        self.m = max(8, int(math.ceil(-capacity * math.log(error_rate) / (math.log(2) ** 2))))
        self.m += (-self.m) % 8                      # round up to whole bytes
        self.k = max(1, int(round((self.m / capacity) * math.log(2))))
        self.bits = bytearray(self.m // 8)
        self.n = 0

    def memory_bytes(self) -> int:
        return len(self.bits)

    def add(self, key) -> None:
        h = hash64(key)
        for i in range(self.k):
            idx = _pair(h, i, self.m)
            self.bits[idx >> 3] |= (1 << (idx & 7))
        self.n += 1

    def __contains__(self, key) -> bool:
        h = hash64(key)
        for i in range(self.k):
            idx = _pair(h, i, self.m)
            if not (self.bits[idx >> 3] >> (idx & 7)) & 1:
                return False
        return True

    def merge(self, other: "BloomFilter") -> "BloomFilter":
        if self.m != other.m or self.k != other.k:
            raise ValueError("cannot merge bloom filters with different geometry")
        a, b = self.bits, other.bits
        for i in range(len(a)):
            a[i] |= b[i]
        self.n += other.n
        return self

    def expected_fp_rate(self) -> float:
        """Observed load factor -> predicted false-positive probability."""
        set_bits = sum(bin(b).count("1") for b in self.bits)
        load = set_bits / self.m
        return load ** self.k

    def __getstate__(self):
        return (self.m, self.k, bytes(self.bits), self.n)

    def __setstate__(self, state):
        self.m, self.k, raw, self.n = state
        self.bits = bytearray(raw)

    def __repr__(self):
        return (f"BloomFilter(m={self.m} bits, k={self.k}, n={self.n}, "
                f"{self.memory_bytes()/1024:.1f} KB, p~{self.expected_fp_rate():.4f})")


# ─────────────────────────────────────────────────────────────────────────────
#  HyperLogLog
# ─────────────────────────────────────────────────────────────────────────────
class HyperLogLog:
    """Distinct-count estimation in ``2^b`` bytes.

    Standard error is ``1.04 / sqrt(2^b)``; at ``b=12`` that is ~1.6% for 4 KB
    per sketch, independent of how many distinct items pass through it.

    We use it where an exact ``set()`` of trip ids would blow up the driver:
    counting distinct trips per LSH bucket, and distinct taxis per H3 cell.
    """

    __slots__ = ("b", "m", "registers", "_alpha")

    def __init__(self, b: int = 12):
        if not 4 <= b <= 16:
            raise ValueError("b must be in [4, 16]")
        self.b = b
        self.m = 1 << b
        self.registers = bytearray(self.m)
        self._alpha = self._alpha_for(self.m)

    @staticmethod
    def _alpha_for(m: int) -> float:
        if m == 16:
            return 0.673
        if m == 32:
            return 0.697
        if m == 64:
            return 0.709
        return 0.7213 / (1.0 + 1.079 / m)

    def memory_bytes(self) -> int:
        return self.m

    def add(self, key) -> None:
        self.add_hashed(hash64(key))

    def add_hashed(self, h: int) -> None:
        idx = h & (self.m - 1)
        w = h >> self.b
        # position of the leftmost 1-bit in the remaining 61-b bits, 1-indexed
        rank = 1
        limit = 61 - self.b
        while rank <= limit and not (w & 1):
            w >>= 1
            rank += 1
        if rank > self.registers[idx]:
            self.registers[idx] = rank

    def count(self) -> int:
        m = self.m
        acc = 0.0
        zeros = 0
        for r in self.registers:
            acc += 1.0 / (1 << r)
            if r == 0:
                zeros += 1
        est = self._alpha * m * m / acc
        if est <= 2.5 * m and zeros:                 # small-range correction
            est = m * math.log(m / zeros)
        return int(round(est))

    def merge(self, other: "HyperLogLog") -> "HyperLogLog":
        if self.b != other.b:
            raise ValueError("cannot merge HLLs with different precision")
        a, o = self.registers, other.registers
        for i in range(self.m):
            if o[i] > a[i]:
                a[i] = o[i]
        return self

    def __getstate__(self):
        return (self.b, bytes(self.registers))

    def __setstate__(self, state):
        self.b, raw = state
        self.m = 1 << self.b
        self.registers = bytearray(raw)
        self._alpha = self._alpha_for(self.m)

    def __repr__(self):
        return f"HyperLogLog(b={self.b}, {self.memory_bytes()/1024:.1f} KB, n~{self.count()})"


# ─────────────────────────────────────────────────────────────────────────────
#  Adaptive distinct counter (sparse -> dense)
# ─────────────────────────────────────────────────────────────────────────────
class DistinctCounter:
    """Counts distinct items exactly while the count is small, HLL once it isn't.

    A full :class:`HyperLogLog` costs ``2^b`` bytes *whether or not anything was
    added to it*, which is fatal when the counter is the accumulator of a Spark
    ``aggregateByKey`` over tens of millions of keys: almost every key is cold
    and would still pay for 4 KB of registers.

    So this starts as a plain ``set`` and only promotes itself to a HyperLogLog
    after ``sparse_limit`` distinct items.  Cold keys stay at a few dozen bytes,
    hot keys are bounded at ``2^b``, and the count is *exact* in the sparse
    regime -- which is where LSH buckets below the support threshold live.
    This is the same sparse/dense split that production HLL implementations use.
    """

    __slots__ = ("sparse", "hll", "b", "sparse_limit")

    def __init__(self, b: int = 8, sparse_limit: int = 64):
        self.b = b
        self.sparse_limit = sparse_limit
        self.sparse: set | None = set()
        self.hll: HyperLogLog | None = None

    def _promote(self) -> None:
        self.hll = HyperLogLog(b=self.b)
        for h in self.sparse:
            self.hll.add_hashed(h)
        self.sparse = None

    def add(self, key) -> None:
        self.add_hashed(hash64(key))

    def add_hashed(self, h: int) -> None:
        if self.sparse is not None:
            self.sparse.add(h)
            if len(self.sparse) > self.sparse_limit:
                self._promote()
        else:
            self.hll.add_hashed(h)

    def count(self) -> int:
        return len(self.sparse) if self.sparse is not None else self.hll.count()

    def is_exact(self) -> bool:
        return self.sparse is not None

    def merge(self, other: "DistinctCounter") -> "DistinctCounter":
        if self.sparse is not None and other.sparse is not None:
            self.sparse |= other.sparse
            if len(self.sparse) > self.sparse_limit:
                self._promote()
            return self
        if self.sparse is not None:
            self._promote()
        if other.sparse is not None:
            for h in other.sparse:
                self.hll.add_hashed(h)
        else:
            self.hll.merge(other.hll)
        return self

    def __getstate__(self):
        return (self.b, self.sparse_limit,
                list(self.sparse) if self.sparse is not None else None,
                self.hll.__getstate__() if self.hll is not None else None)

    def __setstate__(self, state):
        self.b, self.sparse_limit, sparse, hll = state
        self.sparse = set(sparse) if sparse is not None else None
        if hll is not None:
            self.hll = HyperLogLog(b=self.b)
            self.hll.__setstate__(hll)
        else:
            self.hll = None

    def __repr__(self):
        mode = "exact" if self.is_exact() else f"hll(b={self.b})"
        return f"DistinctCounter({mode}, n={self.count()})"


__all__ = ["hash64", "CountMinSketch", "BloomFilter", "HyperLogLog",
           "DistinctCounter"]
