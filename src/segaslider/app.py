#!/usr/bin/env python3

from kivy import require as kvrequire
from kivy.config import Config
kvrequire('2.0.0')

# Forward all log entries from logging to kivy logger.
import logging
from kivy.logger import Logger
logging.Logger.manager.root = Logger

import os
import weakref
import math
import asyncio

# Usual kivy stuff
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.effectwidget import EffectWidget, HorizontalBlurEffect
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock
import kivy.properties as kvprops
import kivy.resources as kvres
import kivy.metrics as kvmetrics

from . import protocol

class LEDWidget(Widget):
    led_index = kvprops.NumericProperty(0)  # @UndefinedVariable
    led_value = kvprops.ListProperty([0, 0, 0])  # @UndefinedVariable
    top_slider_object = kvprops.ObjectProperty(None)  # @UndefinedVariable

class ElectrodeWidget(Widget):
    electrode_index = kvprops.NumericProperty(0)  # @UndefinedVariable
    value = kvprops.NumericProperty(0)  # @UndefinedVariable
    #led_value = kvprops.ListProperty([0, 0, 0])  # @UndefinedVariable
    overlay_alpha = kvprops.NumericProperty(0.0)  # @UndefinedVariable
    top_slider_object = kvprops.ObjectProperty(None)  # @UndefinedVariable

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

    def _collide_with_overlap(self, x, y):
        if self.top_slider_object is not None and isinstance(self.top_slider_object, SliderWidgetLayout):
            x_overlap = kvmetrics.mm(self.top_slider_object.x_overlap_mm)
            y_overlap = kvmetrics.mm(self.top_slider_object.y_overlap_mm)
            x1, x2 = self.x - x_overlap, self.right + x_overlap
            y1, y2 = self.y - y_overlap, self.top + y_overlap
            return x1 <= x <= x2 and y1 <= y <= y2 and self.parent.collide_point(x, y)
        else:
            Logger.warning('Using electrode widget outside slider widget')
            return super().collide_point(x, y)

    def collide_point(self, x, y):
        return self._collide_with_overlap(x, y)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            # Use 0xfe to avoid extra overhead
            self.value = 0xfe
        super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.value = 0x0
        super().on_touch_up(touch)

    def on_touch_move(self, touch):
        was_us = touch.grab_current is self
        is_us = self.collide_point(*touch.pos)
        if was_us and not is_us:
            touch.ungrab(self)
            self.value = 0x0
        elif not was_us and is_us:
            touch.grab(self)
            self.value = 0xfe
        super().on_touch_move(touch)

