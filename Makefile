.DEFAULT_GOAL := help

.PHONY: help server-push arduino-list arduino-compile arduino-upload _require-device

help:
	@printf '%s\n' \
		'make server-push [SERVER_PUSH_ARGS=--no-wait]' \
		'make arduino-list' \
		'make arduino-compile DEVICE=<device-id>' \
		'make arduino-upload DEVICE=<device-id>'

server-push:
	./tools/server-push $(SERVER_PUSH_ARGS)

arduino-list:
	./tools/arduino list

arduino-compile: _require-device
	./tools/arduino compile "$(DEVICE)"

# tools/arduino upload compiles the firmware before uploading it.
arduino-upload: _require-device
	./tools/arduino upload "$(DEVICE)"

_require-device:
	@test -n "$(strip $(DEVICE))" || { \
		echo 'DEVICE is required (example: make arduino-compile DEVICE=<device-id>)' >&2; \
		exit 2; \
	}
