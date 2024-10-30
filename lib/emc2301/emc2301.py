"""
Basic EMC2301 Driver
Written for OpenJBOD by TheGuyDanish

Currently only implements a few necessary features.
"""

from machine import I2C
from emc2301 import emc2301_regs


def duty_to_percent(duty):
    return round((duty * 100 + 128) / 256)


def percent_to_duty(percent):
    return round(((percent * 256) - 128) / 100)


class EMC2301:
    def __init__(self, i2c: I2C):
        self.i2c = i2c
        self.addr = emc2301_regs.I2C_ADDR

    def get_mfg(self):
        return self.i2c.readfrom_mem(self.addr, emc2301_regs.REG_MFR, 1)

    def set_pwm_duty_cycle(self, duty_cycle):
        duty_cycle = max(0, min(255, duty_cycle))

        self.i2c.writeto_mem(self.addr, emc2301_regs.FAN_DRIVE, bytes([duty_cycle]))

    def get_pwm_duty_cycle(self):
        duty_cycle = self.i2c.readfrom_mem(self.addr, emc2301_regs.FAN_DRIVE, 1)

        return int(duty_cycle[0])

    def get_tach_bytes(self):
        msb = self.i2c.readfrom_mem(self.addr, emc2301_regs.TACH_READING_MSB, 1)
        lsb = self.i2c.readfrom_mem(self.addr, emc2301_regs.TACH_READING_LSB, 1)

        result = {}
        result["msb"] = msb
        result["lsb"] = lsb

        return result

    def get_fan_speed(self, poles=2, edges=5, f_tach=32768, m=1):
        msb = self.i2c.readfrom_mem(self.addr, emc2301_regs.TACH_READING_MSB, 1)
        lsb = self.i2c.readfrom_mem(self.addr, emc2301_regs.TACH_READING_LSB, 1)
        msb = int.from_bytes(msb, "big")
        lsb = int.from_bytes(lsb, "big")
        if msb == 255:
            return 0
        msb_bin = bin(msb)[2:]
        lsb_bin = bin(lsb)[2:]
        pad_msb_bin = "0" * (8 - len(msb_bin)) + msb_bin
        pad_lsb_bin = "0" * (8 - len(lsb_bin)) + lsb_bin
        msb_result = 0
        lsb_result = 0
        msb_values = [4096, 2048, 1024, 512, 256, 128, 64, 32]
        lsb_values = [16, 8, 4, 2, 1, 0, 0, 0]

        for bit, value in zip(pad_msb_bin, msb_values):
            if bit == "1":
                msb_result += value
        for bit, value in zip(pad_lsb_bin, lsb_values):
            if bit == "1":
                lsb_result += value

        tach_count = msb_result + lsb_result

        rpm = 1 / poles * ((edges - 1) / tach_count * (1 / m)) * f_tach * 60

        return rpm

    def get_fan_edges(self):
        edges_map = {
            0b00: 3,  # 3 edges sampled (1 poles) - Tach multiplier is 0.5
            0b01: 5,  # 5 edges sampled (2 poles) - Tach multiplier is 1
            0b10: 7,  # 7 edges sampled (3 poles) - Tach multiplier is 1.5
            0b11: 9,  # 9 edges sampled (4 poles) - Tach multiplier is 2
        }

        edges_register = self.i2c.readfrom_mem(self.addr, emc2301_regs.FAN_CONFIG1, 1)

        edge_bits = (edges_register[0] >> 5) & 0b11
        edges = edges_map.get(edge_bits, None)

        if edges is None:
            raise ValueError("Invalid edge bits value.")

        return edges

    def set_fan_edges(self, edges):
        edges_map = {
            3: 0b00,  # 3 edges sampled (1 poles) - Tach multiplier is 0.5
            5: 0b01,  # 5 edges sampled (2 poles) - Tach multiplier is 1
            7: 0b10,  # 7 edges sampled (3 poles) - Tach multiplier is 1.5
            9: 0b11,  # 9 edges sampled (4 poles) - Tach multiplier is 2
        }

        if edges not in edges_map:
            raise ValueError("Invalid number of edges. Choose from 3, 5, 7, or 9.")

        current_value = self.i2c.readfrom_mem(self.addr, emc2301_regs.FAN_CONFIG1, 1)[0]
        current_value &= ~(0b11 << 5)
        new_value = current_value | (edges_map[edges] << 5)

        self.i2c.writeto_mem(self.addr, emc2301_regs.FAN_CONFIG1, bytes([new_value]))

    def get_fan_range(self):
        range_register = self.i2c.readfrom_mem(self.addr, emc2301_regs.FAN_CONFIG1, 1)

        range_bits = (range_register[0] >> 5) & 0b11

        return range_bits

    def set_fan_range(self, multiplier):
        multiplier_map = {
            1: 0b00,  # 500 RPM minimum
            2: 0b01,  # 1000 RPM minimum
            4: 0b10,  # 2000 RPM minimum
            8: 0b11,  # 4000 RPM minimum
        }

        range_bits = multiplier_map.get(multiplier)

        if range_bits is None:
            raise ValueError("Invalid multiplier, must be 1, 2, 4 or 8.")

        current_value = self.i2c.readfrom_mem(self.addr, emc2301_regs.FAN_CONFIG1, 1)[0]
        new_value = (current_value & 0b10011111) | (range_bits << 5)

        self.i2c.writeto_mem(self.addr, emc2301_regs.FAN_CONFIG1, bytes([new_value]))