class SliderWidgetLayout(FloatLayout):
    electrodes = kvprops.NumericProperty(32)  # @UndefinedVariable
    leds = kvprops.NumericProperty(32)  # @UndefinedVariable
    slider_layout = kvprops.OptionProperty('diva', options=['diva', 'chu'])  # @UndefinedVariable
    x_overlap_mm = kvprops.NumericProperty(0.0)  # @UndefinedVariable
    y_overlap_mm = kvprops.NumericProperty(0.0)  # @UndefinedVariable
    diffuser_width = kvprops.NumericProperty(16.0)  # @UndefinedVariable

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orientation = 'horizontal'
        self._update_electrodes()

    def _update_electrodes(self):
        self.clear_widgets()

        # Create LED layout
        led_layer = BoxLayout(orientation='horizontal', size=self.size, pos=self.pos)
        # Create diffuser on top of LED layout
        led_diffuser = EffectWidget()
        led_diffuser.effects = []
        if self.diffuser_width >= 0:
            led_diffuser.effects.append(HorizontalBlurEffect(size=self.diffuser_width))
        led_diffuser.add_widget(led_layer)
        self.add_widget(led_diffuser)

        # Fix ids reference since kivy doesn't have built-in mechanics to do it
        self.ids['led_diffuser'] = weakref.proxy(led_diffuser)
        led_diffuser.ids['leds'] = weakref.proxy(led_layer)

        if self.slider_layout == 'diva':
            self.electrodes = 32
            self.leds = 32
            electrode_layer = BoxLayout(orientation='horizontal', size=self.size, pos=self.pos)
            for i in range(self.electrodes):
                electrode_layer.add_widget(ElectrodeWidget(electrode_index=i, top_slider_object=self))
            for i in range(self.leds):
                led_layer.add_widget(LEDWidget(led_index=i, top_slider_object=self))
            self.add_widget(electrode_layer)
            self.ids['electrodes'] = weakref.proxy(electrode_layer)
        elif self.slider_layout == 'chu':
            self.electrodes = 32
            self.leds = 31
            electrode_layer = GridLayout(rows=2)
            for i in range(self.electrodes):
                # Calculate the actual ID according to widget insertion sequence
                r = i // 16
                c = 15 - (i % 16)
                electrode_index = c * 2 + r
                electrode_layer.add_widget(ElectrodeWidget(electrode_index=electrode_index, top_slider_object=self))
            for i in range(self.leds):
                if i % 2 == 1:
                    # Partition
                    led_layer.add_widget(LEDWidget(led_index=self.leds-1-i, width=3, size_hint=(None, 1.0), top_slider_object=self))
                else:
                    # Panel
                    led_layer.add_widget(LEDWidget(led_index=self.leds-1-i, top_slider_object=self))
            self.add_widget(electrode_layer)
            self.ids['electrodes'] = weakref.proxy(electrode_layer)

    def on_slider_layout(self, obj, value):
        self._update_electrodes()

    def on_diffuser_width(self, obj, value):
        self._update_electrodes()

    def on_touch_move(self, touch):
        if touch.pos == touch.ppos:
            return True
        else:
            super().on_touch_move(touch)

