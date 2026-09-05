import asyncio
import logging

from train.core.app import App
from train.config import default_automation_path, load_runtime_config
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
        automation_update=automation_module.replace_json,
        automation_subscribe=automation_module.subscribe_changes,
        automation_unsubscribe=automation_module.unsubscribe_changes,
    )
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
