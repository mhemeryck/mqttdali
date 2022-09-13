import logging
import time
import typing

from dali.address import Short  # type: ignore
from dali.driver.base import SyncDALIDriver  # type: ignore
from dali.driver.unipi import SyncUnipiDALIDriver  # type: ignore
from dali.gear.general import (  # type: ignore
    Compare,
    Initialise,
    ProgramShortAddress,
    QueryControlGearPresent,
    Randomise,
    SetSearchAddrH,
    SetSearchAddrL,
    SetSearchAddrM,
    Terminate,
    VerifyShortAddress,
    Withdraw,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def set_search_addr(driver: SyncDALIDriver, addr: int) -> None:
    """
    Indicate the all ballasts on the bus that search is conducted for given (random) address

    The search address is a 24-bit address, split into 3 bytes
    """
    driver.send(SetSearchAddrH((addr >> 16) & 0xFF))
    driver.send(SetSearchAddrM((addr >> 8) & 0xFF))
    driver.send(SetSearchAddrL(addr & 0xFF))


def find_next(driver: SyncDALIDriver, low: int, high: int) -> int | None:
    """
    Find the ballast with the lowest random address.
    The caller guarantees that there are no ballasts with an address lower than
    'low'.
    """
    logger.info(f"Searching from {low} to {high}...")
    if low == high:
        set_search_addr(driver, low)
        response = driver.send(Compare())

        if response.value is True:
            logger.info("Found ballast at {low}; withdrawing it...")
            driver.send(Withdraw())
            return low
        return None

    set_search_addr(driver, high)
    response = driver.send(Compare())

    if response.value is True:
        midpoint = (low + high) // 2
        return find_next(driver, low, midpoint) or find_next(driver, midpoint + 1, high)
    return None


def scan(driver: SyncDALIDriver) -> typing.List[int]:
    """Check which short addresses have already been assigned"""
    devices = []
    for short_address in range(64):
        response = driver.send(QueryControlGearPresent(Short(short_address)))
        if response.value:
            devices.append(short_address)
    return devices


def assign_short_addresses(driver: SyncDALIDriver) -> typing.List[int]:
    """
    Assign short addresses to devices on DALI based interfaced by interface.
    """
    logger.info("Scanning for existing addresses ...")
    # Check for addresses which were already assigned short addresses
    used_addresses = scan(driver)
    logger.info(f"Addresses already in use: {used_addresses}")
    # Available is the remainder ...
    available = set(range(64)) - set(used_addresses)
    new_addresses: typing.List[int] = []
    logger.debug(f"Available addresses: {available}")

    # Assign random long addresses
    logger.info("Randomize addresses ...")
    driver.send(Terminate())
    # Broadcast = False means only ballasts without an assigned address shall react!
    driver.send(Initialise(broadcast=False, address=None))
    driver.send(Randomise())
    time.sleep(0.1)  # Randomise may take up to 100ms

    logger.info("Starting sweep ...")
    low: int | None = 0
    high = 0xFFFFFF
    while low is not None:
        logger.info(f"Search from next low address: {low}")
        low = find_next(driver, low, high)
        logger.debug(f"New low: {low}")
        if low is not None:
            if available:
                new_addr = available.pop()
                driver.send(ProgramShortAddress(new_addr))
                response = driver.send(VerifyShortAddress(new_addr))
                if response.value is not True:
                    logger.warning(f"Short address assignment for {new_addr} ws not verified, proceeding anyway ...")
                driver.send(Withdraw())
                new_addresses.append(new_addr)
            else:
                driver.send(Terminate())
                raise Exception("No free addresses left!")
            low = low + 1
    driver.send(Terminate())

    if new_addresses:
        logger.info(f"Addresses assigned: {new_addresses}")
    else:
        logger.info("Did not assign any new addresses")
    logger.info("Finished!")

    return new_addresses


if __name__ == "__main__":
    driver = SyncUnipiDALIDriver()
    assign_short_addresses(driver)
