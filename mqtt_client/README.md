# MQTT Server Client

This client is for the server side of the MQTT ICD.

- Publish: sends only `command` messages to `server/{fleet_id}/{device_id}/command`.
- Log: subscribes to robot `state`, `presence`, `event`, and `ack` topics and writes JSONL logs.

## Start Broker

```bash
cd /home/hycon_ubuntu/workspace/docker_ws/mqtt_broker
docker compose up -d
```

The broker listens on `localhost:1883`.

If another broker is already using port `1883`, run this workspace broker on another host port:

```bash
cd /home/hycon_ubuntu/workspace/docker_ws/mqtt_broker
MQTT_PORT=1884 MQTT_WS_PORT=9002 docker compose up -d
```

## Create Python venv

```bash
cd /home/hycon_ubuntu/workspace/docker_ws/mqtt_client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Log Robot Messages

Subscribe to every fleet and device:

```bash
python server_client.py log --host localhost
```

Subscribe to one robot:

```bash
python server_client.py log --host localhost --fleet-id fleet-a --device-id robot-1
```

Logs are appended to `mqtt_client/logs/mqtt_messages.jsonl`.

## Publish Command

The input file is `msg_payload` only. The client fills the envelope fields and validates the full message before publish.

```bash
python server_client.py publish \
  --host localhost \
  --fleet-id fleet-a \
  --device-id robot-1 \
  --payload samples/command_payload_move_to.json
```

If `command_id` is missing in the payload file, the client generates one.
