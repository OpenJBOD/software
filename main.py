import helpers
import network
import os
import onewire, ds18x20
import time
from emc2301.emc2301 import EMC2301
from machine import Pin, I2C, SPI, ADC, UART, Timer
from microdot import Microdot, Response, send_file, redirect
from microdot.utemplate import Template
from microdot.session import Session, with_session
from microdot.auth import BasicAuth

# Start UART during boot process.
# Default settings:
# baudrate 9600, 8 bits, no parity, 1 stop bit
uart0 = UART(0)
uart0.init(tx=16, rx=17)
os.dupterm(uart0)

VERSION = "1.1.0"
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
        "on_boot": False,
        "on_boot_delay": 0,
        "follow_usb": False,
        "follow_usb_delay": 0,
        "ignore_power_switch": False,
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

# SSL has been removed.
# Removing deprecated option from config if present.
if CONFIG.get("web").get("use_tls") is not None:
    del CONFIG["web"]["use_tls"]
    helpers.write_config(CONFIG)

# Set up fan curve.
FAN_TEMPS = []
FAN_SPEEDS = []
for i in CONFIG['fan_curve']:
    FAN_TEMPS.append(CONFIG['fan_curve'][i]['temp'])
    FAN_SPEEDS.append(CONFIG['fan_curve'][i]['fan_p'])
FAN_TEMPS.sort()
FAN_SPEEDS.sort()

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


# CHECK THESE FOR REV4
# Busses
i2c = I2C(0, scl=Pin(9), sda=Pin(8), freq=100000)
spi = SPI(0, 2000000, mosi=Pin(3), miso=Pin(4), sck=Pin(2))
onew = Pin(18)  # On-board probe.
if CONFIG["monitoring"]["use_ext_probe"]:
    onew = Pin(11)  # External probe header.
# Individual pin functions
led = Pin(6, Pin.OUT)
fan_fail = Pin(10, Pin.IN, Pin.PULL_UP)
power_btn = Pin(12, Pin.IN, Pin.PULL_UP)
psu_reset = Pin(13, Pin.OUT)
psu_set = Pin(14, Pin.OUT)
psu_sense = Pin(15, Pin.IN)
usb_sense = Pin(25, Pin.IN)
# Interrupts
power_btn.irq(trigger=Pin.IRQ_FALLING, handler=power_debounce)
fan_fail.irq(trigger=Pin.IRQ_FALLING, handler=fan_fail_handler)

psu = helpers.SRLatch(psu_set, psu_reset, psu_sense)

if CONFIG["power"]["on_boot"]:
    time.sleep(CONFIG["power"]["on_boot_delay"])
    if not psu.state():
        psu.on()

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
    config = b'\x00\x00\x1f'
    ds_sensor.write_scratch(ds_rom, config)


def temp_monitor():
    if psu_sense.value() and not CONFIG["monitoring"]["use_ext_fan_ctrl"]:
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
MAC_ADDR = helpers.get_mac_address(spi, Pin(5))
print(ifconfig)


