import machine
import ujson
import time
import neopixel

# konstanty
__MQTT_PUB_TOPIC_1__ = b"v1/devices/me/telemetry"   # publish topic pro thingsboard
__OBSTACLE_WAIT_TIME__ = 5000                       # doba čekání při překážce
__OBSTACLE_INIT_TIME__ = 5000                       # doba čekání při překážce
__PWM_DUTY_VALUE__ = 32768                          # hodnota střídy
__PWM_FREQ_VALUE__ = 1000                           # hodnota frekvence pwm

class GateController:
    def __init__(self, client, wlan) -> None:
        """ Inicializace třídy. """
        # vnitrni stavy brany
        self.state = "INIT"         # aktuální stav automatu
        self.init_time = time.ticks_ms()
        self.obstacle_time = None   # čas, kdy nastala překážka
        self.last_state = "INIT"    # poslední stav, pro spuštění po překážce

        # ovladani brany
        self.pwm_open = machine.PWM(machine.Pin(6), freq=__PWM_FREQ_VALUE__)  # pwm motoru při otevírání
        self.pwm_close = machine.PWM(machine.Pin(7), freq=__PWM_FREQ_VALUE__) # pwm motoru při zavírání
        self.np = neopixel.NeoPixel(machine.Pin(28), 1)             # RGB led
        self.obstacle = machine.Pin(20, machine.Pin.IN)             # snímač překážky
        self.limit_open = machine.Pin(21, machine.Pin.IN)           # koncový snímač při otevírání
        self.limit_close = machine.Pin(22, machine.Pin.IN)          # koncový snímač při zavírání

        # mqtt a wifi
        self.client = client    # mqtt klient
        self.wlan = wlan        # wifi
        
        # pocatecni report
        self.__report(status="Init", message={
            "Device_ID": "67", 
            "Firmware_ver": "1.0.2", 
            "Authors":  "256355, 256243, 247175",
            "Technology": "WiFi",
            "SSID": self.wlan.config('ssid'),
            "Channel": self.wlan.config('channel')
        })
        
        print('INIT: Inicializace brány.')
        self.np[0] = (0, 0, 128)
        self.np.write()
        
        
        
    def set_command(self, cmd: str) -> None:
        """ Přijímá a nastavuje příkazy z MQTT. """

        # blokace příkazů, pokuď je překážka
        if self.obstacle_time is not None:
            return

        # spusti otevirani brany
        if cmd == "OPEN":
            self.state = "OPENING"
            
            if self.limit_open.value():
                self.__report(status="Opening")
                print('RUN: Brána se otevírá.')

        # spusti zavirani brany
        elif cmd == "CLOSE":
            self.state = "CLOSING"
            
            if self.limit_close.value():
                self.__report(status="Closing")
                print('RUN: Brána se zavíra.')
        
        else:
            print(f"RUN: Neznámý příkaz: {cmd}.")
            

    def check(self):
        """ Stavový automat brány """

        # inicializace
        if self.state == "INIT":
            elapsed = time.ticks_diff(time.ticks_ms(), self.init_time)
            if elapsed > __OBSTACLE_INIT_TIME__:
                # brána není zavřená ani otevřená, začne se zavírat
                print('INIT: Nerozhodný stav brány, brána se zavírá')
                self.state = "CLOSING"
                self.__report(status="Closing")
                self.np[0] = (0, 0, 0)
                self.np.write()
                return
            else:
                # pokud je aktivní koncák, tak je brána otevřená
                if not self.limit_open.value():
                    self.__stop()
                    self.state = "STOP"
                    self.__report(status="Open")
                    print('INIT: Brána je otevřená.')
                    self.np[0] = (0, 0, 0)
                    self.np.write()
                    
                # pokud je aktivní koncák, tak je brána zavřená
                elif not self.limit_close.value():
                    self.__stop()
                    self.state = "STOP"
                    self.__report(status="Closed")
                    print('INIT: Brána je zavřená.')
                    self.np[0] = (0, 0, 0)
                    self.np.write()
                
        # blokace pri překážce
        if self.obstacle_time is not None:
            elapsed = time.ticks_diff(time.ticks_ms(), self.obstacle_time)
            if elapsed < __OBSTACLE_WAIT_TIME__:
                return
            else:
                print("RUN: Obnovuji pohyb, cas prekazky uplynul.")
                if not self.obstacle.value():
                    self.obstacle_time = time.ticks_ms()
                else:
                    self.np[0] = (0, 0, 0)
                    self.np.write()
                    self.obstacle_time = None
                    self.state = self.last_state
                    
                    if self.state == "OPENING":
                        self.__report(status="Opening")
                        print('RUN: Brána se otevírá.')
                    elif self.state == "CLOSING":
                        self.__report(status="Closing")
                        print('RUN: Brána se zavíra.')

        # otevírání brány
        if self.state == "OPENING":

            # brána je otevřená - koncák aktivní a nejde znovu otevřít
            if not self.limit_open.value():
                print("RUN: Otevřeno - koncový spínač.")
                self.__stop()
                self.state = "STOP"
                self.__report(status="Open")
                return
            
            # objevila se překážka, zastaví pohyb - není potřeba při otevírání
#             if not self.obstacle.value():
#                 print("Překážka")
#                 self.__stop()
#                 self.obstacle_time = time.ticks_ms()
#                 self.last_state = self.state
#                 self.__report(status="Obstacle")
#                 return
            
            # jinak se otevírá brána
            self.__open()
        
        # zavírání brány
        elif self.state == "CLOSING":
            # brána je zavřená - koncák aktivní a nejde znovu zavřít
            if not self.limit_close.value():
                print("RUN: Zavřeno - koncový spínač.")
                self.__stop()
                self.state = "STOP"
                self.__report(status="Closed")
                return
            
            # objevila se překážka, zastaví pohyb
            if not self.obstacle.value():
                print("RUN: Překážka.")
                self.__stop()
                self.obstacle_time = time.ticks_ms()
                self.last_state = self.state
                self.__report(status="Obstacle")
                self.np[0] = (128, 0, 0)
                self.np.write()
                return
            
            # jinak se zavírá brána
            self.__close()
        else:
            self.__stop()
           
           
    def __open(self) -> None:
        """ Spustí PWM pro otevření brány. """
        self.pwm_open.duty_u16(__PWM_DUTY_VALUE__)
        self.pwm_close.duty_u16(0)
        
        
    def __close(self) -> None:
        """ Spustí PWM pro zavření brány. """
        self.pwm_open.duty_u16(0)
        self.pwm_close.duty_u16(__PWM_DUTY_VALUE__)


    def __stop(self) -> None:
        """ Pomocná funkce pro zastavení obou motorů. """
        self.pwm_open.duty_u16(0)
        self.pwm_close.duty_u16(0)
    

    def __report(self, status: str, message: dict | None = None) -> None:
        """ Pomocna funkce pro poslani statusu. """
        json_string = {"Status": status, "RSSI": self.wlan.status("rssi")}
        if message:
            json_string.update(message)
        
        json = ujson.dumps(json_string)
        self.client.publish(__MQTT_PUB_TOPIC_1__, json)
        
