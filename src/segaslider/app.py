#!/usr/bin/env python3

# Forward all log entries from logging to kivy logger.
import logging
from kivy.logger import Logger
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
logging.Logger.manager.root = Logger

import os
import weakref

# Usual kivy stuff
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors.button import ButtonBehavior
from kivy.clock import Clock
import kivy.properties as kvprops
import kivy.resources as kvres

# For exception handling
import queue
import serial

from . import protocol

class LEDWidget(Widget):
    led_index = kvprops.NumericProperty(0)  # @UndefinedVariable
    led_value = kvprops.ListProperty([0, 0, 0])  # @UndefinedVariable

class ElectrodeWidget(ButtonBehavior, Widget):
    electrode_index = kvprops.NumericProperty(0)  # @UndefinedVariable
    value = kvprops.NumericProperty(0)  # @UndefinedVariable
    #led_value = kvprops.ListProperty([0, 0, 0])  # @UndefinedVariable
    overlay_alpha = kvprops.NumericProperty(0.0)  # @UndefinedVariable

#     def _collide_plus(self, touch):
#         tx, ty = touch.pos
#         
#         if isinstance(touch.shape, kvinputshape.ShapeRect):
#             deltax = touch.shape.width / 2
#             deltay = touch.shape.height / 2
#             tx1, tx2, ty1, ty2 = tx - deltax, tx + deltax, ty - deltay, ty + deltay
#             wx1, wy1, wx2, wy2 = self.x, self.y, self.x + self.width, self.y + self.height
#             if tx1 < wx2 and wx1 < tx2 and ty1 < wy2 and wy1 < ty2:
#                 return True
#             else:
#                 return False
#         else:
#             if self.collide_point(tx, ty):
#                 return True
#             else:
#                 return False

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            # Use 0xfe to avoid extra overhead
            self.value = 0xfe

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.value = 0x0

    def on_touch_move(self, touch):
        was_us = touch.grab_current is self
        is_us = self.collide_point(*touch.pos)
        if was_us and not is_us:
            touch.ungrab(self)
            self.value = 0x0
        elif not was_us and is_us:
            touch.grab(self)
            self.value = 0xfe

class SliderWidgetLayout(FloatLayout):
    electrodes = kvprops.NumericProperty(32)  # @UndefinedVariable
    leds = kvprops.NumericProperty(32)  # @UndefinedVariable
    slider_layout = kvprops.OptionProperty('diva', options=['diva', 'chu'])  # @UndefinedVariable

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orientation = 'horizontal'
        self._update_electrodes()

    def _update_electrodes(self):
        self.clear_widgets()

        led_layer = BoxLayout(id='leds', orientation='horizontal', size=self.size, pos=self.pos)
        self.add_widget(led_layer)
        # Fix ids reference since kivy doesn't have built-in mechanics to do it
        self.ids['leds'] = weakref.proxy(led_layer)

        if self.slider_layout == 'diva':
            self.electrodes = 32
            self.leds = 32
            electrode_layer = BoxLayout(id='electrodes', orientation='horizontal', size=self.size, pos=self.pos)
            for i in range(self.electrodes):
                electrode_layer.add_widget(ElectrodeWidget(electrode_index=i))
            for i in range(self.leds):
                led_layer.add_widget(LEDWidget(led_index=i))
            self.add_widget(electrode_layer)
            self.ids['electrodes'] = weakref.proxy(electrode_layer)
        elif self.slider_layout == 'chu':
            self.electrodes = 32
            self.leds = 31
            electrode_layer = GridLayout(id='electrodes', rows=2)
            for i in range(self.electrodes):
                # Calculate the actual ID according to widget insertion sequence
                r = i // 16
                c = 15 - (i % 16)
                electrode_index = c * 2 + r
                electrode_layer.add_widget(ElectrodeWidget(electrode_index=electrode_index))
            for i in range(self.leds):
                if i % 2 == 1:
                    # Partition
                    led_layer.add_widget(LEDWidget(led_index=i, width=3, size_hint=(None, 1.0)))
                else:
                    # Panel
                    led_layer.add_widget(LEDWidget(led_index=i))
            self.add_widget(electrode_layer)
            self.ids['electrodes'] = weakref.proxy(electrode_layer)

    def on_slider_layout(self, obj, value):
        self._update_electrodes()

