#!/usr/bin/env python3

import typing as T

import asyncio
import io
import serial_asyncio
import bluetooth
import queue
import enum
import logging
import struct
import urllib.parse
from collections import namedtuple

from .helper import e0d0
from .helper import checksum

SliderHardwareInfo = namedtuple('SliderHardwareInfo',
                                ('model', 'device_class', 'fw_type', 'unk_0xe', 'fw_ver', 'unk_0x10', 'unk_0x11',))
_hwinfo_packer = struct.Struct('<8sB5s4B')

HW_INFO = dict(
    diva=_hwinfo_packer.pack(*SliderHardwareInfo(
        model=b'15275   ',
        device_class=0xa0,
        fw_type=b'06687',
        unk_0xe=0xff,
        fw_ver=0x90,
        unk_0x10=0x00,
        unk_0x11=0x64
    )),
    chu=_hwinfo_packer.pack(*SliderHardwareInfo(
        model=b'15330   ',
        device_class=0xa0,
        fw_type=b'06712',
        unk_0xe=0xff,
        fw_ver=0x90,
        unk_0x10=0x00,
        unk_0x11=0x64
    )),
)


class SliderCommand(enum.IntEnum):
    input_report = 0x01
    led_report = 0x02
    enable_slider_report = 0x03
    disable_slider_report = 0x04
    unk_0x09 = 0x09
    unk_0x0a = 0x0a
    reset = 0x10
    exception = 0xee
    get_hw_info = 0xf0


class ExceptionCode1(enum.IntEnum):
    wrong_checksum = 0x1
    bus_error = 0x2
    internal_error = 0xed


