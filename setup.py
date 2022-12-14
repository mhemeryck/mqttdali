import setuptools

setuptools.setup(
    name="mqttdali",
    version="0.2",
    description="Translate MQTT events into DALI bus events",
    url="https://github.com/mhemeryck/mqttdali",
    install_requires=(
        "asyncio-mqtt>=0.12",
        "paho-mqtt>=1.6",
        "pymodbus>=2.5",
        "python-dali>=0.9",
        "pyusb>=1.2",
        "pyserial>=3.5",
    ),
    author="Martijn Hemeryck",
    license="MIT",
    zip_safe=True,
    py_modules=["mqttdali", "cli"],
    entry_points={
        "console_scripts": [
            "salvador=cli:main",
            "mqttdali=mqttdali:main",
        ]
    },
)
