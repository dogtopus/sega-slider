# SegaSlider

Crappy SEGA slider emulator.

(This is of course not affiliated with or endorsed by SEGA.)

## Installation

### Prerequisite

- Tested on Windows and Linux
- Python 3.9
- (Windows only) [MSVC Toolchain](https://visualstudio.microsoft.com/downloads/)
  - MinGW could also work. Refer to [setup guide](https://wiki.python.org/moin/WindowsCompilers#GCC_-_MinGW_.28x86.29) for details.
- (Linux only) System toolchain

### Pipenv

```
pipenv install
```

### requirements.txt

```
pip install -r requirements.txt
```

## Usage

Run `python src/start.py` (or `pipenv run start` if using Pipenv)

### Connect with the game

SegaSlider emulates the slider on the protocol level. Therefore a serial port (either physical or virtual depending on your use case) must be used in order to talk to the host. The host in this case can be a game or a upstream hardware that uses the device running SegaSlider as a slider controller.

The `Port name` option in the settings menu specifies which port to use in order to establish a connection with the host.

### Slider modes

Currently 2 modes are supported.

- diva: emulates the slider controller in Project DIVA Future Tone (837-15275)
- chu: emulates the slider controller in Chunithm (837-15330)

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

Alternatively, the BDADDR can be specified as an [RFC7668 IPv6 link-local address](https://tools.ietf.org/html/rfc7668#section-3.2.2) in the form of `[fe80::0011:22ff:fe33:4455]`.

#### Bluetooth RFCOMM (SDP)

URI format: `rfcomm://<bdaddr>/sdp?name=[name]&uuid=[uuid]`

The BDADDR format is the same as Bluetooth RFCOMM URI. The two optional query parameters, `name` and `uuid`, are used to select the desired service announced via SDP, by service name and UUID respectively. The first serial port class service that matches the specified criteria will be used by the program.

For example, to connect to a [Windows incoming COM port](https://www.verizon.com/support/knowledge-base-20605/) named COM11, use `rfcomm://<bdaddr>/sdp?name=COM11`. Note that games may not accept Bluetooth serial port as-is due to short timeout intervals, so you may need to combine hub4com and com0com to keep the serial port alive for accepting connections from Bluetooth devices.
