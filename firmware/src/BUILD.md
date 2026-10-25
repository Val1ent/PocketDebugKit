# Firmware Build Guide

This directory contains the complete, self-contained firmware source for the
CH32H417 Pocket Digital Debug Kit. You can rebuild **exactly** the prebuilt
firmware files in `firmware/` from these sources.

## Directory layout

| Path | Contents |
|---|---|
| `Common/` | Application code: sampling + signal generator (`hardware.c`), USB CDC device, descriptors, soft-UART |
| `User/` | `main.c`, interrupt handlers, chip config, system clock |
| `Core/` | RISC-V QingKe core support |
| `Debug/` | Low-level debug / UART printf support |
| `Peripheral/` | WCH standard peripheral library (`inc/` headers + `src/` drivers) |
| `Startup/` | Startup assembly (`startup_ch32h417_v3f.S`) |
| `Ld/V3F/Link_v3f.ld` | Linker script for the QingKe V3F core |
| `Makefile` | Standalone command-line build (no IDE required) |
| `alternative_square_hardware.c` | Square-wave version of `hardware.c` (used automatically by `make SQUARE=1`) |

## Toolchain

The firmware targets the **QingKe V3F** RISC-V core (RV32 with the WCH XW
extension). Use the toolchain that ships with MounRiver Studio:

- **MounRiver Studio 2** (includes RISC-V Embedded GCC 12, `riscv-wch-elf-gcc`)
- The `bin` folder of the toolchain must be on your `PATH` (it contains
  `riscv-wch-elf-gcc`, `riscv-wch-elf-objcopy`, ...)

## Build from the command line

```bash
cd firmware/src

make            # build the UART firmware   -> build/PocketDebugKit.hex/.bin
make SQUARE=1   # build the 1 kHz square-wave firmware
make clean      # remove the build/ output folder
```

`make` produces `build/PocketDebugKit.hex` and `build/PocketDebugKit.bin`.
These are byte-for-byte the same build configuration as the prebuilt files
`../UART_10kHz.hex/.bin` and `../Square_1kHz.hex/.bin`.

If your toolchain uses a different prefix, override it:

```bash
make CROSS=riscv-none-elf-
```

## Build with MounRiver Studio (GUI)

1. Open MounRiver Studio, create a workspace.
2. **File > Open Projects from File System** and import this `src` folder as a
   project (the `.cproject`/`.project` files from the original WCH example are
   not required for the command-line build; for the GUI, create a new
   CH32H417 project and add the `Common/`, `User/`, `Core/`, `Debug/`,
   `Peripheral/`, `Startup/` folders and the `Ld/V3F/Link_v3f.ld` linker
   script).
3. Select the V3F target and click **Build**.

## Flashing

Use the WCH-Link debugger with OpenOCD (also bundled with MounRiver Studio):

```bash
openocd -f wch-riscv.cfg \
  -c "program build/PocketDebugKit.hex verify reset exit"
```

`Verified OK` in the output means flashing succeeded. You can also flash the
`.hex` directly from the MounRiver Studio download tool.

## Key firmware parameters

- 8 capture channels: **PD0–PD7**, sample rate **10 kHz**
- USB 2.0 Full-Speed **CDC**, endpoint 3 bulk upload, endpoint 2 command channel
- Sampling runs in the TIM2 interrupt into a ring buffer, so USB stalls never
  drop samples
- Soft-UART test signal: message `"Hello CH32!"`, 1000 baud, 8N1, LSB first
- Square-wave test signal: 1 kHz, 50% duty on PA15