class SegaSliderApp(App):
    report_enabled = kvprops.BooleanProperty(False)  # @UndefinedVariable

    def build(self):
        # Register the app directory as a resource directory
        kvres.resource_add_path(self.directory)
        self._slider_transport = None
        self._slider_protocol = None
        self._fired = 0

    def build_config(self, config):
        super().build_config(config)
        config.setdefaults('segaslider', dict(
            port='serial:/dev/ttyUSB0',
            mode='diva',
            layout='auto',
            hwinfo='auto',
            diffuser='auto',
            x_overlap_mm=6.0,
            y_overlap_mm=6.0,
            gamma=0.5,
            diffuser_width=16.0,
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
            if key in ('x_overlap_mm', 'y_overlap_mm'):
                Logger.info('Overlap settings changed.')
                self.sync_electrode_overlap()
            if key in ('diffuser_width', 'diffuser'):
                Logger.info('Diffuser settings changed.')
                self.sync_diffuser_settings()

    async def _reset_protocol_handler_coro(self):
        default_mode = self.config.get('segaslider', 'mode')
        potential_override = self.config.get('segaslider', 'hwinfo')
        mode = default_mode if potential_override == 'auto' else potential_override
        try:
            self._slider_transport, self._slider_protocol = await protocol.create_connection(asyncio.get_running_loop(), self.config.get('segaslider', 'port'), mode)
        except Exception:
            Logger.exception('Failed to connect to port')
        else:
            self._slider_protocol.on('connection_lost', self._on_connection_lost)
            self._slider_protocol.on('led', self._on_led)
            self._slider_protocol.on('report_oneshot', self._send_input_report)
            self._slider_protocol.on('report_state_change', self._on_report_state_change)
            self._slider_protocol.on('reset', self._on_soft_reset)
            self._on_connection_made()
        
    def reset_protocol_handler(self):
        # Start the serial/frontend event handler
        if self.transport_available():
            self._slider_transport.close()
            self.report_enabled = False
        # okay nodejs code
        asyncio.create_task(self._reset_protocol_handler_coro())

    def transport_available(self):
        return self._slider_transport is not None and not self._slider_transport.is_closing()

    def update_slider_layout(self):
        slider_widget = self.root.ids['slider_root']
        default_mode = self.config.get('segaslider', 'mode')
        potential_override = self.config.get('segaslider', 'layout')
        mode = default_mode if potential_override == 'auto' else potential_override
        slider_widget.slider_layout = mode
        self.sync_electrode_overlap()
        self.sync_diffuser_settings()

    def sync_electrode_overlap(self):
        slider_widget = self.root.ids['slider_root']
        slider_widget.x_overlap_mm = self.config.getfloat('segaslider', 'x_overlap_mm')
        slider_widget.y_overlap_mm = self.config.getfloat('segaslider', 'y_overlap_mm')

    def sync_diffuser_settings(self):
        slider_widget = self.root.ids['slider_root']
        diffuser = self.config.get('segaslider', 'diffuser')
        if (diffuser == 'auto' and slider_widget.slider_layout == 'diva') or diffuser == 'force_on':
            slider_widget.diffuser_width = self.config.getfloat('segaslider', 'diffuser_width')
        else:
            slider_widget.diffuser_width = -1.0

    def _on_connection_lost(self, exc):
        serial_status = self.root.ids['top_hud_serial_status']
        serial_status.serial_connected = False
        self.report_enabled = False

    def _on_connection_made(self):
        serial_status = self.root.ids['top_hud_serial_status']
        serial_status.serial_connected = True

    def _on_soft_reset(self):
        self.report_enabled = False

    def _on_led(self, report):
        slider_widget = self.root.ids['slider_root']
        led_layer = slider_widget.ids['led_diffuser'].ids['leds']
        gamma = self.config.getfloat('segaslider', 'gamma')
        # Clamp the brightness factor to 1
        brightness_factor = min((report['brightness'] / 63), 1.0)
        for w in led_layer.children:
            if len(report['led_brg']) >= (w.led_index + 1) * 3:
                for index_rgb in range(3):
                    # rgb -> brg
                    # 0 -> 1, 1 -> 2, 2 -> 0
                    led_offset = w.led_index * 3
                    index_brg = (index_rgb + 1) % 3
                    w.led_value[index_rgb] = math.pow((report['led_brg'][led_offset + index_brg] / 255) * brightness_factor, gamma)

    def on_report_enabled(self, _inst, val):
        # Update report status indicator
        hud = self.root.ids['top_hud_report_status']
        hud.report_enabled = val

    def _on_report_state_change(self, enabled):
        # Callback on when report state changes
        self.report_enabled = enabled

    def _send_input_report(self):
        if self.transport_available():
            slider_widget = self.root.ids['slider_root']
            electrode_layer = slider_widget.ids['electrodes']
            if self.report_enabled:
                # populate the report
                report = bytearray(slider_widget.electrodes)
                for w in electrode_layer.children:
                    if isinstance(w, ElectrodeWidget) and len(report) >= w.electrode_index + 1:
                        report[w.electrode_index] = w.value
                self._slider_protocol.send_input_report(report)

    def on_tick(self, dt):
        self._fired += 1
        self._send_input_report()

    def print_fired(self, dt):
        Logger.debug('InputReport: %f ticks/second', self._fired/dt)
        self._fired = 0

    def on_start(self):
        self.reset_protocol_handler()
        self.update_slider_layout()
        # Changing FPS lock requires restart so no live update needed.
        maxfps = Config.getint('graphics', 'maxfps')
        Clock.schedule_interval(self.on_tick, 1/maxfps if maxfps > 0 else 0)
        Clock.schedule_interval(self.print_fired, 1)

    def on_stop(self):
        if self.transport_available():
            self._slider_transport.close()
        # TODO properly wait until close
        Logger.info('Will now exit')

if __name__ == '__main__':
    asyncio.run(SegaSliderApp().async_run('asyncio'))
