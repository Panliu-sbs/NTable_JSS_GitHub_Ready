from __future__ import annotations

from typing import List, Optional, Tuple

NEG_INF = -(10**30)


class LazyMaxSegmentTree:
    """Range add, point set/query, and range maximum in O(log n)."""

    __slots__ = ("n", "size", "tree", "lazy")

    def __init__(self, n: int) -> None:
        if n <= 0:
            raise ValueError("Segment-tree size must be positive")
        self.n = n
        size = 1
        while size < n:
            size <<= 1
        self.size = size
        self.tree = [NEG_INF] * (2 * size)
        self.lazy = [0] * (2 * size)

    def _apply(self, idx: int, delta: int) -> None:
        if self.tree[idx] != NEG_INF:
            self.tree[idx] += delta
        self.lazy[idx] += delta

    def _push(self, idx: int) -> None:
        delta = self.lazy[idx]
        if delta:
            self._apply(idx * 2, delta)
            self._apply(idx * 2 + 1, delta)
            self.lazy[idx] = 0

    def point_set(self, pos: int, value: int) -> None:
        self._point_set(1, 0, self.size - 1, pos, value)

    def _point_set(self, idx: int, lo: int, hi: int, pos: int, value: int) -> None:
        if lo == hi:
            self.tree[idx] = value
            self.lazy[idx] = 0
            return
        self._push(idx)
        mid = (lo + hi) // 2
        if pos <= mid:
            self._point_set(idx * 2, lo, mid, pos, value)
        else:
            self._point_set(idx * 2 + 1, mid + 1, hi, pos, value)
        self.tree[idx] = max(self.tree[idx * 2], self.tree[idx * 2 + 1])

    def range_add(self, ql: int, qr: int, delta: int) -> None:
        if ql > qr:
            return
        self._range_add(1, 0, self.size - 1, ql, qr, delta)

    def _range_add(
        self, idx: int, lo: int, hi: int, ql: int, qr: int, delta: int
    ) -> None:
        if qr < lo or hi < ql:
            return
        if ql <= lo and hi <= qr:
            self._apply(idx, delta)
            return
        self._push(idx)
        mid = (lo + hi) // 2
        self._range_add(idx * 2, lo, mid, ql, qr, delta)
        self._range_add(idx * 2 + 1, mid + 1, hi, ql, qr, delta)
        self.tree[idx] = max(self.tree[idx * 2], self.tree[idx * 2 + 1])

    def range_max(self, ql: int, qr: int) -> int:
        if ql > qr:
            return NEG_INF
        return self._range_max(1, 0, self.size - 1, ql, qr)

    def _range_max(self, idx: int, lo: int, hi: int, ql: int, qr: int) -> int:
        if qr < lo or hi < ql:
            return NEG_INF
        if ql <= lo and hi <= qr:
            return self.tree[idx]
        self._push(idx)
        mid = (lo + hi) // 2
        return max(
            self._range_max(idx * 2, lo, mid, ql, qr),
            self._range_max(idx * 2 + 1, mid + 1, hi, ql, qr),
        )

    def point_query(self, pos: int) -> int:
        return self.range_max(pos, pos)


class MaxIndexSegmentTree:
    """Point max update + prefix maximum index query over compressed rank values."""

    __slots__ = ("n", "size", "tree")

    def __init__(self, n: int) -> None:
        if n <= 0:
            raise ValueError("Segment-tree size must be positive")
        self.n = n
        size = 1
        while size < n:
            size <<= 1
        self.size = size
        self.tree = [-1] * (2 * size)

    def update_max(self, pos: int, value: int) -> None:
        idx = self.size + pos
        if value <= self.tree[idx]:
            return
        self.tree[idx] = value
        idx //= 2
        while idx:
            self.tree[idx] = max(self.tree[idx * 2], self.tree[idx * 2 + 1])
            idx //= 2

    def prefix_max(self, right_exclusive: int) -> int:
        if right_exclusive <= 0:
            return -1
        l = self.size
        r = self.size + min(right_exclusive, self.n)
        ans = -1
        while l < r:
            if l & 1:
                ans = max(ans, self.tree[l])
                l += 1
            if r & 1:
                r -= 1
                ans = max(ans, self.tree[r])
            l //= 2
            r //= 2
        return ans


class ArgMaxLeftmostSegmentTree:
    """Static RMQ returning (max value, leftmost index) among operator positions."""

    __slots__ = ("n", "size", "tree")

    def __init__(self, values: Tuple[Optional[int], ...]) -> None:
        self.n = len(values)
        size = 1
        while size < max(1, self.n):
            size <<= 1
        self.size = size
        self.tree: List[Tuple[int, int]] = [(NEG_INF, 10**30)] * (2 * size)
        for i, value in enumerate(values):
            if value is not None:
                self.tree[size + i] = (value, i)
        for idx in range(size - 1, 0, -1):
            self.tree[idx] = self._better(self.tree[idx * 2], self.tree[idx * 2 + 1])

    @staticmethod
    def _better(a: Tuple[int, int], b: Tuple[int, int]) -> Tuple[int, int]:
        if a[0] != b[0]:
            return a if a[0] > b[0] else b
        return a if a[1] < b[1] else b

    def query(self, ql: int, qr: int) -> Tuple[int, int]:
        if ql > qr:
            return (NEG_INF, 10**30)
        l = ql + self.size
        r = qr + self.size + 1
        left_ans = (NEG_INF, 10**30)
        right_ans = (NEG_INF, 10**30)
        while l < r:
            if l & 1:
                left_ans = self._better(left_ans, self.tree[l])
                l += 1
            if r & 1:
                r -= 1
                right_ans = self._better(self.tree[r], right_ans)
            l //= 2
            r //= 2
        return self._better(left_ans, right_ans)
