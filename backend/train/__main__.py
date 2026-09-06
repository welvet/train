import asyncio
import logging
from dataclasses import replace

from train.config import (
    default_automation_path,
    default_trains_path,
    load_runtime_config,
    normalized_trains_document,
    parse_trains_document,
)
from train.configuration import ConfigurationStore
from train.core.app import App
from train.domain import SystemState
from train.modules.arduino_hub import ArduinoHubModule
from train.modules.automation import AutomationModule
from train.modules.lego_ble import LegoBleModule
from train.modules.web_api import WebApiModule


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("bleak").setLevel(logging.WARNING)
    config = load_runtime_config()
    app = App(state=SystemState.from_topology(
        train_hubs={
            train.train_id: train.lego_hub_id for train in config.trains
        },
        arduino_hubs=config.arduino_hubs,
    ))
    automation_module = app.add_module(
        AutomationModule,
        path=default_automation_path(),
        tagged_trains={train.train_id for train in config.trains if train.tag_ids},
    )

    def normalize_trains(document: dict[str, object]) -> dict[str, object]:
        normalized = normalized_trains_document(document)
        automation_module.validate_runtime_config(
            replace(config, trains=parse_trains_document(normalized))
        )
        return normalized

    configuration = ConfigurationStore.for_trains(
        default_trains_path(),
        normalize=normalize_trains,
    )
    configuration_update_lock = asyncio.Lock()

    async def update_configuration(text: str) -> dict[str, object]:
        async with configuration_update_lock:
            return await configuration.replace_json(text)

    async def update_automation(text: str) -> dict[str, object]:
        async with configuration_update_lock:
            persisted_trains = parse_trains_document(
                configuration.document_value("trains")
            )
            automation_module.validate_json_for_runtime_config(
                text,
                replace(config, trains=persisted_trains),
            )
            return await automation_module.replace_json(text)

    app.add_module(
        LegoBleModule,
        train_map=config.train_map,
    )
    app.add_module(
        ArduinoHubModule,
        host=config.backend.arduino_host,
        port=config.backend.arduino_port,
        train_tag_map=config.train_tag_map,
        hub_config=config.arduino_hubs,
    )
    app.add_module(
        WebApiModule,
        host=config.backend.api_host,
        port=config.backend.api_port,
        readiness_check=lambda: automation_module.healthy,
        automation_snapshot=automation_module.snapshot,
        automation_update=update_automation,
        automation_subscribe=automation_module.subscribe_changes,
        automation_unsubscribe=automation_module.unsubscribe_changes,
        configuration_snapshot=configuration.snapshot,
        configuration_update=update_configuration,
    )
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
