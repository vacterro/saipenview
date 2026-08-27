"""T-33 / W2-023: _gen_token race outside registry lock.

_next_token += 1 happened outside the registry lock. Two-thread barrier
caused both record calls to receive token 1. Same-path acknowledgement
with stale first event token cleared newer entry.

Fix: move _gen_token() inside the registry lock so token allocation and
entry insertion are atomic.
"""

from __future__ import annotations

import threading

import pytest

from saipenview.external_changes import ExternalChangeRegistry


def test_concurrent_records_get_distinct_tokens():
    """Two threads recording same path must get distinct tokens."""
    registry = ExternalChangeRegistry()
    tokens = []
    barrier = threading.Barrier(2)

    def record_one():
        barrier.wait()
        token = registry.record("/root", "STATE.md", "fp1")
        tokens.append(token)

    t1 = threading.Thread(target=record_one)
    t2 = threading.Thread(target=record_one)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(tokens) == 2, f"expected 2 tokens, got {tokens}"
    assert tokens[0] != tokens[1], f"tokens must be distinct: {tokens}"


def test_older_token_cannot_acknowledge_newer_entry():
    """Acknowledging with an older token must fail when a newer entry exists."""
    registry = ExternalChangeRegistry()
    token1 = registry.record("/root", "STATE.md", "fp1")
    token2 = registry.record("/root", "STATE.md", "fp2")

    assert token1 != token2, "tokens must be distinct"
    assert token2 > token1, "newer token must be larger"

    # Acknowledge with older token -> must fail
    assert registry.acknowledge("/root", "STATE.md", token1) is False
    # Acknowledge with newer token -> must succeed
    assert registry.acknowledge("/root", "STATE.md", token2) is True
    # No entries remain
    assert registry.pending("/root") == []
