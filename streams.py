"""Tiny in-memory event streams used for Server-Sent Events (live logs, AI jobs)."""
import json
import threading
import time
import uuid


class Stream:
    """Append-only event list; readers can replay from any index (SSE reconnect safe)."""

    def __init__(self):
        self.events = []
        self.cv = threading.Condition()
        self.closed = False
        self.created = time.time()

    def emit(self, **ev):
        with self.cv:
            self.events.append(ev)
            self.cv.notify_all()

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()

    def sse(self, start=0, heartbeat=15):
        """Generator of SSE frames. Sends a comment ping while idle to keep proxies open."""
        i = start
        while True:
            with self.cv:
                if i >= len(self.events) and not self.closed:
                    self.cv.wait(heartbeat)
                batch = self.events[i:]
                closed = self.closed
            if not batch:
                if closed:
                    return
                yield ": ping\n\n"
                continue
            for ev in batch:
                yield f"id: {i}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                i += 1


_streams = {}
_lock = threading.Lock()


def new_stream(prefix="job"):
    sid = f"{prefix}{uuid.uuid4().hex[:10]}"
    s = Stream()
    with _lock:
        _streams[sid] = s
        if len(_streams) > 100:  # prune old finished streams
            for k, v in sorted(_streams.items(), key=lambda kv: kv[1].created)[:30]:
                if v.closed and time.time() - v.created > 3600:
                    _streams.pop(k, None)
    return sid, s


def get_stream(sid):
    with _lock:
        return _streams.get(sid)


def one_shot(events):
    """SSE frames for a fixed list of events (used for finished runs loaded from the DB)."""
    for i, ev in enumerate(events):
        yield f"id: {i}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
