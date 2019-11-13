# SegaSlider

Crappy SEGA slider emulator.

## Usage

1. Install dependencies listed in `requirements.txt` (`requirements.windows.txt` if on Windows)
2. Run `python src/start.py`

### Connect with the game

SegaSlider emulates the slider on the protocol level. Therefore a serial port (either physical or virtual depending on your use case) must be used in order to talk to the host. The host in this case can be a game or a upstream hardware that uses the device running SegaSlider as a SEGA slider.

The `Port name` option in the settings menu specifies which port to use in order to establish a connection with the host.

### Slider modes

Currently 2 modes are supported.

- diva: emulates the slider in Project DIVA Future Tone (837-15275)
- chu: emulates the slider in Chunithm (837-15330)

It is possible to override the layout and/or the reported model number in settings regardless of the modes selected but DO NOT use them unless you really know what you are doing.
