#!/usr/bin/env python3

import asyncio
import io
import serial
import queue
import enum
import logging
import struct
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
        self._dispatch = {
            # input_report should be periodical input report only
            SliderCommand.led_report: self.handle_led_report,
            SliderCommand.enable_slider_report: self.handle_enable_slider_report,
            SliderCommand.reset: self.handle_empty_response,
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

    def connection_made(self, transport):
        self._transport = transport

    def data_received(self, data):
        packets = self.e0d0ctx.decode(data)
        for p in packets:
            self._stitch_and_dispatch(p)

    def connection_lost(self, exc):
        # TODO
        pass

    def handle_led_report(self, cmd, args):
        self._logger.debug('new led report')
        # Copies the data to the queue
        report = dict(brightness=args[0], led_brg=bytes(args[1:]))
        try:
            self.ledqueue.put(report, timeout=0.1)
        except queue.Full:
            self._logger.warning('LED report queue overrun. Report dropped')

    def handle_enable_slider_report(self, cmd, args):
        self._logger.info('Open sesame')
        self.input_report_enable.set()

    def handle_disable_slider_report(self, cmd, args):
        self._logger.info('Close sesame')
        self.input_report_enable.clear()
        self.send_cmd(SliderCommand.disable_slider_report)

    def handle_empty_response(self, cmd, args):
        if cmd == SliderCommand.reset:
            self._logger.info('Reset')
        self.send_cmd(cmd)

    def handle_get_hw_info(self, cmd, args):
        self.send_cmd(cmd, HW_INFO[self._mode])

    def send_input_report(self, report):
        self.send_cmd(SliderCommand.input_report, report)
        #self.ser.flush()

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


async def test_tcp(host, port):
    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: SliderDevice('diva'), host, port)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(test_tcp('127.0.0.1', 12345))
