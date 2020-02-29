# SegaSlider

Crappy SEGA slider emulator.

## Installation

### Prerequisite

- Tested on Windows and Linux
- Python 3.7+
- (Windows only) [MSVC Toolchain](https://visualstudio.microsoft.com/downloads/)
- (Linux only) See [Here](https://kivy.org/doc/stable/installation/installation-devel.html#linux)

### Windows

1. Set the environment variables as per the [Kivy installation guide](https://kivy.org/doc/stable/installation/installation-windows.html#use-development-kivy)

On cmd or bash, follow the step 4. On PowerShell, do

```powershell
$Env:USE_SDL2=1
$Env:USE_GSTREAMER=1
```

2. Install everything listed in `requirements*.txt` in the following order:

```powershell
pip install -r requirements.pass1.txt
pip install -r requirements.pass2.windows.txt
pip install -r requirements.txt
```

### Linux

1. Install everything listed in `requirements*.txt` in the following order:

```sh
pip install -r requirements.pass1.txt
pip install -r requirements.txt
```

## Usage

Run `python src/start.py`

### Connect with the game

SegaSlider emulates the slider on the protocol level. Therefore a serial port (either physical or virtual depending on your use case) must be used in order to talk to the host. The host in this case can be a game or a upstream hardware that uses the device running SegaSlider as a SEGA slider.

The `Port name` option in the settings menu specifies which port to use in order to establish a connection with the host.

### Slider modes

Currently 2 modes are supported.

- diva: emulates the slider in Project DIVA Future Tone (837-15275)
- chu: emulates the slider in Chunithm (837-15330)

It is possible to override the layout and/or the reported model number in settings regardless of the modes selected but DO NOT use them unless you really know what you are doing.

### Transport backends

Currently SegaSlider supports 3 transport backends: TCP connection, serial (COM) and Bluetooth RFCOMM.

#### TCP

URI format: `tcp://<hostname>:<port>`

The hostname can either be an IPv4/IPv6 address or a domain name.

#### Serial

URI format: `serial:COMx` (on Windows) or `serial:///dev/tty<S|USB|ACM>x` or `serial:/dev/tty<S|USB|ACM>x` (on Linux)

The serial port will be configured as 115200 8n1 whenever possible.

#### Bluetooth RFCOMM

URI format: `rfcomm://<bdaddr>:<channel>`

The BDADDR is in the format of `00-11-22-33-44-55` and the channel number is the PSM channel number.

#### Bluetooth RFCOMM (SDP)

URI format: `rfcomm://<bdaddr>/sdp?name=[name]&uuid=[uuid]`

The BDADDR format is the same as Bluetooth RFCOMM URI. The two optional query parameters, `name` and `uuid`, are used to select the desired service announced via SDP, by service name and UUID respectively. The first serial port class service that matches the specified criteria will be used by the program.
