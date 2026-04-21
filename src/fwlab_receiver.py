#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: ALERT1v3
# Author: CD
# Copyright: BoM
# Description: Legacy ALERT
# GNU Radio version: 3.10.5.1

from packaging.version import Version as StrictVersion

if __name__ == '__main__':
    import ctypes
    import sys
    if sys.platform.startswith('linux'):
        try:
            x11 = ctypes.cdll.LoadLibrary('libX11.so')
            x11.XInitThreads()
        except:
            print("Warning: failed to XInitThreads()")

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio.filter import firdes
import sip
from gnuradio import analog
import math
from gnuradio import audio
from gnuradio import blocks
from gnuradio import digital
from gnuradio import filter
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio.qtgui import Range, RangeWidget
from PyQt5 import QtCore
import ALERT1v3_epy_block_0 as epy_block_0  # embedded python block
import ALERT1v3_epy_block_1 as epy_block_1  # embedded python block
import ALERT1v3_epy_block_2 as epy_block_2  # embedded python block
import osmosdr
import time
import json
import os



from gnuradio import qtgui

class ALERT1v3(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "ALERT1v3", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("ALERT1v3")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except:
            pass
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "ALERT1v3")

        try:
            if StrictVersion(Qt.qVersion()) < StrictVersion("5.0.0"):
                self.restoreGeometry(self.settings.value("geometry").toByteArray())
            else:
                self.restoreGeometry(self.settings.value("geometry"))
        except:
            pass

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 2.048e6
        self.fsk_deviation_hz = fsk_deviation_hz = 16e3
        self.decimation = decimation = 250
        self.transition_bw = transition_bw = fsk_deviation_hz/2
        self.samp_rate_audio = samp_rate_audio = 48000
        self.rf_squelch = rf_squelch = -33
        self.rfGain = rfGain = 40
        self.mqtt_username = mqtt_username = ''
        self.mqtt_topic_prefix = mqtt_topic_prefix = 'alert'
        self.mqtt_password = mqtt_password = ''
        self.mqtt_broker_port = mqtt_broker_port = 1883
        self.mqtt_broker_host = mqtt_broker_host = '127.0.0.1'
        self.log_base_path = log_base_path = '/home/cdomotor/rf_log'
        self.demod_rate = demod_rate = samp_rate/decimation
        self.center_freq = center_freq = 173.9e6
        self.demod_mode = demod_mode = 'legacy_fsk'
        self.afsk_mark_hz = afsk_mark_hz = 2100.0
        self.afsk_space_hz = afsk_space_hz = 1300.0

        # Optional runtime RF control override (saved by web admin)
        try:
            rf_cfg_path = '/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/config/rf_control.json'
            if os.path.exists(rf_cfg_path):
                with open(rf_cfg_path, 'r', encoding='utf-8') as f:
                    _rf = json.load(f)
                center_freq = float(_rf.get('center_freq_hz', center_freq))
                rfGain = float(_rf.get('rf_gain_db', rfGain))
                rf_squelch = float(_rf.get('rf_squelch_db', rf_squelch))
                self.center_freq = center_freq
                self.rfGain = rfGain
                self.rf_squelch = rf_squelch
        except Exception:
            pass

        # Optional runtime demod profile override (AFSK scaffolding)
        try:
            demod_cfg_path = '/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/config/demod_control.json'
            if os.path.exists(demod_cfg_path):
                with open(demod_cfg_path, 'r', encoding='utf-8') as f:
                    _dm = json.load(f)
                demod_mode = str(_dm.get('demod_mode', demod_mode))
                afsk_mark_hz = float(_dm.get('afsk_mark_hz', afsk_mark_hz))
                afsk_space_hz = float(_dm.get('afsk_space_hz', afsk_space_hz))
                self.demod_mode = demod_mode
                self.afsk_mark_hz = afsk_mark_hz
                self.afsk_space_hz = afsk_space_hz
        except Exception:
            pass

        ##################################################
        # Blocks
        ##################################################

        self.tabwid0 = Qt.QTabWidget()
        self.tabwid0_widget_0 = Qt.QWidget()
        self.tabwid0_layout_0 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabwid0_widget_0)
        self.tabwid0_grid_layout_0 = Qt.QGridLayout()
        self.tabwid0_layout_0.addLayout(self.tabwid0_grid_layout_0)
        self.tabwid0.addTab(self.tabwid0_widget_0, 'Operator')
        self.tabwid0_widget_1 = Qt.QWidget()
        self.tabwid0_layout_1 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabwid0_widget_1)
        self.tabwid0_grid_layout_1 = Qt.QGridLayout()
        self.tabwid0_layout_1.addLayout(self.tabwid0_grid_layout_1)
        self.tabwid0.addTab(self.tabwid0_widget_1, 'Signal')
        self.tabwid0_widget_2 = Qt.QWidget()
        self.tabwid0_layout_2 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabwid0_widget_2)
        self.tabwid0_grid_layout_2 = Qt.QGridLayout()
        self.tabwid0_layout_2.addLayout(self.tabwid0_grid_layout_2)
        self.tabwid0.addTab(self.tabwid0_widget_2, 'Diagnostics')
        self.top_layout.addWidget(self.tabwid0)
        self._rf_squelch_range = Range(-50, 0, 1, -33, 1)
        self._rf_squelch_win = RangeWidget(self._rf_squelch_range, self.set_rf_squelch, "'rf_squelch'", "counter_slider", float, QtCore.Qt.Horizontal)
        self.tabwid0_grid_layout_0.addWidget(self._rf_squelch_win, 1, 0, 1, 4)
        for r in range(1, 2):
            self.tabwid0_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 4):
            self.tabwid0_grid_layout_0.setColumnStretch(c, 1)
        self._rfGain_range = Range(-100, 100, 1, 40, 200)
        self._rfGain_win = RangeWidget(self._rfGain_range, self.set_rfGain, "'rfGain'", "counter_slider", float, QtCore.Qt.Horizontal)
        self.tabwid0_grid_layout_0.addWidget(self._rfGain_win, 0, 0, 1, 4)
        for r in range(0, 1):
            self.tabwid0_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 4):
            self.tabwid0_grid_layout_0.setColumnStretch(c, 1)
        self._center_freq_range = Range(100e6, 200e6, 25e3, 173.9e6, 200)
        self._center_freq_win = RangeWidget(self._center_freq_range, self.set_center_freq, "'center_freq'", "counter_slider", float, QtCore.Qt.Horizontal)
        self.tabwid0_grid_layout_0.addWidget(self._center_freq_win, 2, 0, 1, 4)
        for r in range(2, 3):
            self.tabwid0_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 4):
            self.tabwid0_grid_layout_0.setColumnStretch(c, 1)
        self.rtlsdr_source_0 = osmosdr.source(
            args="numchan=" + str(1) + " " + ''
        )
        self.rtlsdr_source_0.set_time_unknown_pps(osmosdr.time_spec_t())
        self.rtlsdr_source_0.set_sample_rate(samp_rate)
        self.rtlsdr_source_0.set_center_freq(center_freq, 0)
        self.rtlsdr_source_0.set_freq_corr(0, 0)
        self.rtlsdr_source_0.set_dc_offset_mode(0, 0)
        self.rtlsdr_source_0.set_iq_balance_mode(0, 0)
        self.rtlsdr_source_0.set_gain_mode(False, 0)
        self.rtlsdr_source_0.set_gain(rfGain, 0)
        self.rtlsdr_source_0.set_if_gain(0, 0)
        self.rtlsdr_source_0.set_bb_gain(0, 0)
        self.rtlsdr_source_0.set_antenna('', 0)
        self.rtlsdr_source_0.set_bandwidth(0, 0)
        self.rational_resampler_xxx_0 = filter.rational_resampler_ccc(
                interpolation=3,
                decimation=32,
                taps=[],
                fractional_bw=0)
        self.qtgui_waterfall_sink_x_1_1 = qtgui.waterfall_sink_f(
            256, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            100e3, #bw
            '', #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_1_1.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_1_1.enable_grid(True)
        self.qtgui_waterfall_sink_x_1_1.enable_axis_labels(False)

        self.qtgui_waterfall_sink_x_1_1.disable_legend()

        self.qtgui_waterfall_sink_x_1_1.set_plot_pos_half(not True)

        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_1_1.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_1_1.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_1_1.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_1_1.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_1_1.set_intensity_range(-140, 10)

        self._qtgui_waterfall_sink_x_1_1_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_1_1.qwidget(), Qt.QWidget)

        self.tabwid0_grid_layout_1.addWidget(self._qtgui_waterfall_sink_x_1_1_win, 1, 2, 2, 2)
        for r in range(1, 3):
            self.tabwid0_grid_layout_1.setRowStretch(r, 1)
        for c in range(2, 4):
            self.tabwid0_grid_layout_1.setColumnStretch(c, 1)
        self.qtgui_waterfall_sink_x_1 = qtgui.waterfall_sink_c(
            256, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            100e3, #bw
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_1.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_1.enable_grid(True)
        self.qtgui_waterfall_sink_x_1.enable_axis_labels(False)

        self.qtgui_waterfall_sink_x_1.disable_legend()


        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_1.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_1.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_1.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_1.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_1.set_intensity_range(-140, 10)

        self._qtgui_waterfall_sink_x_1_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_1.qwidget(), Qt.QWidget)

        self.tabwid0_grid_layout_1.addWidget(self._qtgui_waterfall_sink_x_1_win, 1, 0, 2, 2)
        for r in range(1, 3):
            self.tabwid0_grid_layout_1.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabwid0_grid_layout_1.setColumnStretch(c, 1)
        self.qtgui_time_sink_x_1 = qtgui.time_sink_f(
            1024, #size
            48000, #samp_rate
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_time_sink_x_1.set_update_time(0.10)
        self.qtgui_time_sink_x_1.set_y_axis(-1, 1)

        self.qtgui_time_sink_x_1.set_y_label('Amplitude', "")

        self.qtgui_time_sink_x_1.enable_tags(False)
        self.qtgui_time_sink_x_1.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_x_1.enable_autoscale(True)
        self.qtgui_time_sink_x_1.enable_grid(True)
        self.qtgui_time_sink_x_1.enable_axis_labels(False)
        self.qtgui_time_sink_x_1.enable_control_panel(False)
        self.qtgui_time_sink_x_1.enable_stem_plot(False)

        self.qtgui_time_sink_x_1.disable_legend()

        labels = ['Signal 1', 'Signal 2', 'Signal 3', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_time_sink_x_1.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_time_sink_x_1.set_line_label(i, labels[i])
            self.qtgui_time_sink_x_1.set_line_width(i, widths[i])
            self.qtgui_time_sink_x_1.set_line_color(i, colors[i])
            self.qtgui_time_sink_x_1.set_line_style(i, styles[i])
            self.qtgui_time_sink_x_1.set_line_marker(i, markers[i])
            self.qtgui_time_sink_x_1.set_line_alpha(i, alphas[i])

        self._qtgui_time_sink_x_1_win = sip.wrapinstance(self.qtgui_time_sink_x_1.qwidget(), Qt.QWidget)
        self.tabwid0_grid_layout_1.addWidget(self._qtgui_time_sink_x_1_win, 3, 0, 1, 1)
        for r in range(3, 4):
            self.tabwid0_grid_layout_1.setRowStretch(r, 1)
        for c in range(0, 1):
            self.tabwid0_grid_layout_1.setColumnStretch(c, 1)
        self.qtgui_time_sink_x_0_1 = qtgui.time_sink_f(
            1024, #size
            samp_rate, #samp_rate
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_time_sink_x_0_1.set_update_time(0.10)
        self.qtgui_time_sink_x_0_1.set_y_axis(-1, 1)

        self.qtgui_time_sink_x_0_1.set_y_label('Amplitude', "")

        self.qtgui_time_sink_x_0_1.enable_tags(False)
        self.qtgui_time_sink_x_0_1.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_x_0_1.enable_autoscale(True)
        self.qtgui_time_sink_x_0_1.enable_grid(True)
        self.qtgui_time_sink_x_0_1.enable_axis_labels(False)
        self.qtgui_time_sink_x_0_1.enable_control_panel(False)
        self.qtgui_time_sink_x_0_1.enable_stem_plot(True)

        self.qtgui_time_sink_x_0_1.disable_legend()

        labels = ['1', '2', 'cor access', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['red', 'red', 'magenta', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [2.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_time_sink_x_0_1.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_time_sink_x_0_1.set_line_label(i, labels[i])
            self.qtgui_time_sink_x_0_1.set_line_width(i, widths[i])
            self.qtgui_time_sink_x_0_1.set_line_color(i, colors[i])
            self.qtgui_time_sink_x_0_1.set_line_style(i, styles[i])
            self.qtgui_time_sink_x_0_1.set_line_marker(i, markers[i])
            self.qtgui_time_sink_x_0_1.set_line_alpha(i, alphas[i])

        self._qtgui_time_sink_x_0_1_win = sip.wrapinstance(self.qtgui_time_sink_x_0_1.qwidget(), Qt.QWidget)
        self.tabwid0_grid_layout_2.addWidget(self._qtgui_time_sink_x_0_1_win, 0, 1, 1, 1)
        for r in range(0, 1):
            self.tabwid0_grid_layout_2.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabwid0_grid_layout_2.setColumnStretch(c, 1)
        self.qtgui_time_sink_x_0 = qtgui.time_sink_f(
            1024, #size
            samp_rate, #samp_rate
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_time_sink_x_0.set_update_time(0.10)
        self.qtgui_time_sink_x_0.set_y_axis(-1, 1)

        self.qtgui_time_sink_x_0.set_y_label('Amplitude', "")

        self.qtgui_time_sink_x_0.enable_tags(False)
        self.qtgui_time_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_x_0.enable_autoscale(True)
        self.qtgui_time_sink_x_0.enable_grid(True)
        self.qtgui_time_sink_x_0.enable_axis_labels(False)
        self.qtgui_time_sink_x_0.enable_control_panel(False)
        self.qtgui_time_sink_x_0.enable_stem_plot(True)

        self.qtgui_time_sink_x_0.disable_legend()

        labels = ['1', '2', 'cor access', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['green', 'red', 'magenta', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [2.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [4, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_time_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_time_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_time_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_time_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_time_sink_x_0.set_line_style(i, styles[i])
            self.qtgui_time_sink_x_0.set_line_marker(i, markers[i])
            self.qtgui_time_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_time_sink_x_0_win = sip.wrapinstance(self.qtgui_time_sink_x_0.qwidget(), Qt.QWidget)
        self.tabwid0_grid_layout_2.addWidget(self._qtgui_time_sink_x_0_win, 0, 0, 1, 1)
        for r in range(0, 1):
            self.tabwid0_grid_layout_2.setRowStretch(r, 1)
        for c in range(0, 1):
            self.tabwid0_grid_layout_2.setColumnStretch(c, 1)
        self.qtgui_time_raster_sink_x_0 = qtgui.time_raster_sink_f(
            samp_rate,
            30,
            250,
            [],
            [],
            "",
            1,
            None
        )

        self.qtgui_time_raster_sink_x_0.set_update_time(0.10)
        self.qtgui_time_raster_sink_x_0.set_intensity_range(0, 1)
        self.qtgui_time_raster_sink_x_0.enable_grid(True)
        self.qtgui_time_raster_sink_x_0.enable_axis_labels(False)
        self.qtgui_time_raster_sink_x_0.set_x_label("")
        self.qtgui_time_raster_sink_x_0.set_x_range(0.0, 250)
        self.qtgui_time_raster_sink_x_0.set_y_label("")
        self.qtgui_time_raster_sink_x_0.set_y_range(0.0, 30)

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [1, 0, 0, 0, 0,
            0, 0, 0, 0, 0]
        alphas = [1, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_time_raster_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_time_raster_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_time_raster_sink_x_0.set_color_map(i, colors[i])
            self.qtgui_time_raster_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_time_raster_sink_x_0_win = sip.wrapinstance(self.qtgui_time_raster_sink_x_0.qwidget(), Qt.QWidget)
        self.tabwid0_grid_layout_2.addWidget(self._qtgui_time_raster_sink_x_0_win, 1, 0, 3, 3)
        for r in range(1, 4):
            self.tabwid0_grid_layout_2.setRowStretch(r, 1)
        for c in range(0, 3):
            self.tabwid0_grid_layout_2.setColumnStretch(c, 1)
        self.qtgui_edit_box_msg_1 = qtgui.edit_box_msg(qtgui.STRING, '', 'Decoder counters', False, True, '', None)
        self._qtgui_edit_box_msg_1_win = sip.wrapinstance(self.qtgui_edit_box_msg_1.qwidget(), Qt.QWidget)
        self.tabwid0_grid_layout_0.addWidget(self._qtgui_edit_box_msg_1_win, 4, 0, 1, 4)
        for r in range(4, 5):
            self.tabwid0_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 4):
            self.tabwid0_grid_layout_0.setColumnStretch(c, 1)
        self.qtgui_edit_box_msg_0 = qtgui.edit_box_msg(qtgui.STRING, '', 'Latest decode', False, True, '', None)
        self._qtgui_edit_box_msg_0_win = sip.wrapinstance(self.qtgui_edit_box_msg_0.qwidget(), Qt.QWidget)
        self.tabwid0_grid_layout_0.addWidget(self._qtgui_edit_box_msg_0_win, 3, 0, 1, 4)
        for r in range(3, 4):
            self.tabwid0_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 4):
            self.tabwid0_grid_layout_0.setColumnStretch(c, 1)
        self.low_pass_filter_1 = filter.fir_filter_fff(
            1,
            firdes.low_pass(
                1,
                (samp_rate/decimation),
                (1.5*300),
                1e3,
                window.WIN_HAMMING,
                6.76))
        self.low_pass_filter_0_0 = filter.fir_filter_ccf(
            1,
            firdes.low_pass(
                1,
                192000,
                50,
                10000,
                window.WIN_HAMMING,
                6.76))
        self.low_pass_filter_0 = filter.fir_filter_ccf(
            decimation,
            firdes.low_pass(
                1,
                samp_rate,
                5e3,
                1e3,
                window.WIN_HAMMING,
                6.76))
        self.epy_block_2 = epy_block_2.mqtt_event_publisher(broker_host=mqtt_broker_host, broker_port=mqtt_broker_port, username=mqtt_username, password=mqtt_password, topic_prefix=mqtt_topic_prefix)
        self.epy_block_1 = epy_block_1.alert_protocol_decoder(
            center_freq_hz=center_freq,
            rf_gain_db=rfGain,
            rf_squelch_db=rf_squelch,
            demod_mode=demod_mode,
            afsk_mark_hz=afsk_mark_hz,
            afsk_space_hz=afsk_space_hz,
        )
        self.epy_block_0 = epy_block_0.blk(base_path=log_base_path)
        self.digital_symbol_sync_xx_0 = digital.symbol_sync_ff(
            digital.TED_EARLY_LATE,
            (demod_rate/300),
            (2*math.pi*0.04),
            1.0,
            1.0,
            1,
            1,
            digital.constellation_bpsk().base(),
            digital.IR_MMSE_8TAP,
            128,
            [])
        self.blocks_null_source_0 = blocks.null_source(gr.sizeof_float*1)
        self.blocks_null_sink_2 = blocks.null_sink(gr.sizeof_float*1)
        self.blocks_multiply_const_vxx_0 = blocks.multiply_const_ff(1)
        _headless = os.environ.get('FWLAB_HEADLESS', '0') == '1'
        _audio_dev = os.environ.get('FWLAB_AUDIO_DEVICE', '').strip()
        if _headless:
            self.audio_sink_1 = blocks.null_sink(gr.sizeof_float*1)
            self.audio_sink_0 = blocks.null_sink(gr.sizeof_float*1)
        else:
            # Keep only one real ALSA sink to avoid device contention/asserts.
            self.audio_sink_1 = blocks.null_sink(gr.sizeof_float*1)
            self.audio_sink_0 = audio.sink(samp_rate_audio, _audio_dev, False)
        self.analog_wfm_rcv_0 = analog.wfm_rcv(
        	quad_rate=192000,
        	audio_decimation=4,
        )
        self.analog_simple_squelch_cc_0 = analog.simple_squelch_cc(rf_squelch, 1)
        self.analog_quadrature_demod_cf_0 = analog.quadrature_demod_cf(((samp_rate/decimation)/(2*math.pi*fsk_deviation_hz)))
        self.analog_agc_xx_0_0 = analog.agc_ff((1e-3), 1, 1)
        self.analog_agc_xx_0_0.set_max_gain(65536)
        self.analog_agc_xx_0 = analog.agc_ff((1e-4), 1.0, 1.0)
        self.analog_agc_xx_0.set_max_gain(0)


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.epy_block_1, 'debug_out'), (self.epy_block_0, 'msg_in'))
        self.msg_connect((self.epy_block_1, 'debug_out'), (self.epy_block_2, 'msg_in'))
        self.msg_connect((self.epy_block_1, 'debug_out'), (self.qtgui_edit_box_msg_0, 'val'))
        self.msg_connect((self.epy_block_1, 'stats_out'), (self.qtgui_edit_box_msg_1, 'val'))
        self.connect((self.analog_agc_xx_0, 0), (self.low_pass_filter_1, 0))
        self.connect((self.analog_agc_xx_0_0, 0), (self.blocks_multiply_const_vxx_0, 0))
        self.connect((self.analog_quadrature_demod_cf_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.analog_simple_squelch_cc_0, 0), (self.analog_quadrature_demod_cf_0, 0))
        self.connect((self.analog_wfm_rcv_0, 0), (self.analog_agc_xx_0_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.audio_sink_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.qtgui_time_sink_x_1, 0))
        self.connect((self.blocks_null_source_0, 0), (self.audio_sink_1, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.epy_block_1, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.qtgui_time_raster_sink_x_0, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.qtgui_time_sink_x_0_1, 0))
        self.connect((self.epy_block_1, 0), (self.blocks_null_sink_2, 0))
        self.connect((self.low_pass_filter_0, 0), (self.analog_simple_squelch_cc_0, 0))
        self.connect((self.low_pass_filter_0, 0), (self.qtgui_waterfall_sink_x_1, 0))
        self.connect((self.low_pass_filter_0_0, 0), (self.analog_wfm_rcv_0, 0))
        self.connect((self.low_pass_filter_1, 0), (self.digital_symbol_sync_xx_0, 0))
        self.connect((self.low_pass_filter_1, 0), (self.qtgui_time_sink_x_0, 0))
        self.connect((self.low_pass_filter_1, 0), (self.qtgui_waterfall_sink_x_1_1, 0))
        self.connect((self.rational_resampler_xxx_0, 0), (self.low_pass_filter_0_0, 0))
        self.connect((self.rtlsdr_source_0, 0), (self.low_pass_filter_0, 0))
        self.connect((self.rtlsdr_source_0, 0), (self.rational_resampler_xxx_0, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "ALERT1v3")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_demod_rate(self.samp_rate/self.decimation)
        self.analog_quadrature_demod_cf_0.set_gain(((self.samp_rate/self.decimation)/(2*math.pi*self.fsk_deviation_hz)))
        self.low_pass_filter_0.set_taps(firdes.low_pass(1, self.samp_rate, 5e3, 1e3, window.WIN_HAMMING, 6.76))
        self.low_pass_filter_1.set_taps(firdes.low_pass(1, (self.samp_rate/self.decimation), (1.5*300), 1e3, window.WIN_HAMMING, 6.76))
        self.qtgui_time_sink_x_0.set_samp_rate(self.samp_rate)
        self.qtgui_time_sink_x_0_1.set_samp_rate(self.samp_rate)
        self.rtlsdr_source_0.set_sample_rate(self.samp_rate)

    def get_fsk_deviation_hz(self):
        return self.fsk_deviation_hz

    def set_fsk_deviation_hz(self, fsk_deviation_hz):
        self.fsk_deviation_hz = fsk_deviation_hz
        self.set_transition_bw(self.fsk_deviation_hz/2)
        self.analog_quadrature_demod_cf_0.set_gain(((self.samp_rate/self.decimation)/(2*math.pi*self.fsk_deviation_hz)))

    def get_decimation(self):
        return self.decimation

    def set_decimation(self, decimation):
        self.decimation = decimation
        self.set_demod_rate(self.samp_rate/self.decimation)
        self.analog_quadrature_demod_cf_0.set_gain(((self.samp_rate/self.decimation)/(2*math.pi*self.fsk_deviation_hz)))
        self.low_pass_filter_1.set_taps(firdes.low_pass(1, (self.samp_rate/self.decimation), (1.5*300), 1e3, window.WIN_HAMMING, 6.76))

    def get_transition_bw(self):
        return self.transition_bw

    def set_transition_bw(self, transition_bw):
        self.transition_bw = transition_bw

    def get_samp_rate_audio(self):
        return self.samp_rate_audio

    def set_samp_rate_audio(self, samp_rate_audio):
        self.samp_rate_audio = samp_rate_audio

    def get_rf_squelch(self):
        return self.rf_squelch

    def set_rf_squelch(self, rf_squelch):
        self.rf_squelch = rf_squelch
        self.analog_simple_squelch_cc_0.set_threshold(self.rf_squelch)

    def get_rfGain(self):
        return self.rfGain

    def set_rfGain(self, rfGain):
        self.rfGain = rfGain
        self.rtlsdr_source_0.set_gain(self.rfGain, 0)

    def get_mqtt_username(self):
        return self.mqtt_username

    def set_mqtt_username(self, mqtt_username):
        self.mqtt_username = mqtt_username
        self.epy_block_2.username = self.mqtt_username

    def get_mqtt_topic_prefix(self):
        return self.mqtt_topic_prefix

    def set_mqtt_topic_prefix(self, mqtt_topic_prefix):
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.epy_block_2.topic_prefix = self.mqtt_topic_prefix

    def get_mqtt_password(self):
        return self.mqtt_password

    def set_mqtt_password(self, mqtt_password):
        self.mqtt_password = mqtt_password
        self.epy_block_2.password = self.mqtt_password

    def get_mqtt_broker_port(self):
        return self.mqtt_broker_port

    def set_mqtt_broker_port(self, mqtt_broker_port):
        self.mqtt_broker_port = mqtt_broker_port
        self.epy_block_2.broker_port = self.mqtt_broker_port

    def get_mqtt_broker_host(self):
        return self.mqtt_broker_host

    def set_mqtt_broker_host(self, mqtt_broker_host):
        self.mqtt_broker_host = mqtt_broker_host
        self.epy_block_2.broker_host = self.mqtt_broker_host

    def get_log_base_path(self):
        return self.log_base_path

    def set_log_base_path(self, log_base_path):
        self.log_base_path = log_base_path
        self.epy_block_0.base_path = self.log_base_path

    def get_demod_rate(self):
        return self.demod_rate

    def set_demod_rate(self, demod_rate):
        self.demod_rate = demod_rate

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.rtlsdr_source_0.set_center_freq(self.center_freq, 0)




def main(top_block_cls=ALERT1v3, options=None):

    if StrictVersion("4.5.0") <= StrictVersion(Qt.qVersion()) < StrictVersion("5.0.0"):
        style = gr.prefs().get_string('qtgui', 'style', 'raster')
        Qt.QApplication.setGraphicsSystem(style)
    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
