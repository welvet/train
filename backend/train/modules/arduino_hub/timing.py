HEARTBEAT_INTERVAL = 1.0
MAX_READER_TIMEOUT_TOTAL_MS = 1000
MAX_READER_READ_TIMEOUT_MS = MAX_READER_TIMEOUT_TOTAL_MS
HEARTBEAT_TIMEOUT = 3 * MAX_READER_TIMEOUT_TOTAL_MS / 1000

PN532_READY_WAIT_COUNT = 2
PN532_READY_POLL_MS = 10
PN532_FIXED_DELAY_MS = 2


def pn532_wait_delay_bound_ms(read_timeouts_ms: list[int]) -> int:
    """Bound Adafruit PN532 readiness waits and fixed delays for one batch."""
    return sum(
        PN532_READY_WAIT_COUNT
        * ((timeout_ms + PN532_READY_POLL_MS - 1) // PN532_READY_POLL_MS)
        * PN532_READY_POLL_MS
        + PN532_FIXED_DELAY_MS
        for timeout_ms in read_timeouts_ms
    )
