"""RAM hot-graph cache for the board.

The board lives on disk (unbounded); the hot set lives in RAM (bounded).
This is a small LRU over node lookups and neighbor lists so per-turn
retrieval does not re-hit SQLite for the same nodes.

  cache = HotCache(board, max_nodes=5000)
  cache.node(nid)          # node dict or None
  cache.neighbors(nid)     # list of neighbor dicts
  cache.invalidate()       # after a board build
"""
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HotCache:
    def __init__(self, board, max_nodes=5000, max_neighbors=5000):
        self.board = board
        self.max_nodes = max_nodes
        self.max_neighbors = max_neighbors
        self._nodes = OrderedDict()
        self._neighbors = OrderedDict()

    def node(self, nid):
        if nid in self._nodes:
            self._nodes.move_to_end(nid)
            return self._nodes[nid]
        n = self.board.get_node_by_id(nid)
        self._put(self._nodes, nid, n, self.max_nodes)
        return n

    def neighbors(self, nid):
        if nid in self._neighbors:
            self._neighbors.move_to_end(nid)
            return self._neighbors[nid]
        ns = self.board.neighbors(nid)
        self._put(self._neighbors, nid, ns, self.max_neighbors)
        return ns

    @staticmethod
    def _put(cache, key, val, cap):
        cache[key] = val
        while len(cache) > cap:
            cache.popitem(last=False)

    def invalidate(self):
        self._nodes.clear()
        self._neighbors.clear()

    def stats(self):
        return {"hot_nodes": len(self._nodes),
                "hot_neighbors": len(self._neighbors)}


if __name__ == "__main__":
    import os
    import tempfile
    from board.store import BoardStore
    d = tempfile.mkdtemp()
    st = BoardStore(os.path.join(d, "b.db"))
    a = st.upsert_node("project", "robot arm")
    b = st.upsert_node("tool", "NEMA 23")
    st.add_edge(a, b, "uses")
    c = HotCache(st)
    assert c.node(a)["name"] == "robot arm"
    assert c.neighbors(a)[0]["name"] == "NEMA 23"
    assert c.stats()["hot_nodes"] == 1
    print("[board.cache] OK", c.stats())
