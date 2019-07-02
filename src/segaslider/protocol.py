#!/usr/bin/env python3

import io
import serial
import queue
import enum
import logging
import threading

from .helper import e0d0
from .helper import checksum

# Hardcoding this for now
HW_INFO = b'15275   \xa006687\xff\x90\x00d'

class SliderCommand(enum.IntEnum):
    input_report = 0x01
    led_report = 0x02
    enable_slider_report = 0x03
    unk_0x04 = 0x04
    unk_0x09 = 0x09
    unk_0x0a = 0x0a
    ping = 0x10
    exception = 0xee
    get_hw_info = 0xf0

class SliderDevice(object):
    def __init__(self, port):
        self._logger = logging.getLogger('SliderDevice')
        self.ser = serial.Serial(port, 115200)
        self.ser.timeout = 0.1
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
            SliderCommand.unk_0x09: self.handle_empty_response,
            SliderCommand.unk_0x0a: self.handle_empty_response,
            SliderCommand.ping: self.handle_empty_response,
            SliderCommand.get_hw_info: self.handle_get_hw_info,
        }

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
        self.send_cmd(cmd, args)

    def handle_empty_response(self, cmd, args):
        if cmd == SliderCommand.ping:
            self._logger.info('Pong!')
        self.send_cmd(cmd)

    def handle_get_hw_info(self, cmd, args):
        self.send_cmd(cmd, HW_INFO)

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
            self.ser.write(buf.getbuffer())

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
                self.send_input_report(report_body)
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
