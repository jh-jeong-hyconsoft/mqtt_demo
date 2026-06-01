import json
import sys
import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import server_client


class ServerClientTests(unittest.TestCase):
    def setUp(self):
        self.config_dir = CLIENT_DIR / "config"

    def test_build_command_message_wraps_payload_only_json(self):
        payload = {
            "command_id": "11111111-1111-4111-8111-111111111111",
            "command_type": "move_to",
            "details": {
                "target": {
                    "lat": 37.1,
                    "lon": 127.2,
                    "alt_m": 12.3,
                }
            },
        }

        message = server_client.build_command_message(
            payload=payload,
            fleet_id="fleet-a",
            device_id="robot-1",
            session_id="22222222-2222-4222-8222-222222222222",
            now_ms=1234567890,
            message_uuid="33333333-3333-4333-8333-333333333333",
        )

        self.assertEqual(message["msg_schema_version"], 0.3)
        self.assertEqual(message["msg_id"], "command_33333333-3333-4333-8333-333333333333")
        self.assertEqual(message["msg_ts_ms"], 1234567890)
        self.assertEqual(message["msg_type"], "command")
        self.assertEqual(message["device_id"], "robot-1")
        self.assertEqual(message["fleet_id"], "fleet-a")
        self.assertEqual(message["connectivity"], "online")
        self.assertEqual(message["session_id"], "22222222-2222-4222-8222-222222222222")
        self.assertEqual(message["msg_payload"], payload)

    def test_command_topic_comes_from_topic_config(self):
        topic_config = server_client.load_topic_config(self.config_dir / "topic_config.json")

        topic = server_client.command_topic(
            topic_config=topic_config,
            fleet_id="fleet-a",
            device_id="robot-1",
        )

        self.assertEqual(topic, "server/fleet-a/robot-1/command")

    def test_robot_log_topics_deduplicates_same_mqtt_topic(self):
        topic_config = server_client.load_topic_config(self.config_dir / "topic_config.json")

        topics = server_client.robot_log_topics(
            topic_config=topic_config,
            fleet_id="fleet-a",
            device_id="robot-1",
        )

        self.assertEqual(
            topics,
            [
                ("robot/fleet-a/robot-1/state", 1),
                ("robot/fleet-a/robot-1/presence", 1),
                ("robot/fleet-a/robot-1/event", 1),
                ("robot/fleet-a/robot-1/ack", 1),
            ],
        )

    def test_generated_command_validates_against_schema(self):
        schema = server_client.load_schema(self.config_dir / "schema_v0.3_validation.json")
        payload = {
            "command_id": "11111111-1111-4111-8111-111111111111",
            "command_type": "pause",
        }
        message = server_client.build_command_message(
            payload=payload,
            fleet_id="fleet-a",
            device_id="robot-1",
            session_id="22222222-2222-4222-8222-222222222222",
            now_ms=1234567890,
            message_uuid="33333333-3333-4333-8333-333333333333",
        )

        server_client.validate_message(message, schema)

    def test_received_message_log_record_keeps_raw_and_parsed_payload(self):
        record = server_client.build_log_record(
            topic="robot/fleet-a/robot-1/state",
            payload_bytes=json.dumps({"msg_type": "state"}).encode("utf-8"),
            qos=1,
            retain=False,
            received_ts_ms=1234567890,
        )

        self.assertEqual(record["topic"], "robot/fleet-a/robot-1/state")
        self.assertEqual(record["qos"], 1)
        self.assertFalse(record["retain"])
        self.assertEqual(record["received_ts_ms"], 1234567890)
        self.assertEqual(record["payload"], {"msg_type": "state"})
        self.assertEqual(record["payload_raw"], '{"msg_type": "state"}')


if __name__ == "__main__":
    unittest.main()
