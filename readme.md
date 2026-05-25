# Bezdrátový přijímač pro otevírání vjezdové brány

## Důvod výběru technologie a protokolu
### WiFi
* napájení 230V/50Hz - není omezené baterií
* svolení majitele doinstalovat AP

### MQTT
* udržuje trvalé spojení
* režie protokolu je s WiFi zanedbatelná
* jednoduché využití v ThingsBoardu

## Struktura kódu

```
projekt_main.py     # připojení WiFi, MQTT a nekonečná smyčka
GateController.py   # logika ovládání brány
creds.py            # přihlašovací údaje
```

## Hardware piny

| Komponenta | Pin |
|---|---|
| PWM motor – otevírání | GP6 |
| PWM motor – zavírání | GP7 |
| RGB LED (NeoPixel) | GP28 |
| Snímač překážky | GP20 |
| Koncový snímač – otevřeno | GP21 |
| Koncový snímač – zavřeno | GP22 |

# creds.py

```python
WIFI_SSID = "ssid"
WIFI_PWD  = "pwd"
_MQTT_REMOTE_SERVER_IP_ = "ip"
_MQTT_REMOTE_SERVER_PORT_ = 0
_MQTT_CLIENT_ID_ = "client_id"
_MQTT_ACCESS_TOKEN_ = "access_token"
_MQTT_PASSWORD_ = ""
```

# projekt_main.py

Hlavní program obsahující nastavení a připojení WiFi a MQTT. Inicializuje třídu GateController a v nekonečné smyčce zpracovává příkazy z Thingsboardu.

## Konstanty
| Konstanta | Hodnota | Popis |
|---|---|---|
| `__MQTT_PUB_TOPIC_1__` | b"v1/devices/me/telemetry" | Publish topic do ThingsBoardu |
| `__MQTT_SUB_TOPIC_1__` | b"v1/devices/me/attributes" | Subscribe topic pro atributy z ThingsBoardu |
| `__MQTT_SUB_TOPIC_2__` | b"v1/devices/me/rpc/request/+" | Subscribe topic pro RPC commandy z ThingsBoardu |
| `__MQTT_RPC_PREFIX__` | b"v1/devices/me/rpc/request/" | Prefix request topicu, pro detekci v callbacku |
| `KEEPALIVE_S` | 60 s | Interval keepalive pingu |

## on_message_callback()
Funkce kontroluje jestli přišla zpráva z MQTT s topicem `__MQTT_RPC_PREFIX__` a příkazy k ovládání brány předává ovladači brány.

# GateController.py

Třída pro ovládání brány. Obsahuje všechny řídící prvky a funkce k automatickému řízení. Při každé změně stavu posílá report o stavu, spolu s RSSI:
```json
{"Status": "Opening", "RSSI": number}
```
Možné hodnoty `Status`: `Init`, `Opening`, `Closing`, `Open`, `Closed`, `Obstacle`. 

## Konstanty
| Konstanta | Hodnota | Popis |
|---|---|---|
| `__OBSTACLE_WAIT_TIME__` | 5000 ms | Doba blokace při detekci překážky |
| `__OBSTACLE_INIT_TIME__` | 5000 ms | Doba inicializace |
| `__PWM_DUTY_VALUE__` | 32768 | Střída PWM (0–65535) |
| `__PWM_FREQ_VALUE__` | 1000 Hz | Frekvence PWM |

## \_\_init\_\_
Inicializuje třídu - načte ovládací prvky brány, proměnné a pošle počáteční report obsahující informace o stavu, zařízení a technologii:
```json
{
    "Status": "Init", 
    "RSSI": number, 
    "Device_ID": "67", 
    "Firmware_ver": "1.0.2", 
    "Authors": "256355, 256243, 247175", 
    "Technology": "WiFi", 
    "SSID": string,
    "Channel": number
}
```

## set_command()
Příjme příkaz z MQTT a nastaví stav na otevírání nebo zavírání. Podporované příkazy: `OPEN`, `CLOSE`.

## check()
Ovládá logiku stavového automatu. Nejprve kontroluje stav `INIT`, kde se kontroluje, jestli je brána zavřená nebo otevřená. Pokud není ani jeden z koncových spínačů aktivní do 5 sekund, začne se brána zavírat. 

Poté následuje logika blokování při překážce, která funguje pouze při zavírání brány. Blokace trvá definovanou dobu `__OBSTACLE_WAIT_TIME__` (5 sekund). Pokud se překážka neodstraní, následuje další blokace, až dokud se neodstraní překážka. Poté pokračuje v pohybu.

Následně je zbytek automatu, který se stará o otevírání a zavírání brány.

### Logika stavového automatu
```
              start
                │
              INIT ───── limit_open ──→ STOP (Open)
                │
                ├─────── limit_close ──→ STOP (Closed)
                │
                └─────── timeout 5s ──────→ CLOSING
 
MQTT cmd OPEN ──→ limit_open ──→ STOP (Open)
                │
                └── else ──→ OPENING
                                │
                                ├── limit_open ──→ STOP (Open)
                                │
                                └── else ──→ otevírá (__open())
 
MQTT cmd CLOSE ──→ limit_close ──→ STOP (Closed)
                │
                └── else ──→ CLOSING
                                │
                                ├── limit_close ──→ STOP (Closed)
                                │
                                ├── obstacle ──→ timeout 5s ──→ pokračuje (CLOSING)
                                │
                                └── else ──→ zavírá (__close())
```