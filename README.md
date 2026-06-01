# MQTT Broker / Server Client 사용 가이드

이 문서는 `mqtt_broker` Docker 브로커와 `mqtt_client/server_client.py`를 username/password 인증 + TLS 방식으로 사용하는 방법을 정리합니다.

현재 기본 접속값은 다음과 같습니다.

- Broker host: `localhost`
- Broker port: `8883`
- Username: `server`
- Password: `1234`
- CA file: `/home/hycon-server/mqtt_demo/mqtt_broker/certs/ca.crt`

`1234`는 개발용 예시 비밀번호입니다. 실제 배포 환경에서는 더 긴 비밀번호를 사용하고, `passwd`, `certs`, `private` 디렉터리는 절대 Git에 올리지 마세요.

## Git Ignore 정책

다음 파일과 디렉터리는 `.gitignore`에 등록되어 있습니다.

- Codex/Serena 부산물: `.serena/`, `docs/superpowers/`
- MQTT 민감 자료: `mqtt_broker/certs/`, `mqtt_broker/private/`, `mqtt_broker/config/passwd`
- MQTT 런타임 자료: `mqtt_broker/data/`, `mqtt_broker/log/`, `mqtt_client/logs/`
- Python 부산물: `__pycache__/`, `*.pyc`, `.venv/`

이미 Git에 추적된 파일은 `.gitignore`만으로 제거되지 않습니다. 이미 추적 중인 민감 파일이 있다면 다음처럼 index에서 제거해야 합니다.

```bash
git rm --cached -r mqtt_broker/certs mqtt_broker/private mqtt_broker/data mqtt_broker/log
git rm --cached mqtt_broker/config/passwd
```

## Broker 디렉터리 구조

```text
mqtt_broker/
  config/
    mosquitto.conf
    passwd              # Git 제외
  certs/                # Git 제외
    ca.crt
    server.crt
    server.key
  private/              # Git 제외
    ca.key
    server.csr
    server_ext.cnf
  data/                 # Git 제외
  log/                  # Git 제외
  docker-compose.yml
```

## Password 파일 생성

`server / 1234` 계정을 새로 만들거나 덮어쓰려면 다음을 실행합니다.

```bash
cd /home/hycon-server/mqtt_demo/mqtt_broker
mkdir -p config

docker run --rm \
  -v "$PWD/config:/mosquitto/config" \
  eclipse-mosquitto:2.0.11 \
  mosquitto_passwd -c -b /mosquitto/config/passwd server 1234
```

기존 `passwd` 파일에 사용자를 추가하려면 `-c`를 빼고 실행합니다.

```bash
docker run --rm \
  -v "$PWD/config:/mosquitto/config" \
  eclipse-mosquitto:2.0.11 \
  mosquitto_passwd -b /mosquitto/config/passwd another_user another_password
```

## TLS 인증서 생성

아래 명령은 개발/테스트용 자체 서명 CA와 서버 인증서를 생성합니다.

```bash
cd /home/hycon-server/mqtt_demo/mqtt_broker
mkdir -p certs private

openssl genrsa -out private/ca.key 4096
openssl req -x509 -new -nodes \
  -key private/ca.key \
  -sha256 \
  -days 3650 \
  -out certs/ca.crt \
  -subj "/C=KR/O=Hycon/OU=MQTT/CN=Hycon MQTT Test CA"
```

서버 인증서에 넣을 주소를 `private/server_ext.cnf`에 작성합니다. 클라이언트가 접속할 host/IP가 SAN에 반드시 포함되어야 합니다.

```bash
cat > private/server_ext.cnf <<'EOF'
subjectAltName = DNS:localhost,IP:127.0.0.1,IP:192.168.0.12,IP:218.236.78.9
EOF
```

서버 key/csr/crt를 생성합니다.

