from train.modules.arduino_hub.timing import (
    HEARTBEAT_TIMEOUT,
    MAX_READER_TIMEOUT_TOTAL_MS,
    pn532_wait_delay_bound_ms,
)


def test_maximum_reader_batch_leaves_heartbeat_margin() -> None:
    timeouts = [1] * 7 + [993]

    assert sum(timeouts) == MAX_READER_TIMEOUT_TOTAL_MS
    bound_ms = pn532_wait_delay_bound_ms(timeouts)
    assert bound_ms < HEARTBEAT_TIMEOUT * 1000
    assert HEARTBEAT_TIMEOUT * 1000 - bound_ms >= 800
