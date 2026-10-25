################################################################################
# PocketDebugKit - CH32H417 firmware standalone Makefile
# Clone the repo, then build with the WCH RISC-V toolchain (riscv-wch-elf-gcc):
#
#   make            # build UART firmware (default)
#   make SQUARE=1   # build the fixed 1 kHz square-wave firmware
#   make clean
#
# The toolchain ships with MounRiver Studio (RISC-V Embedded GCC12).
# Override the prefix if needed:   make CROSS=riscv-none-elf-
################################################################################

CROSS  ?= riscv-wch-elf-
CC      = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
SIZE    = $(CROSS)size

BUILD   = build

# ---- Architecture / CPU flags (match the MRS generated project) ----
ARCH = -march=rv32imac_zba_zbb_zbc_zbs_xw -mabi=ilp32 -msmall-data-limit=8 -msave-restore

CFLAGS = $(ARCH) -fmax-errors=20 -Os -fmessage-length=0 -fsigned-char \
         -ffunction-sections -fdata-sections -fno-common \
         -Wunused -Wuninitialized -g -DCore_V3F -std=gnu99 \
         -I Common -I User -I Core -I Debug -I Peripheral/inc

# ---- Sources ----
C_SRCS  = $(wildcard Common/*.c User/*.c Core/*.c Debug/*.c Peripheral/src/*.c)
ASM_SRCS = Startup/startup_ch32h417_v3f.S

# Build the square-wave firmware by swapping in the alternative hardware.c
ifeq ($(SQUARE),1)
CFLAGS += -D SQUARE_BUILD
C_SRCS := $(filter-out Common/hardware.c,$(C_SRCS))
C_SRCS += alternative_square_hardware.c
endif

OBJS = $(patsubst %.c,$(BUILD)/%.o,$(C_SRCS)) \
       $(patsubst %.S,$(BUILD)/%.o,$(ASM_SRCS))

LDSCRIPT = Ld/V3F/Link_v3f.ld
LDFLAGS  = $(ARCH) -T $(LDSCRIPT) -nostartfiles -Xlinker --gc-sections \
           -Wl,-Map=$(BUILD)/firmware.map --specs=nano.specs --specs=nosys.specs

TARGET = $(BUILD)/PocketDebugKit

all: $(TARGET).hex $(TARGET).bin
	$(SIZE) --format=berkeley $(TARGET).elf

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -MMD -MP -c -o $@ $<

$(BUILD)/%.o: %.S
	@mkdir -p $(dir $@)
	$(CC) $(ARCH) -x assembler-with-cpp -g -DCore_V3F -c -o $@ $<

$(TARGET).elf: $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS) -lm

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -rf $(BUILD)

-include $(OBJS:.o=.d)
.PHONY: all clean
