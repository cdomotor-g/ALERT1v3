#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Not titled yet
# GNU Radio version: 3.10.5.1

from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import bokehgui
import math
import osmosdr
import time




class bokeh_test_1(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "Not titled yet", catch_exceptions=True)
        self.plot_lst = []
        self.widget_lst = []

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 2.048e6
        self.fsk_deviation_hz = fsk_deviation_hz = 16e3
        self.decimation = decimation = 250
        self.transition_bw = transition_bw = fsk_deviation_hz/2
        self.rfGain = rfGain = 40
        self.demod_rate = demod_rate = samp_rate/decimation
        self.center_freq = center_freq = 173.9e6

        ##################################################
        # Blocks
        ##################################################

        self.rtlsdr_source_0 = osmosdr.source(
            args="numchan=" + str(1) + " " + ''
        )
        self.rtlsdr_source_0.set_time_now(osmosdr.time_spec_t(time.time()), osmosdr.ALL_MBOARDS)
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
        self.low_pass_filter_0 = filter.fir_filter_ccf(
            decimation,
            firdes.low_pass(
                1,
                samp_rate,
                5e3,
                1e3,
                window.WIN_HAMMING,
                6.76))
        self.bokehgui_waterfall_sink_x_0 = bokehgui.waterfall_sink_c_proc(256, window.WIN_BLACKMAN_hARRIS, 0,100e3, "")

        legend_list = []
        for i in  range(1):
          if len('') == 0:
            legend_list.append("Data {0}".format(i))
          else:
            legend_list.append('')
        self.bokehgui_waterfall_sink_x_0_plot = bokehgui.waterfall_sink_c(self.plot_lst, self.bokehgui_waterfall_sink_x_0, update_time = 100,
                      legend_list = legend_list, palette = 'Inferno',
                      values_range = [-140, 10], is_message =    False  )

        self.bokehgui_waterfall_sink_x_0_plot.set_y_label('Time' + '(' +''+')')
        self.bokehgui_waterfall_sink_x_0_plot.set_x_label('Frequency' + '(' +'Hz'+')')
        self.bokehgui_waterfall_sink_x_0_plot.enable_grid(False)
        self.bokehgui_waterfall_sink_x_0_plot.enable_legend(True)
        self.bokehgui_waterfall_sink_x_0_plot.set_layout(*(1,0,2,2))


        ##################################################
        # Connections
        ##################################################
        self.connect((self.low_pass_filter_0, 0), (self.bokehgui_waterfall_sink_x_0, 0))
        self.connect((self.rtlsdr_source_0, 0), (self.low_pass_filter_0, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_demod_rate(self.samp_rate/self.decimation)
        self.low_pass_filter_0.set_taps(firdes.low_pass(1, self.samp_rate, 5e3, 1e3, window.WIN_HAMMING, 6.76))
        self.rtlsdr_source_0.set_sample_rate(self.samp_rate)

    def get_fsk_deviation_hz(self):
        return self.fsk_deviation_hz

    def set_fsk_deviation_hz(self, fsk_deviation_hz):
        self.fsk_deviation_hz = fsk_deviation_hz
        self.set_transition_bw(self.fsk_deviation_hz/2)

    def get_decimation(self):
        return self.decimation

    def set_decimation(self, decimation):
        self.decimation = decimation
        self.set_demod_rate(self.samp_rate/self.decimation)

    def get_transition_bw(self):
        return self.transition_bw

    def set_transition_bw(self, transition_bw):
        self.transition_bw = transition_bw

    def get_rfGain(self):
        return self.rfGain

    def set_rfGain(self, rfGain):
        self.rfGain = rfGain
        self.rtlsdr_source_0.set_gain(self.rfGain, 0)

    def get_demod_rate(self):
        return self.demod_rate

    def set_demod_rate(self, demod_rate):
        self.demod_rate = demod_rate

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.rtlsdr_source_0.set_center_freq(self.center_freq, 0)




def main(top_block_cls=bokeh_test_1, options=None):
    # Create Top Block instance
    tb = top_block_cls()

    try:
        tb.start()

        bokehgui.utils.run_server(tb, sizing_mode = "fixed",  widget_placement =  (0, 0), window_size =  (1000, 1000))
    finally:
        print("Exiting the simulation. Stopping Bokeh Server")
        tb.stop()
        tb.wait()


if __name__ == '__main__':
    main()
