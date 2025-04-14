import helpers
import network
import os
import onewire, ds18x20
import time
from emc2301.emc2301 import EMC2301
from machine import Pin, I2C, SPI, ADC, UART, Timer
from microdot import Microdot, Response
from web_routes import setup_routes
from api_routes import setup_api_routes

# Start UART during boot process.
# Default settings:
# baudrate 9600, 8 bits, no parity, 1 stop bit
uart0 = UART(0)
uart0.init(tx=16, rx=17)
os.dupterm(uart0)

# Define PSU latch early to use in on-boot checks.
psu_set = Pin(14, Pin.OUT)
psu_sense = Pin(15, Pin.IN)
psu_reset = Pin(13, Pin.OUT)
psu = helpers.SRLatch(psu_set, psu_reset, psu_sense, name="psu")

# Defining i2c bus early to check for MACROM.
i2c = I2C(0, scl=Pin(9), sda=Pin(8), freq=100000)
MACROM_PRESENT = 80 in i2c.scan()
if MACROM_PRESENT:
    print("[INIT] Found MACROM!")
    MACROM_MAC = helpers.read_eeprom_mac(i2c)
    MACROM_STR = ":".join("{:02X}".format(b) for b in MACROM_MAC)
    BOARD_REV = helpers.read_board_rev(i2c)
else:
    print("[INIT] No MACROM found, assuming Rev4.x board.")
    BOARD_REV = "Rev 4"

VERSION = "1.3.0-DEV"
DEFAULT_CONFIG = {
    "network": {
        "hostname": "openjbod",
        "method": "dhcp",
        "ip": "",
        "subnet_mask": "",
        "gateway": "",
        "dns": "",
    },
    "power": {
        "on_boot_delay": 0,
        "follow_usb": False,
        "follow_usb_delay": 0,
        "ignore_power_switch": False,
        "on_power_restore": "hardware_control",
    },
    "monitoring": {
        "use_ds18x20": True,
        "use_ext_probe": False,
        "use_ext_fan_ctrl": False,
        "ignore_fan_fail": False,
    },
    "web": {
        "users": {
            "1": {
                "username": "admin",
                "password": "c37a6c962da994da14d7494769ff5d53aac6eaf0",
            },  # admin/openjbod
            "2": {"username": "", "password": ""},
            "3": {"username": "", "password": ""},
            "4": {"username": "", "password": ""},
            "5": {"username": "", "password": ""},
        }
    },
    "fan_curve": {
        "1": {"temp": 10, "fan_p": 20},
        "2": {"temp": 20, "fan_p": 40},
        "3": {"temp": 30, "fan_p": 60},
        "4": {"temp": 40, "fan_p": 80},
        "5": {"temp": 50, "fan_p": 100},
    },
    "notes": "This field can be used to store free-form notes about the device, such as where it is located, or what it is connected to.",
}

try:
    os.stat(helpers.CONFIG_FILE)
    print("[INIT] Reading config from file.")
    CONFIG = helpers.read_config()
except OSError:
    print("[INIT] Config not found, writing and assuming defaults!")
    helpers.write_config(DEFAULT_CONFIG)
    CONFIG = helpers.read_config()


if CONFIG["power"].get("on_power_restore", "hardware_control") == "power_on":
    if not psu.state():
        time.sleep(CONFIG["power"]["on_boot_delay"])
        psu.on()
elif CONFIG["power"].get("on_power_restore", "hardware_control") == "power_off":
    psu.off()
elif CONFIG["power"].get("on_power_restore", "hardware_control") == "last_state":
    if psu.stored_state():
        time.sleep(CONFIG["power"]["on_boot_delay"])
        psu.on(store=False)
    else:
        psu.off(store=False)

# Remove generated template files as otherwise these will
# be rendered even if they are no longer accurate to the HTML
for i in os.ilistdir("templates"):
    (name, entry_type, inode, size) = i
    if "_html.py" in name:
        os.remove(f"templates/{name}")

# SSL has been removed.
# Removing deprecated option from config if present.
if CONFIG.get("web").get("use_tls") is not None:
    del CONFIG["web"]["use_tls"]
    helpers.write_config(CONFIG)

# Set up fan curve.
FAN_TEMPS = []
FAN_SPEEDS = []
for i in CONFIG["fan_curve"]:
    FAN_TEMPS.append(CONFIG["fan_curve"][i]["temp"])
    FAN_SPEEDS.append(CONFIG["fan_curve"][i]["fan_p"])
FAN_TEMPS.sort()
FAN_SPEEDS.sort()

usb_timer = Timer()


def usb_pin_check(pin):
    pin.irq(handler=None)
    print("Triggered usb_pin_check")
    if CONFIG["power"]["follow_usb_delay"]:
        usb_timer.init(
            mode=Timer.ONE_SHOT,
            period=CONFIG["power"]["follow_usb_delay"] * 1000,
            callback=lambda t: usb_pin_action(pin),
        )
    else:
        usb_pin_action(pin)


def usb_pin_action(pin):
    time.sleep(1)
    if pin.value():
        psu.on()
        print("Turning on")
    else:
        psu.off()
        print("Turning off")
    pin.irq(handler=usb_pin_check)


