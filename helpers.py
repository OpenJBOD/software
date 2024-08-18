"""
OpenJBOD Helper Functions
"""
import json
import machine
import time
import binascii

CONFIG_FILE = "config.json"

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

def psu_on(lset, lreset):
  # Turn off the latch reset pin (it shouldn't be on anyway), then turn on the set pin briefly.
  lreset.off()
  lset.on()
  time.sleep(0.2)
  lset.off()

def psu_off(lset, lreset):
  # Opposite of psu_on()
  lset.off()
  lreset.on()
  time.sleep(0.2)
  lreset.off()

def reset_rp2040():
  # Note, this is a hard reset. For soft resets, use sys.exit()
  machine.reset()

def get_rp2040_temp():
  conversion_factor = 3.3/(65535)
  reading = machine.ADC(4).read_u16() * conversion_factor

  temp = round(27 - (reading - 0.706)/0.001721)
  return temp

def get_ds18x20_temp(ds_sensor, rom):
  ds_sensor.convert_temp()
  time.sleep_ms(250)
  
  return round(ds_sensor.read_temp(rom))

def check_temp(temp, fan_curve):
  for step in fan_curve.values():
    if temp >= step['temp']:
      fan_speed = step['fan_p']
    else:
      fan_speed = fan_curve['1']['fan_p']
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
