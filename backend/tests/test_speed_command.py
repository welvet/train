from train.modules.lego_ble import _build_speed_command


def test_stop_command() -> None:
    cmd = _build_speed_command(0x01, 0)
    assert cmd == bytes([0x06, 0x00, 0x81, 0x01, 0x11, 0x51, 0x00, 0x00])


def test_full_forward() -> None:
    cmd = _build_speed_command(0x01, 100)
    assert cmd[7] == 0x64


def test_full_reverse() -> None:
    cmd = _build_speed_command(0x01, -100)
    assert cmd[7] == 0x9C


def test_positive_speed() -> None:
    cmd = _build_speed_command(0x01, 50)
    assert cmd[7] == 0x32


def test_negative_speed() -> None:
    cmd = _build_speed_command(0x01, -50)
    assert cmd[7] == 0xCE


def test_clamp_over_100() -> None:
    cmd = _build_speed_command(0x01, 200)
    assert cmd[7] == 0x64


def test_clamp_under_minus_100() -> None:
    cmd = _build_speed_command(0x01, -200)
    assert cmd[7] == 0x9C


def test_different_port() -> None:
    cmd = _build_speed_command(0x00, 50)
    assert cmd[3] == 0x00


def test_command_length() -> None:
    cmd = _build_speed_command(0x01, 50)
    assert len(cmd) == 8


def test_message_header() -> None:
    cmd = _build_speed_command(0x01, 50)
    assert cmd[0] == 0x06  # length
    assert cmd[1] == 0x00  # hub id
    assert cmd[2] == 0x81  # port output command
    assert cmd[4] == 0x11  # startup + completion flags
    assert cmd[5] == 0x51  # StartPower sub-command
    assert cmd[6] == 0x00  # mode
