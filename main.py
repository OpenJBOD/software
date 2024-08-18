from machine import Pin, I2C, SPI, ADC
from time import sleep
from emc2301.emc2301 import EMC2301
import helpers
import onewire, ds18x20
import network
import time
import os
import _thread
from microdot import Microdot, Response, send_file, redirect
from microdot.utemplate import Template
from microdot.session import Session, with_session
import sys

DEBUG = True
DEFAULT_CONFIG = {
  'network': {
    'hostname': "openjbod",
    'method': "dhcp",
    'ip': None,
    'subnet_mask': None,
    'gateway': None,
    'dns': None
  },
  'power': {
    'on_boot': False,
    'on_boot_delay': 0,
    'follow_usb': False,
    'follow_usb_delay': 0,
    'ignore_power_switch': False
  },
  'monitoring': {
    'use_ds18x20': False,
  },
  'fan_curve': {
    '1': {'temp': 16, 'fan_p': 20},
    '2': {'temp': 25, 'fan_p': 40},
    '3': {'temp': 35, 'fan_p': 60},
    '4': {'temp': 45, 'fan_p': 80},
    '5': {'temp': 60, 'fan_p': 100}
  },
  'notes': 'This field can be used to store free-form notes about the device, such as where it is located, or what it is connected.'
}

try:
  os.stat(helpers.CONFIG_FILE)
  print("[INIT] Reading config from file.")
  CONFIG = helpers.read_config()
except OSError:
  print("[INIT] Config not found, writing and assuming defaults!")
  helpers.write_config(DEFAULT_CONFIG)
  CONFIG = helpers.read_config()

def fan_fail_handler(pin):
  # TODO: See https://github.com/OpenJBOD/rp2040/issues/3
  print("FAN FAILED!")

def power_btn_handler(pin):
  #REWRITE FOR REV4
  if psu_set.value():
    psu_set.off()
  else:
    psu_set.on()

# CHECK THESE FOR REV4
# Busses
i2c = I2C(1, scl=Pin(19), sda=Pin(18), freq=100000)
spi = SPI(0, 2000000, mosi=Pin(3), miso=Pin(4), sck=Pin(2))
onew = Pin(27)
# Individual pin functions
#led = Pin(6, Pin.OUT)
led = Pin(11, Pin.OUT)
#fan_fail = Pin(13, Pin.IN, Pin.PULL_UP)
power_btn = Pin(28, Pin.IN, Pin.PULL_UP)
#psu_reset = Pin(13)
psu_set = Pin(29, Pin.OUT)
#psu_sense = Pin(15, Pin.IN)
#usb_sense = Pin(25, Pin.IN)
# Interrupts
power_btn.irq(trigger=Pin.IRQ_FALLING,handler=power_btn_handler)
#fan_fail.irq(trigger=Pin.IRQ_FALLING,handler=fan_fail_handler)

led.on()
emc2301 = EMC2301(i2c)
# This shouldn't need to be hardcoded.
# See https://github.com/OpenJBOD/rp2040/issues/4
emc2301.set_fan_edges(3)

if CONFIG['monitoring']['use_ds18x20']:
  ds_sensor = ds18x20.DS18X20(onewire.OneWire(onew))
  ds_roms = ds_sensor.scan()
  if len(ds_roms) == 0:
    print("[INIT] No ds18x20 device found, reverting to RP2040 measurements")
    CONFIG['monitoring']['use_ds18x20'] = False
  else:
    ds_rom = ds_roms[0]

def w5500_init(spi):
  nic = network.WIZNET5K(spi, Pin(5), Pin(0))
  # Setting the hostname currently does nothing.
  # See https://github.com/OpenJBOD/rp2040/issues/2
  network.hostname(CONFIG['network']['hostname'])
  nic.active(True)
  if CONFIG['network']['method'] == "static":
    ip_addr = CONFIG['network']['ip']
    subnet_mask = CONFIG['network']['subnet_mask']
    gateway = CONFIG['network']['gateway']
    dns = CONFIG['network']['dns']
    nic.ifconfig((ip_addr, subnet_mask, gateway, dns))
  while not nic.isconnected():
    sleep(1)
    print("[INIT]: Not connected to NIC, waiting...")
  return nic.ifconfig()

# Get mac before init'ing w5500 so we don't mess with it.
mac_addr = helpers.get_mac_address(spi, Pin(5))
ifconfig = w5500_init(spi)

def temp_monitor():
  while True:
    # Currently broken, unsure why.
    # Needs debugging in the main/core0 thread.
    if CONFIG['monitoring']['use_ds18x20']:
      temp = helpers.get_ds18x20_temp(ds_sensor, ds_rom)
    else:
      temp = helpers.get_rp2040_temp()
    fan_p = helpers.check_temp(temp, CONFIG['fan_curve'])
    duty_cycle = helpers.percent_to_duty(fan_p)
    emc2301.set_pwm_duty_cycle(duty_cycle)
    time.sleep(60)