class SliderDevice(asyncio.Protocol):
    def __init__(self, mode='diva'):
        self._transport = None
        self._logger = logging.getLogger('SliderDevice')
        self._mode = mode
        self.e0d0ctx = e0d0.E0D0Context(sync=0xff, esc=0xfd)
        self.cksumctx_rx = checksum.NegativeJVSChecksum(init=-0xff)
        self.cksumctx_tx = checksum.NegativeJVSChecksum(init=-0xff)
        self.ledqueue = queue.Queue(maxsize=4)
        self.inputqueue = queue.Queue(maxsize=4)
        self.partial_packets = io.BytesIO()
        self._callback = {}
        self._dispatch = {
            # input_report should be periodical input report only
            SliderCommand.input_report: self.handle_input_report_one_shot,
            SliderCommand.led_report: self.handle_led_report,
            SliderCommand.enable_slider_report: self.handle_enable_slider_report,
            SliderCommand.reset: self.handle_reset,
            SliderCommand.get_hw_info: self.handle_get_hw_info,
        }
        if self._mode == 'chu':
            self._dispatch.update({
                # TODO figure out what to return
                SliderCommand.disable_slider_report: self.handle_disable_slider_report,
            })
        elif self._mode == 'diva':
            self._dispatch.update({
                SliderCommand.unk_0x09: self.handle_empty_response,
                SliderCommand.unk_0x0a: self.handle_empty_response,
            })

    def on(self, event, cb):
        self._callback[event] = cb

    def _run_callback(self, event, *argc, **argv):
        if event in self._callback:
            return self._callback[event](*argc, **argv)

    def connection_made(self, transport):
        self._transport = transport
        self._run_callback('connection_made')

    def data_received(self, data):
        packets = self.e0d0ctx.decode(data)
        for p in packets:
            self._stitch_and_dispatch(p)

    def connection_lost(self, exc: T.Optional[Exception]):
        if exc is None:
            self._logger.info('Connection closed')
            # TODO notify app
        else:
            self._logger.exception('Unexpected connection lost', exc_info=exc)
            # TODO notify app
        self._run_callback('connection_lost', exc=exc)

    def handle_input_report_one_shot(self, cmd, args):
        self._logger.debug('one-shot input report request')
        self._run_callback('report_oneshot')

    def handle_led_report(self, cmd, args):
        self._logger.debug('new led report')
        # Copies the data to the queue
        report = dict(brightness=args[0], led_brg=bytes(args[1:]))
        self._run_callback('led', report=report)

    def handle_enable_slider_report(self, cmd, args):
        self._logger.info('Open sesame')
        self._run_callback('report_state_change', enabled=True)

    def handle_disable_slider_report(self, cmd, args):
        self._logger.info('Close sesame')
        self._run_callback('report_state_change', enabled=False)
        self.send_cmd(SliderCommand.disable_slider_report)

    def handle_reset(self, cmd, args):
        self._logger.info('Reset')
        self._run_callback('reset')
        self.send_cmd(cmd)

    def handle_empty_response(self, cmd, args):
        self.send_cmd(cmd)

    def handle_get_hw_info(self, cmd, args):
        self.send_cmd(cmd, HW_INFO[self._mode])

    def send_input_report(self, report):
        self.send_cmd(SliderCommand.input_report, report)

    def send_exception(self, code1):
        response = bytearray(2)
        response[0] = 0xff
        response[1] = code1
        self.send_cmd(SliderCommand.exception, bytes(response))

    def send_cmd(self, cmd, args=None):
        self.cksumctx_tx.reset()
        buf = io.BytesIO()
        cmd_byte = cmd.to_bytes(1, 'big')
        len_byte = len(args).to_bytes(1, 'big') if args is not None else b'\x00'
        buf.write(self.e0d0ctx.encode(cmd_byte))
        self.cksumctx_tx.update(cmd_byte)
        buf.write(self.e0d0ctx.encode(len_byte))
        self.cksumctx_tx.update(len_byte)
        if args != None:
            buf.write(self.e0d0ctx.encode(args))
            self.cksumctx_tx.update(args)
        buf.write(self.e0d0ctx.finalize(self.cksumctx_tx.getvalue().to_bytes(1, 'big')))
        self._logger.debug('Reply: %s', repr(buf.getvalue()))
        # TODO: possible error handling
        self._transport.write(buf.getbuffer())

    def _stitch_and_dispatch(self, packet):
        self.partial_packets.write(packet)
        self.cksumctx_rx.update(packet)

        # if there is not enough bytes, wait for more
        if self.partial_packets.tell() < 2:
            return

        # Index 0: cmd
        # Index 1: argc
        # Index 2-n: argv
        # Index n+1: checksum
        argc = self.partial_packets.getbuffer()[1]
        packet_len = argc + 3

        assert packet_len >= self.partial_packets.tell(), 'stitched packet is larger than expected'

        if packet_len == self.partial_packets.tell():
            stitched = self.partial_packets.getbuffer()
            assert packet_len == len(stitched)
            if self.cksumctx_rx.getvalue() != 0:
                # Warn, discard packet and return
                self._logger.error('bad checksum (expecting 0x%02x, got 0x%02x)', stitched[-1], (self.cksumctx_rx.getvalue() + stitched[-1]) & 0xff)
                self.send_exception(ExceptionCode1.wrong_checksum)
            else:
                # Proceed to dispatch
                cmd = stitched[0]
                args = stitched[2:-1]
                if cmd in self._dispatch:
                    self._logger.debug('cmd 0x%02x args %s', cmd, repr(bytes(args)))
                    self._dispatch[cmd](cmd, args)
                else:
                    self._logger.warning('Unknown cmd 0x%02x args %s', cmd, repr(bytes(args)))
            # manually free the memoryviews
            del args
            del stitched

            # cleanup
            self.partial_packets.close()
            del self.partial_packets
            self.partial_packets = io.BytesIO()
            self.cksumctx_rx.reset()


async def create_rfcomm_connection(loop: asyncio.BaseEventLoop, protocol_factory: asyncio.Protocol, bdaddr: str, channel: int) -> T.Tuple[asyncio.Transport, asyncio.Protocol]:
    sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    sock.connect((bdaddr, channel))
    return await loop.create_connection(protocol_factory, sock=sock)


async def create_connection(loop: asyncio.BaseEventLoop, uri: str, mode: T.Optional[str]='diva') -> T.Tuple[asyncio.Transport, SliderDevice]:
    parsed_uri = urllib.parse.urlparse(uri)
    # tcp://127.0.0.1:12345 or tcp://[::1]:12345
    if parsed_uri.scheme == 'tcp':
        return await loop.create_connection(lambda: SliderDevice(mode), parsed_uri.hostname, parsed_uri.port or 12345)
    # serial:COM0 or serial:///dev/ttyUSB0 or serial:/dev/ttyUSB0
    elif parsed_uri.scheme == 'serial':
        return await serial_asyncio.create_serial_connection(loop, lambda: SliderDevice(mode), parsed_uri.path, baudrate=115200)
    # rfcomm://[11:22:33:44:55:66]:0
    elif parsed_uri.scheme == 'rfcomm':
        return await create_rfcomm_connection(loop, lambda: SliderDevice(mode), parsed_uri.hostname, parsed_uri.port or 0)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(create_connection(loop, 'tcp://127.0.0.1'))
    loop.run_forever()
    loop.close()