class SegaSliderApp(App):
    def build(self):
        # Register the app directory as a resource directory
        kvres.resource_add_path(self.directory)
        self._slider_protocol = None

    def build_config(self, config):
        super().build_config(config)
        config.setdefaults('segaslider', dict(
            port='/dev/ttyUSB0',
            mode='diva',
            layout='auto',
            hwinfo='auto',
        ))

    def build_settings(self, settings):
        super().build_settings(settings)
        settings.add_json_panel('segaslider', self.config, kvres.resource_find('segaslider.settings.json'))

    def get_application_config(self):
        return os.path.join(self.user_data_dir, '{}.ini'.format(self.name))

    def on_config_change(self, config, section, key, value):
        super().on_config_change(config, section, key, value)
        if section == 'segaslider':
            if key in ('port', 'mode', 'hwinfo',):
                Logger.info('Serial port settings changed, restarting handler.')
                self.reset_protocol_handler()
            if key in ('mode', 'layout',):
                Logger.info('Layout settings changed.')
                self.update_slider_layout()

    def reset_protocol_handler(self):
        # Start the serial/frontend event handler
        if self._slider_protocol is not None:
            self._slider_protocol.halt()
            self._slider_protocol = None
            report_status = self.root.ids['top_hud_report_status']
            report_status.report_enabled = False
        try:
            default_mode = self.config.get('segaslider', 'mode')
            potential_override = self.config.get('segaslider', 'hwinfo')
            mode = default_mode if potential_override == 'auto' else potential_override
            self._slider_protocol = protocol.SliderDevice(self.config.get('segaslider', 'port'), mode=mode)
            self._slider_protocol.start()
        except serial.serialutil.SerialException:
            Logger.exception('Failed to connect to serial port')

    def update_slider_layout(self):
        slider_widget = self.root.ids['slider_root']
        default_mode = self.config.get('segaslider', 'mode')
        potential_override = self.config.get('segaslider', 'layout')
        mode = default_mode if potential_override == 'auto' else potential_override
        slider_widget.slider_layout = mode

    def on_tick(self, dt):
        serial_status = self.root.ids['top_hud_serial_status']
        if self._slider_protocol is not None:
            if not serial_status.serial_connected:
                serial_status.serial_connected = True
            slider_widget = self.root.ids['slider_root']
            led_layer = slider_widget.ids['leds']
            electrode_layer = slider_widget.ids['electrodes']
            hud = self.root.ids['top_hud_report_status']
            # populating the report
            report = bytearray(slider_widget.electrodes)

            try:
                led_report = self._slider_protocol.ledqueue.get_nowait()
            except queue.Empty:
                Logger.debug('LED report queue underrun')
                led_report = None

            for w in electrode_layer.children:
                if isinstance(w, ElectrodeWidget) and len(report) >= w.electrode_index + 1:
                    report[w.electrode_index] = w.value
            for w in led_layer.children:
                if led_report is not None and len(led_report['led_brg']) >= (w.led_index + 1) * 3:
                    w.led_value[0] = led_report['led_brg'][(w.led_index * 3) + 1]
                    w.led_value[1] = led_report['led_brg'][(w.led_index * 3) + 2]
                    w.led_value[2] = led_report['led_brg'][(w.led_index * 3) + 0]
            try:
                if self._slider_protocol.input_report_enable.is_set():
                    self._slider_protocol.inputqueue.put_nowait(report)
                    if not hud.report_enabled:
                        hud.report_enabled = True
            except queue.Full:
                Logger.warning('Input report queue overrun')
        else:
            if serial_status.serial_connected:
                serial_status.serial_connected = False

    def on_start(self):
        self.reset_protocol_handler()
        self.update_slider_layout()
        try:
            # Put other initialization code here
            Clock.schedule_interval(self.on_tick, 12/1000)
        except:
            # Halt the thread in case something happens
            Logger.exception('Exception occurred during startup. Notifying the protocol handler to quit.')
            self.on_stop()
            raise

    def on_stop(self):
        if self._slider_protocol is not None:
            self._slider_protocol.halt()
        Logger.info('Will now exit')

if __name__ == '__main__':
    SegaSliderApp().run()
