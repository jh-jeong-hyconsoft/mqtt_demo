#!/usr/bin/env python3
import argparse
import json
import ssl
import sys
import threading
import time
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = BASE_DIR / "config"
DEFAULT_LOG_FILE = BASE_DIR / "logs" / "mqtt_messages.jsonl"
DEFAULT_CA_FILE = BASE_DIR.parent / "mqtt_broker" / "certs" / "ca.crt"
SCHEMA_VERSION = 0.3


def load_json_file(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_schema(path):
    return load_json_file(path)


def load_topic_config(path):
    return load_json_file(path)


def find_topic_config_entry(topic_config, section, schema_key):
    for entry in topic_config.get(section, []):
        if entry.get("schema_key") == schema_key:
            return entry
    raise ValueError(f"No topic config entry for {section}.{schema_key}")


def format_topic(template, fleet_id, device_id):
    return template.format(fleet_id=fleet_id, device_id=device_id)


def command_topic(topic_config, fleet_id, device_id):
    entry = find_topic_config_entry(topic_config, "inbound", "command")
    return format_topic(entry["mqtt_topic"], fleet_id=fleet_id, device_id=device_id)


def command_publish_options(topic_config):
    entry = find_topic_config_entry(topic_config, "inbound", "command")
    return {
        "qos": int(entry.get("qos", 0)),
        "retain": bool(entry.get("retain", False)),
    }


LOG_TOPIC_FILTERS = ("state", "presence", "event", "ack")


def robot_log_topics(topic_config, fleet_id="+", device_id="+", schema_keys=None):
    schema_key_filter = set(schema_keys or [])
    topics = []
    seen = set()
    for entry in topic_config.get("outbound", []):
        schema_key = entry.get("schema_key")
        if schema_key_filter and schema_key not in schema_key_filter:
            continue

        mqtt_topic = entry.get("mqtt_topic")
        qos = int(entry.get("qos", 0))
        if mqtt_topic:
            topic = format_topic(mqtt_topic, fleet_id=fleet_id, device_id=device_id)
            key = (topic, qos)
            if key not in seen:
                seen.add(key)
                topics.append(key)
    return topics


def selected_log_schema_keys(args):
    return [schema_key for schema_key in LOG_TOPIC_FILTERS if getattr(args, schema_key, False)]


def normalize_command_payload(payload, command_id=None):
    if not isinstance(payload, dict):
        raise ValueError("Command payload JSON must be an object")

    normalized = dict(payload)
    if command_id is not None:
        normalized["command_id"] = command_id
    elif "command_id" not in normalized:
        normalized["command_id"] = str(uuid.uuid4())

    return normalized


def build_command_message(
    payload,
    fleet_id,
    device_id,
    session_id=None,
    now_ms=None,
    message_uuid=None,
    command_id=None,
):
    message_uuid = message_uuid or str(uuid.uuid4())
    session_id = session_id or str(uuid.uuid4())
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)

    return {
        "msg_schema_version": SCHEMA_VERSION,
        "msg_id": f"command_{message_uuid}",
        "msg_ts_ms": now_ms,
        "msg_type": "command",
        "device_id": device_id,
        "fleet_id": fleet_id,
        "connectivity": "online",
        "session_id": session_id,
        "msg_payload": normalize_command_payload(payload, command_id=command_id),
    }


def validate_message(message, schema):
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(message), key=lambda error: list(error.path))
    if not errors:
        return

    messages = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{location}: {error.message}")
    raise ValueError("Schema validation failed:\n" + "\n".join(messages))


def build_log_record(topic, payload_bytes, qos, retain, received_ts_ms=None):
    received_ts_ms = int(received_ts_ms if received_ts_ms is not None else time.time() * 1000)
    payload_raw = payload_bytes.decode("utf-8", errors="replace")
    record = {
        "received_ts_ms": received_ts_ms,
        "topic": topic,
        "qos": qos,
        "retain": retain,
        "payload_raw": payload_raw,
        "payload": None,
    }

    try:
        record["payload"] = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        record["payload_parse_error"] = str(exc)

    return record


def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def encode_payload(message):
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def mqtt_success(reason_code):
    try:
        return int(reason_code) == 0
    except (TypeError, ValueError):
        return str(reason_code).lower() in {"success", "0"}


def create_mqtt_client(client_id):
    from paho.mqtt import client as mqtt

    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


