import argparse
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

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


_COMMAND_OP = "status"
_ON_PAYLOAD = b"ON"
_OFF_PAYLOAD = b"OFF"
_BRIGHTNESS_OP = "brightness"

_TOPIC_FMT = "{device_name}/lights/{number}/{op}/state"
_CACHE: typing.Dict[int, int] = {}


async def process_message(
    message: paho.mqtt.client.MQTTMessage,
    driver: dali.driver.base.SyncDALIDriver,
    mqtt_client: asyncio_mqtt.Client,
    device_name: str,
) -> None:
    """Handle single message"""
    logger.info(f"Incoming message: {message.payload}")

    topic_regex = re.compile(
        r"{device_name}/lights/(?P<number>\d+)/(?P<op>(status|brightness))/set".format(device_name=device_name)
    )
    match = topic_regex.match(message.topic)
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
                    _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_COMMAND_OP),
                    _ON_PAYLOAD,
                ),
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_BRIGHTNESS_OP), b"254"
                ),
            )
            _CACHE[device_number] = 254
        elif message.payload == _OFF_PAYLOAD and previous != 0:
            driver.send(Off(device_number))
            await asyncio.gather(
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_COMMAND_OP), _OFF_PAYLOAD
                ),
                mqtt_client.publish(
                    _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_BRIGHTNESS_OP), b"0"
                ),
            )
            _CACHE[device_number] = 0
        else:
            return
    # home assistant seems to send and "ON" for each brightness update
    elif op == _BRIGHTNESS_OP:
        driver.send(DAPC(device_number, int(message.payload)))
        await mqtt_client.publish(
            _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_BRIGHTNESS_OP), message.payload
        )
        _CACHE[device_number] = int(message.payload)
        return


async def amain(mqtt_broker: str, bus_number: int, device_name: str) -> None:
    """Main loop"""

    logger.info("Setting up DALI bus ...")
    driver = dali.driver.unipi.SyncUnipiDALIDriver(bus=bus_number)
    logger.info("Finished setup DALI bus.")

    topic_filter = f"{device_name}/lights/#"

    logger.info("Set up MQTT connection.")
    async with asyncio_mqtt.Client(mqtt_broker) as client:
        logger.info(f"Subscribing to base topic filter {topic_filter}")
        await client.subscribe(topic_filter)
        async with client.filtered_messages(topic_filter) as messages:
            async for message in messages:
                await process_message(message, driver, client, device_name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mqtt_broker", help="MQTT broker URI")
    parser.add_argument("--bus", type=int, help="Unipi DALI driver bus number", default=0)
    parser.add_argument("--device_name", type=str, help="Base topic device name", default="dali")
    args = parser.parse_args()

    asyncio.run(amain(args.mqtt_broker, args.bus, args.device_name))


if __name__ == "__main__":
    main()
