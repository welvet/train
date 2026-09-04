import asyncio
import logging

from train.core.app import App
from train.config import load_automation, load_runtime_config
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
    automation = load_automation()
    app = App()
    app.add_module(
        AutomationModule,
        configure=automation.configure,
        script=automation.run,
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
        shutdown_callback=app.request_shutdown,
    )
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
