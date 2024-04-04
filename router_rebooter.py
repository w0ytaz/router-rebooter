import network
import socket
import urequests as requests
import ntptime
import time
from time import sleep
from machine import Pin, Timer
import gc


# ===== user config ====================================================================================================
ssid = 'SkyNetMobile'            		# wifi ssid, 2.4GHz
pwd = '1serafin@3'               		# wifi password
router_boot_time = 60               	# time in seconds for booting the router, setup and connection, probably 120-180
internet_ping_interval = 30       		# main loop ping interval in seconds
connection_wait_time = 10           	# timeout in seconds for wifi connection
failed_ping_wait_time = 5          		# time in seconds before next ping
max_wifi_failed_con_attempts = 3    	# wifi connection attempts before relay power restart
max_internet_failed_con_attempts = 3  	# ping connection attempts before relay power restart
time_offset = 2							# time offset for time change 1 for CET 2 for CEST
# ======================================================================================================================


# setup
sta_if = network.WLAN(network.STA_IF)  # wifi connection object
relay = Pin(6, Pin.OUT)                # router power relay pin
led = Pin("LED", Pin.OUT)              # LED pin for blinking according to status
tim = Timer()                          # hardware timer used for blinking the LED
state = "no-wifi"                      # initial state
wifi_failed_con_attempts = 0           # set initial counter value
internet_failed_con_attempts = 0       # set initial counter value
failures = []                          # list that contains failures dates limited to 3 entries
google = "https://www.google.com"
cloudflare = "https://one.one.one.one"
quad9 = "https://on.quad9.net"


def time_stamp():
    now = time.localtime()
    day = now[2]
    month = now[1]
    year = now[0]
    hour = now[3] + time_offset
    minutes = now[4]
    sec = now[5]
    timestamp = f"{year}.{month:02}.{day:02} {hour:02}:{minutes:02}:{sec:02}"
    return timestamp

def restart_relay_and_boot(restart=True):
    """
    Restart relay/router and wait for booting. For power saving purpose relay on/off are inverted.
    :param restart:
        If False then just wait for booting (used for initial waiting)
    :return:
        None
    """
    tim.init(period=500, mode=Timer.PERIODIC, callback=lambda t: led.toggle())
    if restart:
        relay.on()  # on and off are inverted, on means off
        # wait some time to completely switch off
        for i in range(10, 0, -1):
            print('keeping the switch off: {:>2.0f}'.format(i), end='\r')
            sleep(1)
    relay.off()  # on and off are inverted, off means on
    for i in range(router_boot_time, 0, -1):
        print('waiting for booting the router: {:>2.0f}'.format(i), end='\r')
        sleep(1)


def check_inet(url: str):
    """
    Check if the HTTP status code is 200 and return True or False
    :return:
        True/False according to connection status
    """
    # print("Testing:",url)
    time.sleep(1)
    gc.collect()
    try:
        response = requests.get(url,timeout=5)
        response_code = response.status_code
        # gc.collect()
        if response_code == 200:
            return True
        else:
            return False
    except Exception as e:
        timestamp = time_stamp()
        print(f"{timestamp} Failed: {url} Fatal error: {e}")
        # gc.collect()
        return False
    

def ping():
    """
    Check if the Internet is available and return True or False
    If False create timestamp an add it to the failures list
    :return:
        True/False according to connection status
    """
    if (check_inet(google) or check_inet(cloudflare) or check_inet(quad9)):
        return True
    else:
        timestamp = time_stamp()
        if len(failures) == 3:
            failures.pop(2)
        failures.insert(0,timestamp)
        return False


# turn on the router and wait for booting
restart_relay_and_boot(restart=False)

# the main loop
gc.enable()
while True:
    timestamp = time_stamp()
    year = time.localtime()[0]
    last_failures = "None" if len(failures) == 0 else ",".join(str(fail) for fail in failures)
    print(f"{timestamp}: state = {state}, wifi_failed_con_attempts = {wifi_failed_con_attempts}, internet_failed_con_attempts = {internet_failed_con_attempts}, Last failures: {last_failures}")
    if state == "no-wifi":
        sta_if.active(True)
        sta_if.connect(ssid, pwd)

        # wait for handshake and establishing the connection
        tim.init(period=200, mode=Timer.PERIODIC, callback=lambda t: led.toggle())
        for i in range(connection_wait_time, 0, -1):
            print('waiting for connection: {:>2.0f}'.format(i), end='\r')
            sleep(1)

            if sta_if.isconnected():
                state = "wifi-connected"
                wifi_failed_con_attempts = 0
                if year == 2021:
                    try:
                        ntptime.settime()
                    except:
                        pass
                break

        if not sta_if.isconnected():
            wifi_failed_con_attempts += 1
            if wifi_failed_con_attempts >= max_wifi_failed_con_attempts:
                wifi_failed_con_attempts = 0
                restart_relay_and_boot()  # wifi not available, restart the router
    elif state == "wifi-connected":
        if sta_if.isconnected():
            if ping():
                tim.init(period=2000, mode=Timer.PERIODIC, callback=lambda t: led.toggle())
                internet_failed_con_attempts = 0
                for i in range(internet_ping_interval, 0, -1):
                    print('ping succeed, waiting for next ping: {:>2.0f}'.format(i), end='\r')
                    sleep(1)
            else:
                tim.init(period=200, mode=Timer.PERIODIC, callback=lambda t: led.toggle())
                internet_failed_con_attempts += 1
                if internet_failed_con_attempts >= max_internet_failed_con_attempts:
                    # restart the router
                    internet_failed_con_attempts = 0
                    state = "no-wifi"
                    restart_relay_and_boot()
                else:
                    # wait before next ping
                    for i in range(failed_ping_wait_time, 0, -1):
                        print('ping failed {:>.0f}/{:>.0f}, waiting for next ping attempt before restart: {:>2.0f}'.format(internet_failed_con_attempts, max_internet_failed_con_attempts, i), end='\r')
                        sleep(1)
        else:
            state = "no-wifi"  # if wifi connection broken go to the other state