def configure_mqtt_security(client, username=None, password=None, ca_file=None, insecure=False):
    if username is not None:
        client.username_pw_set(username, password=password)

    if ca_file:
        ca_path = Path(ca_file)
        if not ca_path.is_file():
            raise FileNotFoundError(f"CA file not found: {ca_path}")
        client.tls_set(ca_certs=str(ca_path), cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(insecure)


def connect_client(client, host, port, keepalive, timeout_s):
    connected = threading.Event()
    errors = []

    def on_connect(_client, _userdata, _flags, reason_code, _properties=None):
        if mqtt_success(reason_code):
            connected.set()
        else:
            errors.append(f"MQTT connect failed: {reason_code}")
            connected.set()

    client.on_connect = on_connect
    client.connect(host, port, keepalive)
    client.loop_start()

    if not connected.wait(timeout_s):
        client.loop_stop()
        raise TimeoutError(f"Timed out connecting to MQTT broker {host}:{port}")
    if errors:
        client.loop_stop()
        raise RuntimeError(errors[0])


def publish_command(args):
    config_dir = Path(args.config_dir)
    topic_config = load_topic_config(config_dir / "topic_config.json")
    schema = load_schema(config_dir / "schema_v0.3_validation.json")
    payload = load_json_file(args.payload)
    message = build_command_message(
        payload=payload,
        fleet_id=args.fleet_id,
        device_id=args.device_id,
        session_id=args.session_id,
        command_id=args.command_id,
    )
    validate_message(message, schema)

    topic = command_topic(topic_config, fleet_id=args.fleet_id, device_id=args.device_id)
    publish_options = command_publish_options(topic_config)
    client_id = args.client_id or f"server-publisher-{uuid.uuid4()}"
    client = create_mqtt_client(client_id)
    configure_mqtt_security(client, username=args.username, password=args.password, ca_file=args.ca_file, insecure=args.insecure)

    try:
        connect_client(client, args.host, args.port, args.keepalive, args.timeout)
        info = client.publish(
            topic,
            encode_payload(message),
            qos=publish_options["qos"],
            retain=publish_options["retain"],
        )
        info.wait_for_publish(timeout=args.timeout)
        if not info.is_published():
            raise TimeoutError(f"Timed out publishing command to {topic}")
    finally:
        client.loop_stop()
        client.disconnect()

    print(json.dumps({"published": True, "topic": topic, "message": message}, ensure_ascii=False, indent=2))


def log_messages(args):
    config_dir = Path(args.config_dir)
    topic_config = load_topic_config(config_dir / "topic_config.json")
    schema_keys = selected_log_schema_keys(args)
    topics = robot_log_topics(
        topic_config,
        fleet_id=args.fleet_id,
        device_id=args.device_id,
        schema_keys=schema_keys,
    )
    if not topics:
        if schema_keys:
            raise ValueError(f"No robot log topics found for: {', '.join(schema_keys)}")
        raise ValueError("No robot log topics found in topic_config.json outbound section")

    log_file = Path(args.log_file)
    client_id = args.client_id or f"server-logger-{uuid.uuid4()}"
    client = create_mqtt_client(client_id)
    configure_mqtt_security(client, username=args.username, password=args.password, ca_file=args.ca_file, insecure=args.insecure)

    def on_connect(mqtt_client, _userdata, _flags, reason_code, _properties=None):
        if not mqtt_success(reason_code):
            print(f"MQTT connect failed: {reason_code}", file=sys.stderr)
            return
        mqtt_client.subscribe(topics)
        for topic, qos in topics:
            print(f"subscribed topic={topic} qos={qos}", flush=True)

    def on_message(_client, _userdata, message):
        record = build_log_record(
            topic=message.topic,
            payload_bytes=message.payload,
            qos=message.qos,
            retain=message.retain,
        )
        append_jsonl(log_file, record)
        print(json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, args.keepalive)

    print(f"logging to {log_file}", flush=True)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nstopping logger", flush=True)
    finally:
        client.disconnect()


def build_parser():
    parser = argparse.ArgumentParser(description="Server-side MQTT client for command publishing and robot message logging")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR), help="Directory containing topic_config.json and schema_v0.3_validation.json")

    subparsers = parser.add_subparsers(dest="command", required=True)

    publish_parser = subparsers.add_parser("publish", help="Publish a command message from a payload-only JSON file")
    add_mqtt_args(publish_parser)
    publish_parser.add_argument("--fleet-id", required=True, help="Fleet ID used in the MQTT topic and message envelope")
    publish_parser.add_argument("--device-id", required=True, help="Device ID used in the MQTT topic and message envelope")
    publish_parser.add_argument("--payload", required=True, help="Path to payload-only command JSON")
    publish_parser.add_argument("--session-id", help="Session UUID for the message envelope; generated when omitted")
    publish_parser.add_argument("--command-id", help="Command UUID to place inside msg_payload; generated when payload omits command_id")
    publish_parser.set_defaults(func=publish_command)

    log_parser = subparsers.add_parser("log", help="Subscribe to robot topics and write JSONL logs")
    add_mqtt_args(log_parser)
    log_parser.add_argument("--fleet-id", default="+", help="Fleet ID topic filter; default subscribes to all fleets")
    log_parser.add_argument("--device-id", default="+", help="Device ID topic filter; default subscribes to all devices")
    log_parser.add_argument("--log-file", default=str(DEFAULT_LOG_FILE), help="JSON Lines log output path")
    log_parser.set_defaults(func=log_messages)

    log_subparsers = log_parser.add_subparsers(dest="log_command")
    topic_parser = log_subparsers.add_parser("topic", help="Subscribe only to selected robot message topics")
    log_filter_group = topic_parser.add_argument_group("topic filters")
    for schema_key in LOG_TOPIC_FILTERS:
        log_filter_group.add_argument(
            f"--{schema_key}",
            action="store_true",
            help=f"Subscribe only to robot {schema_key} messages; can be combined with other log filters",
        )
    topic_parser.set_defaults(func=log_messages)

    return parser


def add_mqtt_args(parser):
    parser.add_argument("--host", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port")
    parser.add_argument("--keepalive", type=int, default=60, help="MQTT keepalive seconds")
    parser.add_argument("--timeout", type=float, default=5.0, help="Connect/publish timeout seconds")
    parser.add_argument("--client-id", help="MQTT client ID; generated when omitted")
    parser.add_argument("--username", default="server", help="MQTT username")
    parser.add_argument("--password", default="1234", help="MQTT password")
    parser.add_argument("--ca-file", default=str(DEFAULT_CA_FILE), help="CA certificate for TLS broker verification")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS hostname verification")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
