"""Check a simulated run against the `expect` block of its scenario file.

    study / context / intents / requests   ordered subsequence of what happened
    reflex   {"at", "state", "within"}     a study state is entered within `within` s of `at`
    no_motion_after   t                    every intervention after t is light-only
    vetoed   [intent, ...]                 these intents were blocked by an interceptor
    count    {intent: n}                   intent fired exactly n times
"""

from __future__ import annotations

from .types import APP_REQUEST, INTERVENE, STATE_ENTER, VETO, Event


def _subsequence(want: list, have: list) -> bool:
    it = iter(have)
    return all(any(x == w for x in it) for w in want)


def check(expect: dict, events: list[Event]) -> list[str]:
    """Returns a list of failures; empty means the run met every expectation."""
    enters = [e for e in events if e.kind == STATE_ENTER]
    study = [e.data["state"] for e in enters if e.data["layer"] == "study"]
    context = [e.data["state"] for e in enters if e.data["layer"] == "context"]
    fired = [e for e in events if e.kind == INTERVENE]
    intents = [e.data["intent"] for e in fired]
    requests = [e.data.get("action") for e in events if e.kind == APP_REQUEST]
    fails = []
    for key, have in (("study", study), ("context", context), ("intents", intents), ("requests", requests)):
        if key in expect and not _subsequence(expect[key], have):
            fails.append("%s: wanted %s in order, got %s" % (key, expect[key], have))
    if "reflex" in expect:
        r = expect["reflex"]
        hits = [e.t for e in enters if e.data["state"] == r["state"] and e.t >= r["at"] - 1e-9]
        if not hits or hits[0] - r["at"] > r["within"] + 1e-9:
            fails.append("reflex: %s not entered within %.2fs of %.1fs (got %s)" % (r["state"], r["within"], r["at"], hits[:1]))
    if "no_motion_after" in expect:
        moved = [e.data["intent"] for e in fired if e.t > expect["no_motion_after"] and e.data.get("motion")]
        if moved:
            fails.append("no_motion_after: moved for %s" % moved)
    if "vetoed" in expect:
        blocked = [e.data["data"].get("intent") for e in events if e.kind == VETO and isinstance(e.data.get("data"), dict)]
        missing = [i for i in expect["vetoed"] if i not in blocked]
        if missing:
            fails.append("vetoed: %s were not blocked (blocked %s)" % (missing, blocked))
    for intent, n in expect.get("count", {}).items():
        if intents.count(intent) != n:
            fails.append("count: %s fired %d times, wanted %d" % (intent, intents.count(intent), n))
    return fails