def webserver():
  app = Microdot()
  Response.default_content_type = 'text/html'

  # Utility
  @app.route('/static/<path:path>')
  def static(request, path):
    if '..' in path:
      return 'Not found', 404
    return send_file('gzstatic/' + path, compressed=True, file_extension='.gz')

  @app.route('/power_toggle')
  async def power_toggle(req):
    psu_set.toggle()
    return redirect('/')

  @app.route('/reset_config')
  async def reset_config(req):
    helpers.write_config(DEFAULT_CONFIG)
    helpers.reset_rp2040()

  @app.route('/note', methods=['POST'])
  async def update_note(req):
    CONFIG['notes'] = req.form['notes']
    helpers.write_config(CONFIG)
    return redirect('/')

  # Pages
  @app.route('/settings', methods=['GET', 'POST'])
  async def settings_page(req):
    if req.method == 'POST':
      print(req.form)
      # TODO: Validation logic
      # https://github.com/OpenJBOD/rp2040/issues/5
      CONFIG['network']['hostname'] = req.form['hostname']
      CONFIG['network']['method'] = req.form['ip_method']
      CONFIG['network']['ip'] = req.form['ip_address']
      CONFIG['network']['subnet_mask'] = req.form['subnet_mask']
      CONFIG['network']['gateway'] = req.form['gateway_ip']
      CONFIG['network']['dns'] = req.form['dns_ip']
      if req.form.get('on_boot'):
        CONFIG['power']['on_boot'] = True
      else:
        CONFIG['power']['on_boot'] = False
      CONFIG['power']['on_boot_delay'] = int(req.form['on_boot_delay'])
      if req.form.get('follow_usb'):
        CONFIG['power']['follow_usb'] = True
      else:
        CONFIG['power']['follow_usb'] = False
      CONFIG['power']['follow_usb_delay'] = int(req.form['follow_usb_delay'])
      if req.form.get('ignore_power_switch'):
        CONFIG['power']['ignore_power_switch'] = True
      else:
        CONFIG['power']['ignore_power_switch'] = False
      if req.form.get('use_ds18x20'):
        CONFIG['monitoring']['use_ds18x20'] = True
      else:
        CONFIG['monitoring']['use_ds18x20'] = False
      CONFIG['fan_curve']['1']['temp'] = int(req.form['curve_1_c'])
      CONFIG['fan_curve']['1']['fan_p'] = int(req.form['curve_1_p'])
      CONFIG['fan_curve']['2']['temp'] = int(req.form['curve_2_c'])
      CONFIG['fan_curve']['2']['fan_p'] = int(req.form['curve_2_p'])
      CONFIG['fan_curve']['3']['temp'] = int(req.form['curve_3_c'])
      CONFIG['fan_curve']['3']['fan_p'] = int(req.form['curve_3_p'])
      CONFIG['fan_curve']['4']['temp'] = int(req.form['curve_4_c'])
      CONFIG['fan_curve']['4']['fan_p'] = int(req.form['curve_4_p'])
      CONFIG['fan_curve']['5']['temp'] = int(req.form['curve_5_c'])
      CONFIG['fan_curve']['5']['fan_p'] = int(req.form['curve_5_p'])
      CONFIG['notes'] = req.form['notes']
      helpers.write_config(CONFIG)
      redirect('/')
      helpers.reset_rp2040()
    return Template('settings.html').render(config=CONFIG)

  @app.route('/')
  @app.route('/index')
  async def index(req):
    response = {}
    response['config'] = CONFIG
    response['atx_state'] = psu_set.value()
    response['serial'] = helpers.get_id()
    response['fan_rpm'] = emc2301.get_fan_speed(edges=3, poles=1)
    response['net_info'] = helpers.get_network_info(ifconfig)
    response['mac_addr'] = mac_addr
    response['duty_cycle'] = helpers.duty_to_percent(emc2301.get_pwm_duty_cycle())
    if CONFIG['monitoring']['use_ds18x20']:
      response['temp'] = helpers.get_ds18x20_temp(ds_sensor, ds_rom)
    else:
      response['temp'] = helpers.get_rp2040_temp()
    return Template('index.html').render(resp=response)
  
  @app.route('/about')
  async def about(req):
    return send_file('gzstatic/about.html', compressed=True, file_extension='.gz')
  
  # TODO: SSL/TLS support
  # https://github.com/OpenJBOD/rp2040/issues/1
  app.run(port=80)

fan = _thread.start_new_thread(temp_monitor, ())
webserver()
