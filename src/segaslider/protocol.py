#!/usr/bin/env python3

import io
import serial
import queue
import enum
import logging
import threading
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
    ping = 0x10
    exception = 0xee
    get_hw_info = 0xf0

class SliderDevice(object):
    def __init__(self, port, mode='diva'):
        self._logger = logging.getLogger('SliderDevice')
        self._mode = mode
        self.ser = serial.Serial(port, 115200)
        self.ser.timeout = 0.1
        self.ser.write_timeout = 0.1
        self.ser_lock = threading.Lock()
        self.serial_event_thread = threading.Thread(target=self.run_serial_event_handler)
        self.frontend_event_thread = threading.Thread(target=self.run_frontend_event_handler)
        self.e0d0ctx = e0d0.E0D0Context(sync=0xff, esc=0xfd)
        self.cksumctx_rx = checksum.NegativeJVSChecksum(init=-0xff)
        self.cksumctx_tx = checksum.NegativeJVSChecksum(init=-0xff)
        self.input_report_enable = threading.Event()
        self.ledqueue = queue.Queue(maxsize=4)
        self.inputqueue = queue.Queue(maxsize=4)
        self.partial_packets = io.BytesIO()
        self.rx_len_hint = 1
        self._halt = threading.Event()
        self._dispatch = {
            # input_report should be periodical input report only
            SliderCommand.led_report: self.handle_led_report,
            SliderCommand.enable_slider_report: self.handle_enable_slider_report,
            SliderCommand.ping: self.handle_empty_response,
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
        if cmd == SliderCommand.ping:
            self._logger.info('Pong!')
        self.send_cmd(cmd)

    def handle_get_hw_info(self, cmd, args):
        self.send_cmd(cmd, HW_INFO[self._mode])

    def send_input_report(self, report):
        self.send_cmd(SliderCommand.input_report, report)
        self.ser.flush()

    def send_exception(self, body):
        self.send_cmd(SliderCommand.exception, body)

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
        with self.ser_lock:
            try:
                self.ser.write(buf.getbuffer())
            except serial.SerialTimeoutException:
                # OS serial buffer overrun, usually not a good sign (except if using a null modem driver and the other side disconnects)
                self._logger.error('OS serial TX buffer overrun')
                # Report to upper level as well
                raise

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
            self.rx_len_hint = 1
            if self.cksumctx_rx.getvalue() != 0:
                # Warn, discard packet and return
                self._logger.warning('bad checksum (expecting 0x%02x, got 0x%02x)', stitched[-1], (self.cksumctx_rx.getvalue() + stitched[-1]) & 0xff)
            else:
                # Proceed to dispatch
                cmd = stitched[0]
                args = stitched[2:-1]
                if cmd in self._dispatch:
                    self._logger.debug('cmd 0x%02x args %s', cmd, repr(bytes(args)))
                    try:
                        self._dispatch[cmd](cmd, args)
                    except serial.SerialTimeoutException:
                        # Top-level timeout exception handler (ignore)
                        pass
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
        else:
            # We have at least (total length - buffered length) bytes to read (because e0d0)
            new_hint = packet_len - self.partial_packets.tell()
            assert new_hint >= 1
            self.rx_len_hint = new_hint

    def run_serial_event_handler(self):
        self._logger.info('Starting serial event handler')
        while not self._halt.wait(0):
            packets = self.e0d0ctx.decode(self.ser.read(self.rx_len_hint))
            for p in packets:
                self._stitch_and_dispatch(p)
        self._logger.info('Serial event handler stopped')

    def run_frontend_event_handler(self):
        self._logger.info('Starting frontend event handler')
        while not self._halt.wait(0):
            if self.input_report_enable.wait(timeout=0.1):
                self._logger.debug('Waiting for input report')
                try:
                    report_body = self.inputqueue.get(timeout=0.1)
                except queue.Empty:
                    self._logger.warning('Input report queue underrun')
                    continue
                self._logger.debug('Pushing input report')
                try:
                    self.send_input_report(report_body)
                except serial.SerialTimeoutException:
                    pass

        self._logger.info('Frontend event handler stopped')

    def start(self):
        self.serial_event_thread.start()
        self.frontend_event_thread.start()

    def halt(self):
        self._halt.set()
        self._logger.info('Waiting for threads to terminate')
        self.serial_event_thread.join()
        self.frontend_event_thread.join()
        self._logger.info('Closing serial port')
        self.ser.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    proto = SliderDevice('/dev/ttyUSB0')
    proto.run_serial_event_handler()
