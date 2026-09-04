import asyncio
import logging

from train.core.app import App
from train.config import TRAINS
from train.modules.arduino_hub import ArduinoHubModule
from train.modules.automation import AutomationModule
from train.modules.lego_ble import LegoBleModule
from train.modules.web_api import WebApiModule
from train.scripts.demo_script import demo_script


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("bleak").setLevel(logging.WARNING)
    app = App()
    app.add_module(
        LegoBleModule,
        train_map={train.ble_address: train.train_id for train in TRAINS},
    )
    app.add_module(AutomationModule, script=demo_script)
    app.add_module(
        ArduinoHubModule,
        train_tag_map={train.tag_id: train.train_id for train in TRAINS if train.tag_id},
    )
    app.add_module(WebApiModule, shutdown_callback=app.request_shutdown)
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
