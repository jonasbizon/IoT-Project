import network
import time
import sys
from umqtt.simple import MQTTClient, MQTTException
import creds
import ujson
from GateController import GateController

# MQTT konstanty
__MQTT_PUB_TOPIC_1__ = b"v1/devices/me/telemetry"
__MQTT_SUB_TOPIC_1__ = b"v1/devices/me/attributes"
__MQTT_SUB_TOPIC_2__ = b"v1/devices/me/rpc/request/+"
__MQTT_RPC_PREFIX__ = b"v1/devices/me/rpc/request/"
__MQTT_ERRORS__ = [
    "Connection Accepted",
    "Connection Refused, Unacceptable Protocol Version",
    "Connection Refused, Identifier Rejected",
    "Connection Refused, Server Unavailable",
    "Connection Refused, Bad Username or Password",
    "Connection Refused, Not Authorized"
]
KEEPALIVE_S = 60

# WiFi konstanty
SSID = creds.WIFI_SSID
PASS = creds.WIFI_PWD

# připojení wifi
wlan = network.WLAN(network.STA_IF)
wlan.active(False)
time.sleep(1)
wlan.active(True)
time.sleep(0.5)
wlan.connect(SSID, PASS)

# čekání na připojení
print("WiFi: Připojování...")
while not wlan.isconnected():
    time.sleep(1)
print("WiFi: Připojeno. IP: ", wlan.ifconfig()[0])


def on_message_callback(topic, msg) -> None:
    print("MQTT: ", topic, msg)
    
    # pouze RPC požadavky z thingsboardu
    if not topic.startswith(__MQTT_RPC_PREFIX__):
        return
    
    # zpracování požadavku
    try:
        js = ujson.loads(msg)
        cmd = js.get("params", {}).get("gate_command")
        if cmd:
            gate.set_command(cmd)
        else:
            print("MQTT: Neplatný command.")

    except Exception as e:
        print("MQTT: Chyba při zpracování zprávy: ", e)

# MQTT
client = MQTTClient(
    creds._MQTT_CLIENT_ID_,
    creds._MQTT_REMOTE_SERVER_IP_, 
    user=creds._MQTT_ACCESS_TOKEN_, 
    password=creds._MQTT_PASSWORD_,
    keepalive=KEEPALIVE_S, 
    port=creds._MQTT_REMOTE_SERVER_PORT_
)
client.set_callback(on_message_callback)

# připojení MQTT
try:
     client.connect()
     client.subscribe(__MQTT_SUB_TOPIC_1__)
     client.subscribe(__MQTT_SUB_TOPIC_2__)
except MQTTException as mqtte:
     print(f"MQTT: MQTTException {mqtte} - {__MQTT_ERRORS__[int(str(mqtte))]}")
     sys.exit(1)    # ukončení programu při chybě
except Exception as e:
     print("MQTT: Chyba pripojeni: ", e)
     sys.exit(1)    # ukončení programu při chybě

print("MQTT: připojeno")

# ovladač brány
gate = GateController(client, wlan)



# keepalive ping nastavení
mqtt_ctr = 0
ping_interval_ticks = int((KEEPALIVE_S - 2) / 0.1)

# hlavní cyklus
while True:
    try:
        # ovládání brány
        client.check_msg()  # kontrolá zprávy
        gate.check()        # kontrola stavu brány

        # keepalive ping
        mqtt_ctr = mqtt_ctr+1
        if mqtt_ctr >= ping_interval_ticks:
            mqtt_ctr = 0
            client.ping()
        
        # 100 ms čekání
        time.sleep(0.1)

    except KeyboardInterrupt:
        print("Keyboard Interrupt.")
        break
    except Exception as exception:
        print("Error: " + str(exception))
        print("a")
        
client.disconnect()
