# mqttdali

Small wrapper script that bridges between (home assistant) MQTT commands and the unipi DALI controller.

## Quickstart

Install dependencies in virtualenv

    poetry install

Run main command

    poetry run python mqttdali.py {mqtt.example.com}

## Virtualenv installation

Create a virtualenv

    python3 -m venv {venv-folder}

Active

    source {venv-folder}/bin/activate

Install the full package

    python3 python setup.py install

Run `mqttdali`:

    {venv-folder}/bin/mqttdali {mqtt.example.com}

## Sample systemd unit file

```
[Unit]
Description=mqttdali
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/mqttdali/bin/mqttdali emqx.broker.com
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```
