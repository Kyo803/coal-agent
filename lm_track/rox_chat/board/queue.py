"""Board queue: append-only list of conversation exchanges awaiting the
archivist. Kept as JSONL at ~/.rox/board_queue.jsonl so nothing is lost
if the machine restarts mid-batch.

A job is one exchange:
  {"id","session_id","msg_id","ts","user_text","thinking","output","tools"}
"""
import json
import os
import time
import uuid


class Queue:
    def __init__(self, root="~/.rox"):
        self.root = os.path.expanduser(root)
        os.makedirs(self.root, exist_ok=True)
        self.path = os.path.join(self.root, "board_queue.jsonl")

    def enqueue(self, job):
        job = dict(job)
        job.setdefault("id", uuid.uuid4().hex[:12])
        job.setdefault("ts", time.time())
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(job) + "\n")
        return job["id"]

    def pending(self):
        if not os.path.exists(self.path):
            return []
        out = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            return []
        return out

    def remove(self, ids):
        ids = set(ids)
        if not ids:
            return
        pend = [j for j in self.pending() if j.get("id") not in ids]
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for j in pend:
                f.write(json.dumps(j) + "\n")
        os.replace(tmp, self.path)

    def count(self):
        return len(self.pending())


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    q = Queue(d)
    q.enqueue({"session_id": 1, "msg_id": 1, "user_text": "hi",
               "thinking": "greeting", "output": "hello"})
    q.enqueue({"session_id": 1, "msg_id": 2, "user_text": "build a robot",
               "thinking": "project", "output": "ok"})
    assert q.count() == 2
    pend = q.pending()
    q.remove([pend[0]["id"]])
    assert q.count() == 1
    print("[board.queue] OK, pending:", q.count())
