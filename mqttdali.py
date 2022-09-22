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
from dali.address import Short  # type: ignore
from dali.gear.general import DAPC, Off, QueryActualLevel  # type: ignore

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
_CACHE_LOCK = asyncio.Lock()


async def light_command_messages(
    driver: dali.driver.base.SyncDALIDriver,
    mqtt_client: asyncio_mqtt.Client,
    device_name: str,
) -> None:

    topic_regex = re.compile(r"{device_name}/lights/(?P<number>\d+)/status/set".format(device_name=device_name))
    topic_filter = f"{device_name}/lights/+/status/set"

    await mqtt_client.subscribe(topic_filter)
    async with mqtt_client.filtered_messages(topic_filter) as messages:
        async for message in messages:
            logger.info(f"Incoming light command message: {message.payload}")

            match = topic_regex.match(message.topic)
            if not match:
                logger.warning(f"{message.topic} did not match regex {topic_regex}")
                continue
            device_number = int(match.group("number"))

            previous = _CACHE.get(device_number)
            if not previous:
                async with _CACHE_LOCK:
                    response = driver.send(QueryActualLevel(Short(device_number)))
                    _CACHE[device_number] = previous = response.value

            if message.payload == _ON_PAYLOAD and previous == 0:
                driver.send(DAPC(Short(device_number), 254))
                await asyncio.gather(
                    mqtt_client.publish(
                        _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_COMMAND_OP),
                        _ON_PAYLOAD,
                    ),
                    mqtt_client.publish(
                        _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_BRIGHTNESS_OP), b"254"
                    ),
                )
                async with _CACHE_LOCK:
                    _CACHE[device_number] = 254
            elif message.payload == _OFF_PAYLOAD and previous != 0:
                driver.send(Off(Short(device_number)))
                await asyncio.gather(
                    mqtt_client.publish(
                        _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_COMMAND_OP), _OFF_PAYLOAD
                    ),
                    mqtt_client.publish(
                        _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_BRIGHTNESS_OP), b"0"
                    ),
                )
                async with _CACHE_LOCK:
                    _CACHE[device_number] = 0


async def light_brightness_messages(
    driver: dali.driver.base.SyncDALIDriver,
    mqtt_client: asyncio_mqtt.Client,
    device_name: str,
) -> None:

    topic_regex = re.compile(r"{device_name}/lights/(?P<number>\d+)/brightness/set".format(device_name=device_name))
    topic_filter = f"{device_name}/lights/+/brightness/set"

    await mqtt_client.subscribe(topic_filter)
    async with mqtt_client.filtered_messages(topic_filter) as messages:
        async for message in messages:
            logger.info(f"Incoming light brightness message: {message.payload}")

            match = topic_regex.match(message.topic)
            if not match:
                logger.warning(f"{message.topic} did not match regex {topic_regex}")
                continue
            device_number = int(match.group("number"))

            driver.send(DAPC(Short(device_number), int(message.payload)))
            await mqtt_client.publish(
                _TOPIC_FMT.format(device_name=device_name, number=device_number, op=_BRIGHTNESS_OP), message.payload
            )
            async with _CACHE_LOCK:
                _CACHE[device_number] = int(message.payload)


async def amain(mqtt_broker: str, bus_number: int, device_name: str) -> None:
    """Main loop"""

    logger.info("Setting up DALI bus ...")
    driver = dali.driver.unipi.SyncUnipiDALIDriver(bus=bus_number)
    logger.info("Finished setup DALI bus.")

    logger.info("Set up MQTT connection.")
    async with asyncio_mqtt.Client(mqtt_broker) as client:
        await asyncio.gather(
            light_command_messages(driver, client, device_name),
            light_brightness_messages(driver, client, device_name),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mqtt_broker", help="MQTT broker URI")
    parser.add_argument("--bus", type=int, help="Unipi DALI driver bus number", default=0)
    parser.add_argument("--device_name", type=str, help="Base topic device name", default="dali")
    args = parser.parse_args()

    asyncio.run(amain(args.mqtt_broker, args.bus, args.device_name))


if __name__ == "__main__":
    main()
