from micropython import const

MFG_ID = const(0x5D)
PART_ID_EMC2301 = const(0x37)
I2C_ADDR = const(0x2F)

CONFIG = const(0x20)  # 6-1
FAN_STATUS = const(0x24)  # 6-2
FAN_STALL_STATUS = const(0x25)  # 6-3
FAN_SPIN_STATUS = const(0x26)  # 6-4
DRIVE_FAIL_STATUS = const(0x27)  # 6-5
FAN_INT_EN = const(0x29)  # 6-6
PWM_POLARITY = const(0x2A)  # 6-7
PWM_OUT_CONFIG = const(0x2B)  # 6-8
PWM_BASEF45 = const(0x2C)  # 6-9 Check if implemented on EMC2301
PWM_BASEF123 = const(0x2D)  # 6-10
FAN_DRIVE = const(0x30)  # 6-11
PWM_DIVIDE = const(0x31)  # 6-12
FAN_CONFIG1 = const(0x32)  # 6-13
FAN_CONFIG2 = const(0x33)  # 6-14
PID_GAIN = const(0x35)  # 6-15
FAN_SPIN_UP = const(0x36)  # 6-16
MAX_STEP = const(0x37)  # 6-17
MIN_DRIVE = const(0x38)  # 6-18
VALID_TACH_COUNT = const(0x39)  # 6-19
DRIVE_FAIL_MSB = const(0x3B)  # 6-20
DRIVE_FAIL_LSB = const(0x3A)  # 6-21
TACH_TARGET_MSB = const(0x3D)  # 6-22
TACH_TARGET_LSB = const(0x3C)  # 6-22
TACH_READING_MSB = const(0x3E)  # 6-23
TACH_READING_LSB = const(0x3F)  # 6-24
SOFTWARE_LOCK = const(0xEF)  # 6-25

# Register 6-26 not implemented in 2301
REG_PID = const(0xFD)  # 6-27
REG_MFR = const(0xFE)  # 6-28
REG_REV = const(0xFF)  # 6-29

# Bits in config register 6-1.
CONFIG_MASK = const(0x80)
CONFIG_DIST_TO = const(0x40)
CONFIG_WD_EN = const(0x20)
# The bits in 0x10, 0x08, 0x04 are not implemented in the EMC230x.
CONFIG_DRECK = const(0x02)
CONFIG_USECK = const(0x01)

FAN_STATUS_WATCH = const(0x80)
# Bits 6-3 are unimplemented.
FAN_STATUS_DVFAIL = const(0x04)
FAN_STATUS_FNSPIN = const(0x02)
FAN_STATUS_FNSTL = const(0x01)
