"""
OpenJBOD Helper Functions
"""
import json
import machine
import time
import binascii
from hashlib import sha1

CONFIG_FILE = "config.json"

class SRLatch:
  def __init__(self, set_pin: machine.Pin, reset_pin: machine.Pin, 
               sense_pin: machine.Pin):
    if (not isinstance(set_pin, machine.Pin) or 
        not isinstance(reset_pin, machine.Pin) or 
        not isinstance(sense_pin, machine.Pin)):
        raise TypeError("All arguments must be machine.Pin instances.")
    
    self.set_pin = set_pin
    self.reset_pin = reset_pin
    self.sense_pin = sense_pin

  def on(self):
    self.reset_pin.off()
    self.set_pin.on()
    time.sleep_ms(250)
    self.set_pin.off()
    
  def off(self):
    self.set_pin.off()
    self.reset_pin.on()
    time.sleep_ms(250)
    self.reset_pin.off()
    
  def state(self):
    if self.sense_pin.value():
      return True
    else:
      return False

def create_hash(password):
  return binascii.hexlify(sha1(password).digest()).decode("utf-8")

def get_id():
  # Uses the flash attached to the RP2040 to derive a unique board ID.
  return binascii.hexlify(machine.unique_id()).decode('utf-8').upper()

def spi_write_read(spi, cs, addr, length=1):
  # Simple SPI function for reading arbitrary bytes.
  addr_high = (addr >> 8) & 0xFF
  addr_low = addr & 0xFF
  control_byte = 0x00
  
  cmd = bytearray([addr_high, addr_low, control_byte])
  
  cs.off()
  spi.write(cmd)
  data = spi.read(length)
  cs.on()
  
  return data

def get_mac_address(spi, cs):
  # Get W5500 MAC address.
  mac = spi_write_read(spi, cs, 0x0009, 6)
    
  mac_str = ':'.join('{:02X}'.format(b) for b in mac)
    
  return mac_str

def reset_rp2040():
  # Note, this is a hard reset. For soft resets, use sys.exit()
  machine.reset()

def get_rp2040_temp():
  conversion_factor = 3.3/(65535)
  reading = machine.ADC(4).read_u16() * conversion_factor

  temp = 27 - (reading - 0.706)/0.001721
  return temp

def get_ds18x20_temp(ds_sensor, rom):
  ds_sensor.convert_temp()
  time.sleep_ms(250)
  
  return ds_sensor.read_temp(rom)

def check_temp(temp, fan_curve):
  fan_speed = list(fan_curve.values())[0]['fan_p']
  for step in fan_curve.values():
    if temp >= step['temp']:
      fan_speed = step['fan_p']
    else:
      break
  return fan_speed

def get_network_info(ifconfig):
  # Store the W5500 ifconfig tuple in a more readable format.
  network_info = {}
  (ip_addr, subnet_mask, gateway_ip, dns_ip) = ifconfig
  network_info['ip_addr'] = ip_addr
  network_info['subnet_mask'] = subnet_mask
  network_info['gateway_ip'] = gateway_ip
  network_info['dns_ip'] = dns_ip
 
  return network_info

def duty_to_percent(duty):
  return round((duty * 100 + 128) / 256)

def percent_to_duty(percent):
  return round(((percent * 256) - 128) / 100)

def read_config():
  with open(CONFIG_FILE, 'r') as f:
    return json.load(f)
  
def write_config(config):
  with open(CONFIG_FILE, 'w') as f:
    json.dump(config, f)
  
  return "Config written!"
