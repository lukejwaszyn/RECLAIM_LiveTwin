from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

from convene_bridge.writer import AtomicJSONWriter, AtomicWriteError, SingletonLock


def test_atomic_replacement_remains_complete_under_concurrent_reader(tmp_path):
    destination = tmp_path / "sim_vars.json"
    writer = AtomicJSONWriter(destination)
    writer.write({"seq": 0, "blob": "x" * 10_000})
    stop = threading.Event()
    failures: list[Exception] = []

    def read_repeatedly():
        while not stop.is_set():
            try:
                payload = json.loads(destination.read_text(encoding="utf-8"))
                assert isinstance(payload["seq"], int)
                assert len(payload["blob"]) == 10_000
            except Exception as exc:  # captured for assertion in the parent thread
                failures.append(exc)
                stop.set()

    reader = threading.Thread(target=read_repeatedly)
    reader.start()
    try:
        for seq in range(1, 101):
            writer.write({"seq": seq, "blob": str(seq % 10) * 10_000})
    finally:
        stop.set()
        reader.join(timeout=5)
    assert not failures
    assert json.loads(destination.read_text(encoding="utf-8"))["seq"] == 100


def test_sharing_violation_is_retried_then_replaced(tmp_path):
    destination = tmp_path / "sim_vars.json"
    attempts = 0
    sleeps: list[float] = []

    def replace_after_two(source, target):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        os.replace(source, target)

    writer = AtomicJSONWriter(
        destination,
        retry_timeout_s=1,
        retry_interval_s=0.01,
        sleeper=sleeps.append,
        replacer=replace_after_two,
    )
    writer.write({"complete": True})
    assert attempts == 3
    assert len(sleeps) == 2
    assert json.loads(destination.read_text(encoding="utf-8")) == {"complete": True}


def test_bounded_retry_leaves_last_complete_destination_intact(tmp_path):
    destination = tmp_path / "sim_vars.json"
    destination.write_text('{"seq":1}\n', encoding="utf-8")
    current = [0.0]

    def clock():
        return current[0]

    def sleep(seconds):
        current[0] += seconds

    def always_locked(_source, _target):
        error = PermissionError("sharing violation")
        error.winerror = 32
        raise error

    writer = AtomicJSONWriter(
        destination,
        retry_timeout_s=0.1,
        retry_interval_s=0.05,
        clock=clock,
        sleeper=sleep,
        replacer=always_locked,
    )
    with pytest.raises(AtomicWriteError):
        writer.write({"seq": 2})
    assert destination.read_text(encoding="utf-8") == '{"seq":1}\n'
    assert current[0] == pytest.approx(0.1)
    assert not list(tmp_path.glob("*.tmp"))


def test_singleton_enforces_one_writer(tmp_path):
    path = tmp_path / "bridge.lock"
    first = SingletonLock(path)
    second = SingletonLock(path)
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="another"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()
