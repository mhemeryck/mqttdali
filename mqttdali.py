import asyncio
import logging
import logging.config
import re
import typing

import asyncio_mqtt  # type: ignore
import dali.address  # type: ignore
import dali.driver.base  # type: ignore
import dali.driver.unipi  # type: ignore
import paho.mqtt.client  # type: ignore
from dali.gear.general import DAPC, Off  # type: ignore

LOG_LEVEL = logging.INFO
LOG_CONFIG = dict(
    version=1,
    formatters={"default": {"format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s"}},
    handlers={
        "stream": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": LOG_LEVEL,
        }
    },
    root={"handlers": ["stream"], "level": LOG_LEVEL},
)

logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)

# TODO: convert to settings
# _MQTT_BROKER = "192.168.1.14"
_MQTT_BROKER = "emqx.mhemeryck.com"
# _MQTT_BROKER = "shuttle.lan"
# _MQTT_BROKER = "192.168.1.205"
_DEVICE_NAME = "dali"

_BUS_NUMBER = 0
_BUS_NAME = "1_01"
_DEVICE_NUMBER = 0
_BASE_TOPIC = "{device_name}/lights/+".format(
    device_name=_DEVICE_NAME,
)


logger.info("Setting up DALI bus ...")
_DRIVER = dali.driver.unipi.SyncUnipiDALIDriver(bus=_BUS_NUMBER)
logger.info("Finished setup DALI bus.")

_COMMAND_OP = "status"
_ON_PAYLOAD = b"ON"
_OFF_PAYLOAD = b"OFF"
_BRIGHTNESS_OP = "brightness"
_TOPIC_REGEX = re.compile(
    r"{device_name}/lights/(?P<number>\d+)/(?P<op>(status|brightness))/set".format(device_name=_DEVICE_NAME)
)
_TOPIC_FMT = "{device_name}/lights/{number}/{op}/state"
_CACHE: typing.Dict[int, int] = {}

_BASE_TOPIC_FILTER = "{device_name}/lights/#".format(device_name=_DEVICE_NAME)


async def process_message(
    message: paho.mqtt.client.MQTTMessage,
    driver: dali.driver.base.SyncDALIDriver,
    mqtt_client: asyncio_mqtt.Client,
) -> None:
    """Handle single message"""
    logger.info(f"Incoming message: {message.payload}")
    match = _TOPIC_REGEX.match(message.topic)
    if not match:
        return

    device_number = int(match.group("number"))
    op = match.group("op")
    previous = _CACHE.get(device_number)
    if not previous:
        _CACHE[device_number] = previous = 0

    if op == _COMMAND_OP:
        if message.payload == _ON_PAYLOAD and previous == 0:
            driver.send(DAPC(device_number, 254))
            await asyncio.gather(
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=_DEVICE_NAME, number=device_number, op=_COMMAND_OP),
                    _ON_PAYLOAD,
                ),
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=_DEVICE_NAME, number=device_number, op=_BRIGHTNESS_OP), b"254"
                ),
            )
            _CACHE[device_number] = 254
        elif message.payload == _OFF_PAYLOAD and previous != 0:
            driver.send(Off(device_number))
            await asyncio.gather(
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=_DEVICE_NAME, number=device_number, op=_COMMAND_OP), _OFF_PAYLOAD
                ),
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=_DEVICE_NAME, number=device_number, op=_BRIGHTNESS_OP), b"0"
                ),
            )
            _CACHE[device_number] = 0
        else:
            return
    # home assistant seems to send and "ON" for each brightness update
    elif op == _BRIGHTNESS_OP:
        driver.send(DAPC(device_number, int(message.payload)))
        await mqtt_client.publish(
            _TOPIC_FMT.format(device_name=_DEVICE_NAME, number=device_number, op=_BRIGHTNESS_OP), message.payload
        )
        _CACHE[device_number] = int(message.payload)
        return


async def amain() -> None:
    """Main loop"""
    logger.info("Set up MQTT connection.")
    async with asyncio_mqtt.Client(_MQTT_BROKER) as client:
        logger.info(f"Subscribing to base topic filter {_BASE_TOPIC_FILTER}")
        await client.subscribe(_BASE_TOPIC_FILTER)
        async with client.filtered_messages(_BASE_TOPIC_FILTER) as messages:
            async for message in messages:
                await process_message(message, _DRIVER, client)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
