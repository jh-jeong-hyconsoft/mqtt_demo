# MQTT Server Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Docker MQTT broker and a venv-friendly Python server client with logging and command publish features.

**Architecture:** Use Eclipse Mosquitto for the broker. Use one Python CLI file for both server-client modes, with pure helper functions covered by unit tests and Paho MQTT used only at the CLI network boundary.

**Tech Stack:** Docker Compose, Eclipse Mosquitto, Python 3, paho-mqtt, jsonschema, unittest.

---

### Task 1: Broker Docker Configuration

**Files:**
- Create: `mqtt_broker/docker-compose.yml`
- Create: `mqtt_broker/config/mosquitto.conf`

- [ ] Add a Mosquitto service exposing ports `1883` and `9001`.
- [ ] Add a local-development Mosquitto config that allows anonymous clients.

### Task 2: Server Client Tests

**Files:**
- Create: `mqtt_client/tests/test_server_client.py`

- [ ] Test command envelope generation from payload-only JSON data.
- [ ] Test topic formatting from `topic_config.json`.
- [ ] Test schema validation accepts a generated command.
- [ ] Test received-message log record formatting.

### Task 3: Server Client Implementation

**Files:**
- Create: `mqtt_client/server_client.py`
- Create: `mqtt_client/requirements.txt`
- Create: `mqtt_client/samples/command_payload_move_to.json`

- [ ] Implement config loading.
- [ ] Implement command envelope generation.
- [ ] Implement schema validation.
- [ ] Implement `publish` and `log` CLI subcommands.
- [ ] Add a payload-only sample command JSON file.

### Task 4: Documentation and Verification

**Files:**
- Create: `mqtt_client/README.md`

- [ ] Document venv setup, broker startup, logging, and publish commands.
- [ ] Run unit tests.
- [ ] Run CLI help commands.
