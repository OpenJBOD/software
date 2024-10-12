# OpenJBOD Software

The OpenJBOD Software is a Python-based software package for managing an OpenJBOD controller.

## Requirements

- An OpenJBOD RP2040 controller
- MicroPython v1.23.0 or newer
> [!TIP]
> You can download a combined firmware package with both MicroPython and the OpenJBOD software by going to this repository's [releases page](https://github.com/OpenJBOD/software/releases) and downloading the .uf2 file in the Assets section.

## How to deploy

Starting with version 1.1.0 of the OpenJBOD software. It is compiled into a firmware image that includes MicroPython and the OpenJBOD software. After copying the firmware image to your board, it will automatically extract the files required to run the board on boot.

Simply put your board into flashing mode by holding the BOOTSEL button, then dragging the .uf2 file found in the Releases on this repository onto your board. You can also load the .uf2 file using [picotool](https://github.com/raspberrypi/picotool).

The instructions below are for manual installation to the board with a separate MicroPython firmware:

All files and folders in this repo (except documentation) should be uploaded to the board after installing. Contents of the `gzstatic` folder should be gzipped before being copied to the board.

For CLI tools:
- Linux and macOS users can use [rshell](https://github.com/dhylands/rshell)
- Windows users can use [mpfshell](https://github.com/wendlers/mpfshell)

For GUI tools:
- [Thonny](https://thonny.org/) can show local and remote file systems by enabling it in View -> Files. Navigate to the directory on your computer with the files, right click each file and folder, and select "Upload to '/'".

After copying the files, you can unplug the board and plug it into an ATX power supply, after which it will start the boot process and pick up an IP.

> [!TIP]
> The default username and password for the board's web UI is `admin`:`openjbod`!

## How to develop

For current TODO items, see the `TODO` label in the Issues on this repository.

For development, it is suggested to use a dev environment like Thonny or VS Code with the MicroPico extension.

Important files are:
- `main.py` - Contains core logic for configuring, starting and the general operation of the board.
- `helpers.py` - Contains helper functions, so as to not clog up main.py with (unnecessary) ugly code or repeated functions.
- `emc2301/` - This directory contains the basic EMC2301 driver. This is the class we use to interface with the fan controller. `emc2301_regs.py` contains the register addresses of the EMC2301 for quick reference.

Webpage templates are stored in the `templates/` and `gzstatic/` directories, these are unique because:
- `gzstatic/` - Any request invoked to `/static/<path>` goes to the gzstatic directory. This is a good place to put gzipped static resources that will not change. Such as the about page, the CSS, images, etc. Please note that gzipped pages cannot be rendered as templates. **For the sake of ease of development, the files in gzstatic are NOT gzipped in this repo. Before pushing them to your board, ensure they are gzipped or they will fail to load!**
- `templates/` - These are the templates with variables. utemplate, the library used for templating, uses a very Jinja-like syntax. For exact examples, please see [miguelgrinberg's examples](https://github.com/miguelgrinberg/microdot/tree/main/examples/templates/utemplate).

## Shoutouts

This software uses a bunch of cool projects that are making this all possible, they include:

- [MicroPython](https://github.com/micropython/micropython)
- [Microdot](https://github.com/miguelgrinberg/microdot)
- [utemplate](https://github.com/pfalcon/utemplate)
- [Pure CSS](https://github.com/pure-css/pure/)
- [Pure CSS Layout Examples](https://purecss.io/layouts/)