```bash
openssl genrsa -out certs/server.key 2048
openssl req -new \
  -key certs/server.key \
  -out private/server.csr \
  -subj "/C=KR/O=Hycon/OU=MQTT/CN=localhost"

openssl x509 -req \
  -in private/server.csr \
  -CA certs/ca.crt \
  -CAkey private/ca.key \
  -CAcreateserial \
  -out certs/server.crt \
  -days 825 \
  -sha256 \
  -extfile private/server_ext.cnf
```

인증서 내용을 확인합니다.

```bash
openssl x509 -in certs/server.crt -noout -subject -issuer -ext subjectAltName
```

## Mosquitto 설정

`mqtt_broker/config/mosquitto.conf`는 TLS와 password 인증을 사용합니다.

```conf
listener 8883 0.0.0.0
protocol mqtt

certfile /mosquitto/certs/server.crt
keyfile /mosquitto/certs/server.key

allow_anonymous false
password_file /mosquitto/config/passwd

persistence true
persistence_location /mosquitto/data/

log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
connection_messages true
```

## Docker Broker 실행

```bash
cd /home/hycon-server/mqtt_demo/mqtt_broker
docker compose up -d
```

상태 확인:

```bash
docker compose ps
docker logs -f mqtt_broker
```

재시작:

```bash
docker compose restart
```

중지:

```bash
docker compose down
```

설정, password, 인증서를 바꾼 뒤에는 broker를 재시작하세요.

```bash
docker compose restart mqtt_broker
```

## Python Client 준비

```bash
cd /home/hycon-server/mqtt_demo/mqtt_client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Command 발행

입력 JSON은 전체 MQTT envelope가 아니라 `msg_payload` 내용만 담습니다. `server_client.py`가 envelope를 채우고 schema 검증 후 publish합니다.

```bash
cd /home/hycon-server/mqtt_demo/mqtt_client
source .venv/bin/activate

python server_client.py publish \
  --host localhost \
  --fleet-id fleet-a \
  --device-id robot-1 \
  --payload samples/command_payload_move_to.json
```

기본값을 명시해서 실행하면 다음과 같습니다.

```bash
python server_client.py publish \
  --host localhost \
  --port 8883 \
  --username server \
  --password 1234 \
  --ca-file /home/hycon-server/mqtt_demo/mqtt_broker/certs/ca.crt \
  --fleet-id fleet-a \
  --device-id robot-1 \
  --payload samples/command_payload_move_to.json
```

## Robot 메시지 로그 구독

모든 fleet/device를 구독합니다.

```bash
cd /home/hycon-server/mqtt_demo/mqtt_client
source .venv/bin/activate

python server_client.py log --host localhost
```

특정 robot만 구독합니다.

```bash
python server_client.py log \
  --host localhost \
  --fleet-id fleet-a \
  --device-id robot-1
```

로그는 기본적으로 아래 파일에 JSON Lines 형식으로 저장됩니다.

```text
/home/hycon-server/mqtt_demo/mqtt_client/logs/mqtt_messages.jsonl
```

## Hostname 검증 문제

TLS 접속 시 `certificate verify failed` 또는 hostname mismatch가 나면, 접속에 사용한 host가 서버 인증서 SAN에 없는 것입니다.

권장 해결 방법:

1. 실제 접속 host/IP를 `private/server_ext.cnf`의 `subjectAltName`에 추가합니다.
2. 서버 인증서를 다시 생성합니다.
3. broker를 재시작합니다.

개발 중 임시 확인만 필요하면 `--insecure`로 hostname 검증을 끌 수 있습니다. 이 옵션은 실제 배포에서 사용하지 마세요.

```bash
python server_client.py publish \
  --host 218.236.78.9 \
  --insecure \
  --fleet-id fleet-a \
  --device-id robot-1 \
  --payload samples/command_payload_move_to.json
```

## 테스트

```bash
cd /home/hycon-server/mqtt_demo
python3 -m unittest discover -s mqtt_client/tests
```

전역 Python에 dependency가 없다면 venv를 사용합니다.

```bash
cd /home/hycon-server/mqtt_demo
mqtt_client/.venv/bin/python -m unittest discover -s mqtt_client/tests
```