def fan_fail_handler(pin):
    # TODO: See https://github.com/OpenJBOD/software/issues/3
    FAN_FAILED = True


def power_btn_handler(pin):
    if psu.state():
        psu.off()
    else:
        psu.on()
    power_btn.irq(handler=power_debounce)


pwr_timer = Timer()


def power_debounce(pin):
    power_btn.irq(handler=None)
    pwr_timer.init(mode=Timer.ONE_SHOT, period=200, callback=power_btn_handler)


# Busses
spi = SPI(0, 2000000, mosi=Pin(3), miso=Pin(4), sck=Pin(2))
onew = Pin(18)  # On-board probe.
if CONFIG["monitoring"]["use_ext_probe"]:
    onew = Pin(11)  # External probe header.
# Individual pin functions
led = Pin(6, Pin.OUT)
fan_fail = Pin(10, Pin.IN, Pin.PULL_UP)
power_btn = Pin(12, Pin.IN, Pin.PULL_UP)
usb_sense = Pin(25, Pin.IN)
# Interrupts
power_btn.irq(trigger=Pin.IRQ_FALLING, handler=power_debounce)
fan_fail.irq(trigger=Pin.IRQ_FALLING, handler=fan_fail_handler)
if CONFIG["power"]["follow_usb"]:
    usb_sense.irq(trigger=Pin.IRQ_RISING, handler=usb_pin_check)
    usb_sense.irq(trigger=Pin.IRQ_FALLING, handler=usb_pin_check)

led.on()
emc2301 = EMC2301(i2c)
# This shouldn't need to be hardcoded.
# 3 is a good default for NF-F12 fans.
# See https://github.com/OpenJBOD/software/issues/4
emc2301.set_fan_edges(3)

ds_sensor = ds18x20.DS18X20(onewire.OneWire(onew))
ds_roms = ds_sensor.scan()
if len(ds_roms) == 0:
    print("[INIT] No ds18x20 device found, reverting to RP2040 measurements")
    CONFIG["monitoring"]["use_ds18x20"] = False
else:
    ds_rom = ds_roms[0]
    # Set temperature resolution to 9 bits.
    config = b"\x00\x00\x1f"
    ds_sensor.write_scratch(ds_rom, config)


def temp_monitor():
    if not CONFIG["monitoring"]["use_ext_fan_ctrl"]:
        if CONFIG["monitoring"]["use_ds18x20"]:
            temp = helpers.get_ds18x20_temp(ds_sensor, ds_rom)
        else:
            temp = helpers.get_rp2040_temp()
        fan_p = int(helpers.linear_interpolation(FAN_TEMPS, FAN_SPEEDS, temp))
        duty_cycle = helpers.percent_to_duty(fan_p)
        emc2301.set_pwm_duty_cycle(duty_cycle)


temp_monitor_timer = Timer()
temp_monitor_timer.init(
    mode=Timer.PERIODIC, period=500, callback=lambda t: temp_monitor()
)


def w5500_init(spi):
    nic = network.WIZNET5K(spi, Pin(5), Pin(0))  # Bus, CSn, RSTn
    # Setting the hostname currently does nothing.
    # See https://github.com/OpenJBOD/software/issues/2
    network.hostname(CONFIG["network"]["hostname"])
    nic.active(True)
    if MACROM_PRESENT:
        print(f"[INIT] Using MAC from EEPROM: {MACROM_STR}")
        nic.config(mac=bytes(MACROM_MAC))
    if CONFIG["network"]["method"] == "static":
        ip_addr = CONFIG["network"]["ip"]
        subnet_mask = CONFIG["network"]["subnet_mask"]
        gateway = CONFIG["network"]["gateway"]
        dns = CONFIG["network"]["dns"]
        nic.ifconfig((ip_addr, subnet_mask, gateway, dns))
    while not nic.isconnected():
        time.sleep(1)
        print("[INIT] Not connected to NIC, waiting for IP...")
        led.toggle()
    led.on()
    return nic.ifconfig()


ifconfig = w5500_init(spi)
if MACROM_PRESENT:
    MAC_ADDR = MACROM_STR
else:
    MAC_ADDR = helpers.get_mac_address(spi, Pin(5))
print(ifconfig)


def webserver():
    app = Microdot()

    setup_routes(
        app,
        CONFIG,
        psu,
        emc2301,
        ds_sensor,
        ds_rom,
        FAN_TEMPS,
        FAN_SPEEDS,
        VERSION,
        MAC_ADDR,
        BOARD_REV,
        ifconfig,
    )
    setup_api_routes(
        app,
        CONFIG,
        psu,
        emc2301,
        ds_sensor,
        ds_rom,
        FAN_TEMPS,
        FAN_SPEEDS,
        VERSION,
        MAC_ADDR,
        BOARD_REV,
        ifconfig,
    )

    Response.default_content_type = "text/html"
    app.run(port=80, debug=True)


try:
    webserver()
except KeyboardInterrupt:
    temp_monitor_timer.deinit()
