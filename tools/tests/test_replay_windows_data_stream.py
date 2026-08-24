from __future__ import annotations

import json
import socket
import threading

from replay_windows_data_stream import inferred_chamber, parse_record, records, replay


LINE = (
    "PL_surface_temp: 22.677758, PL_preprocess: TRUE, MW_RF: FALSE, "
    "MW_reverse_coupler: 0, MW_freq: 2450.000000"
)


def test_parse_record_preserves_exact_channel_names_and_types():
    value = parse_record(LINE)
    assert value == {
        "PL_surface_temp": 22.677758,
        "PL_preprocess": True,
        "MW_RF": False,
        "MW_reverse_coupler": 0,
        "MW_freq": 2450.0,
    }
    assert inferred_chamber(value) == "PL"


def test_records_ignores_header_and_blank_lines(tmp_path):
    capture = tmp_path / "capture.txt"
    capture.write_text("08/03/26 12:57:43 PM\n\n" + LINE + "\n\n", encoding="ascii")
    assert list(records(capture)) == [parse_record(LINE)]


def test_replay_emits_structured_scenario_envelope(tmp_path):
    capture = tmp_path / "capture.txt"
    capture.write_text("08/03/26 12:57:43 PM\n\n" + LINE + "\n", encoding="ascii")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received = []

    def accept():
        connection, _ = listener.accept()
        with connection, connection.makefile(encoding="utf-8") as stream:
            received.append(json.loads(stream.readline()))
        listener.close()

    thread = threading.Thread(target=accept)
    thread.start()
    assert replay(capture, "127.0.0.1", port, 100, 100, 1, "S_Unknown", "auto") == 1
    thread.join(timeout=2)

    assert received[0]["source_op_state"] == "S_Unknown"
    assert received[0]["active_chamber"] == "PL"
    assert received[0]["vars"]["PL_surface_temp"] == 22.677758