def webserver():
    app = Microdot()
    auth = BasicAuth()
    Response.default_content_type = "text/html"

    # Utility
    @auth.authenticate
    async def check_credentials(request, username, password):
        for user in CONFIG["web"]["users"]:
            if username in CONFIG["web"]["users"][user]["username"]:
                if (
                    helpers.create_hash(password)
                    == CONFIG["web"]["users"][user]["password"]
                ):
                    return user

    @app.route("/static/<path:path>")
    @auth
    def static(request, path):
        if ".." in path:
            return "Not found", 404
        return send_file("gzstatic/" + path, compressed=True, file_extension=".gz")

    @app.route("/power_toggle")
    @auth
    async def power_toggle(req):
        if psu.state():
            psu.off()
        else:
            psu.on()
        return redirect("/")

    @app.route("/reset_rp2040")
    @auth
    async def reset_rp2040(req):
        helpers.reset_rp2040()
        return redirect("/")

    @app.route("/reset_config")
    @auth
    async def reset_config(req):
        helpers.write_config(DEFAULT_CONFIG)
        helpers.reset_rp2040()

    @app.route("/note", methods=["POST"])
    @auth
    async def update_note(req):
        CONFIG["notes"] = req.form["notes"]
        helpers.write_config(CONFIG)
        return redirect("/")

    # Pages
    @app.route("/settings/network", methods=["GET", "POST"])
    @auth
    async def settings_network(req):
        if req.method == "POST":
            CONFIG["network"]["hostname"] = req.form["hostname"]
            CONFIG["network"]["method"] = req.form["ip_method"]
            CONFIG["network"]["ip"] = req.form["ip_address"]
            CONFIG["network"]["subnet_mask"] = req.form["subnet_mask"]
            CONFIG["network"]["gateway"] = req.form["gateway_ip"]
            CONFIG["network"]["dns"] = req.form["dns_ip"]
            helpers.write_config(CONFIG)
            return redirect("/settings/network")
        return Template("settings_network.html").render(config=CONFIG)

    @app.route("/settings/power", methods=["GET", "POST"])
    @auth
    async def settings_power(req):
        if req.method == "POST":
            if req.form.get("on_boot"):
                CONFIG["power"]["on_boot"] = True
            else:
                CONFIG["power"]["on_boot"] = False
            CONFIG["power"]["on_boot_delay"] = int(req.form["on_boot_delay"])
            if req.form.get("follow_usb"):
                CONFIG["power"]["follow_usb"] = True
            else:
                CONFIG["power"]["follow_usb"] = False
            CONFIG["power"]["follow_usb_delay"] = int(req.form["follow_usb_delay"])
            if req.form.get("ignore_power_switch"):
                CONFIG["power"]["ignore_power_switch"] = True
            else:
                CONFIG["power"]["ignore_power_switch"] = False
            helpers.write_config(CONFIG)
            return redirect("/settings/power")
        return Template("settings_power.html").render(config=CONFIG)

    @app.route("/settings/environment", methods=["GET", "POST"])
    @auth
    async def settings_environ(req):
        if req.method == "POST":
            if req.form.get("use_ext_probe"):
                old_ds18x20 = CONFIG["monitoring"]["use_ext_probe"]
                CONFIG["monitoring"]["use_ext_probe"] = True
            else:
                old_ds18x20 = CONFIG["monitoring"]["use_ext_probe"]
                CONFIG["monitoring"]["use_ext_probe"] = False
            if req.form.get("use_ext_fan_ctrl"):
                CONFIG["monitoring"]["use_ext_fan_ctrl"] = True
            else:
                CONFIG["monitoring"]["use_ext_fan_ctrl"] = False
            if req.form.get("ignore_fan_fail"):
                CONFIG["monitoring"]["ignore_fan_fail"] = True
            else:
                CONFIG["monitoring"]["ignore_fan_fail"] = False
            CONFIG["fan_curve"]["1"]["temp"] = int(req.form["curve_1_c"])
            CONFIG["fan_curve"]["1"]["fan_p"] = int(req.form["curve_1_p"])
            CONFIG["fan_curve"]["2"]["temp"] = int(req.form["curve_2_c"])
            CONFIG["fan_curve"]["2"]["fan_p"] = int(req.form["curve_2_p"])
            CONFIG["fan_curve"]["3"]["temp"] = int(req.form["curve_3_c"])
            CONFIG["fan_curve"]["3"]["fan_p"] = int(req.form["curve_3_p"])
            CONFIG["fan_curve"]["4"]["temp"] = int(req.form["curve_4_c"])
            CONFIG["fan_curve"]["4"]["fan_p"] = int(req.form["curve_4_p"])
            CONFIG["fan_curve"]["5"]["temp"] = int(req.form["curve_5_c"])
            CONFIG["fan_curve"]["5"]["fan_p"] = int(req.form["curve_5_p"])
            helpers.write_config(CONFIG)
            # Revert to the previous setting after writing config.
            # This is to avoid having to re-do the sensor setup code.
            # Instead, the used probe will change on uC reset.
            if old_ds18x20 == False:
                CONFIG["monitoring"]["use_ext_probe"] = False
            return redirect("/settings/environment")
        return Template("settings_environment.html").render(config=CONFIG)

    @app.route("/settings/users", methods=["GET", "POST"])
    @auth
    async def settings_users(req):
        if req.method == "POST":
            if req.form.get("user_1_n") != CONFIG["web"]["users"]["1"]["username"]:
                CONFIG["web"]["users"]["1"]["username"] = req.form["user_1_n"]
            if req.form.get("user_1_cp"):
                CONFIG["web"]["users"]["1"]["password"] = helpers.create_hash(
                    req.form["user_1_p"]
                )
            if req.form.get("user_2_n") != CONFIG["web"]["users"]["2"]["username"]:
                CONFIG["web"]["users"]["2"]["username"] = req.form["user_2_n"]
            if req.form.get("user_2_cp"):
                CONFIG["web"]["users"]["2"]["password"] = helpers.create_hash(
                    req.form["user_2_p"]
                )
            if req.form.get("user_3_n") != CONFIG["web"]["users"]["3"]["username"]:
                CONFIG["web"]["users"]["3"]["username"] = req.form["user_3_n"]
            if req.form.get("user_3_cp"):
                CONFIG["web"]["users"]["3"]["password"] = helpers.create_hash(
                    req.form["user_3_p"]
                )
            if req.form.get("user_4_n") != CONFIG["web"]["users"]["4"]["username"]:
                CONFIG["web"]["users"]["4"]["username"] = req.form["user_4_n"]
            if req.form.get("user_4_cp"):
                CONFIG["web"]["users"]["4"]["password"] = helpers.create_hash(
                    req.form["user_4_p"]
                )
            if req.form.get("user_5_n") != CONFIG["web"]["users"]["5"]["username"]:
                CONFIG["web"]["users"]["5"]["username"] = req.form["user_5_n"]
            if req.form.get("user_5_cp"):
                CONFIG["web"]["users"]["5"]["password"] = helpers.create_hash(
                    req.form["user_5_p"]
                )

            helpers.write_config(CONFIG)
            return redirect("/settings/users")
        return Template("settings_users.html").render(config=CONFIG)

    @app.route("/settings/reset")
    @auth
    async def settings_reset(req):
        return Template("settings_reset.html").render()

    @app.route("/api/temperatures")
    @auth
    async def get_temperatures(req):
        temperatures = {}
        temperatures["rp2040"] = helpers.get_rp2040_temp()
        if CONFIG["monitoring"]["use_ds18x20"]:
            temperatures["chassis"] = helpers.get_ds18x20_temp(ds_sensor, ds_rom)
        return temperatures

    @app.route("/api/fanmode", methods=["POST"])
    @auth
    async def set_fan_ctrl(req):
        if "use_ext_fan_ctrl" in req.json and isinstance(
            req.json["use_ext_fan_ctrl"], (int, float)
        ):
            CONFIG["monitoring"]["use_ext_fan_ctrl"] = req.json["use_ext_fan_ctrl"]
        return {"status": "success"}

    @app.route("/api/fans", methods=["POST"])
    @auth
    async def set_fans(req):
        if "fan0" in req.json and isinstance(req.json["fan0"], (int, float)):
            CONFIG["monitoring"]["use_ext_fan_ctrl"] = True
            duty_cycle = helpers.percent_to_duty(req.json["fan0"])
            emc2301.set_pwm_duty_cycle(duty_cycle)
        return {"status": "success"}

    @app.route("/")
    @app.route("/index")
    @auth
    async def index(req):
        response = {}
        response["config"] = CONFIG
        response["atx_state"] = psu.state()
        response["serial"] = helpers.get_id()
        response["fan_rpm"] = emc2301.get_fan_speed(edges=3, poles=1)
        response["net_info"] = helpers.get_network_info(ifconfig)
        response["mac_addr"] = MAC_ADDR
        response["fan_speed_p"] = helpers.duty_to_percent(emc2301.get_pwm_duty_cycle())
        response["version"] = VERSION
        if CONFIG["monitoring"]["use_ds18x20"]:
            response["temp"] = round(helpers.get_ds18x20_temp(ds_sensor, ds_rom), 2)
        else:
            response["temp"] = round(helpers.get_rp2040_temp(), 2)
        return Template("index.html").render(resp=response)

    @app.route("/about")
    @auth
    async def about(req):
        return send_file("gzstatic/about.html", compressed=True, file_extension=".gz")

    app.run(port=80, debug=True)


try:
    webserver()
except KeyboardInterrupt:
    temp_monitor_timer.deinit()
