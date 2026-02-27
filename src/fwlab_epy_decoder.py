import numpy as np
from gnuradio import gr
import pmt
import datetime


class alert_protocol_decoder(gr.basic_block):
    """
    ALERT protocol decoder.

    Input:
      - float stream containing symbol decisions / soft-ish values

    Output stream (single float, kept for GRC compatibility):
      - decoded data_val as float

    Message output:
      - debug_out (PMT dict with structured decode payload)
    """

    FRAME_WORDS = 4

    def __init__(self, center_freq_hz=173900000.0, rf_gain_db=40.0, rf_squelch_db=-33.0):
        gr.basic_block.__init__(
            self,
            name="ALERT Protocol Decoder",
            in_sig=[np.float32],
            out_sig=[np.float32],
        )

        self.center_freq_hz = float(center_freq_hz)
        self.rf_gain_db = float(rf_gain_db)
        self.rf_squelch_db = float(rf_squelch_db)

        self.message_port_register_out(pmt.intern("debug_out"))
        self.message_port_register_out(pmt.intern("stats_out"))

        self.state = "HUNTING_S"
        self.bit_buffer = []
        self.message_bits = []
        self.bits_per_word = 10
        self.word_count = 0

        # Runtime counters to help verify behavior during long runs.
        self.frames_decoded = 0
        self.frames_dropped_output_full = 0
        self.frames_total = 0
        self.error_total = 0
        self._window_decode = 0
        self._window_errors = 0
        self._window_started = datetime.datetime.utcnow()

    def _publish_event(self, event_dict):
        try:
            msg = pmt.to_pmt(event_dict)
        except Exception:
            # Fallback to string if PMT conversion fails for any reason.
            msg = pmt.intern(str(event_dict))
        self.message_port_pub(pmt.intern("debug_out"), msg)

    def _reset_word_collection(self):
        self.state = "HUNTING_S"
        self.bit_buffer = []

    def _reset_frame_collection(self):
        self.word_count = 0
        self.message_bits = []
        self._reset_word_collection()

    def _publish_stats_if_due(self, force=False):
        now = datetime.datetime.utcnow()
        elapsed = (now - self._window_started).total_seconds()
        if not force and elapsed < 1.0:
            return

        decode_rate = (self._window_decode / elapsed) if elapsed > 0 else 0.0
        stats = {
            "schema": "alert.operator.stats.v1",
            "ts": now.isoformat() + "Z",
            "decode_rate_hz": round(float(decode_rate), 3),
            "total_decodes": int(self.frames_total),
            "recent_errors": int(self._window_errors),
            "error_total": int(self.error_total),
            "window_seconds": round(float(elapsed), 3),
            "display": f"rate={decode_rate:.2f}/s | total={self.frames_total} | recent_errors={self._window_errors}",
        }
        self.message_port_pub(pmt.intern("stats_out"), pmt.to_pmt(stats["display"]))

        self._window_started = now
        self._window_decode = 0
        self._window_errors = 0

    def _decode_message_bits(self, bits):
        """Decode 32 collected bits into fields using current legacy mapping."""
        msg_int = np.uint32(0)
        for b in bits:
            msg_int = (msg_int << 1) | np.uint32(b)

        sensor_id = (msg_int >> 0) & 0x3F
        sensor_id |= ((msg_int >> 8) & 0x3F) << 6
        sensor_id |= ((msg_int >> 16) & 0x01) << 12

        format_id = (msg_int >> 6) & 0x03
        is_binary = format_id == 2

        data_val = (msg_int >> 17) & 0x1F
        data_val |= ((msg_int >> 24) & 0x3F) << 5

        raw_bits = ''.join(str(int(b)) for b in bits)
        raw_hex = f"{int(msg_int):08X}"

        summary = f"{int(sensor_id):04d}, {int(data_val):06d}"

        return {
            "schema": "alert.decode.v1",
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "status": "ok",
            "rx": {
                "center_freq_hz": self.center_freq_hz,
                "rf_gain_db": self.rf_gain_db,
                "rf_squelch_db": self.rf_squelch_db,
            },
            "frame": {
                "bits_per_word": self.bits_per_word,
                "word_count": self.FRAME_WORDS,
                "payload_bits": raw_bits,
                "payload_hex": raw_hex,
            },
            "decode": {
                "sensor_id": int(sensor_id),
                "format_id": int(format_id),
                "is_binary": bool(is_binary),
                "data_val": int(data_val),
            },
            "summary": summary,
            "display": summary,
        }

    def general_work(self, input_items, output_items):
        in0 = input_items[0]
        out0 = output_items[0]

        consumed = 0
        produced = 0
        out_capacity = len(out0)

        for float_sample in in0:
            logical_bit = 1 if float_sample > 0.5 else 0
            consumed += 1

            if self.state == "HUNTING_S":
                if logical_bit == 1:
                    self.state = "COLLECTING_WORD"
                    self.bit_buffer = [logical_bit]
                continue

            if self.state == "COLLECTING_WORD":
                self.bit_buffer.append(logical_bit)

                if len(self.bit_buffer) < self.bits_per_word:
                    continue

                # Keep legacy behavior: consume payload bits [1:9] from each 10-bit word.
                self.message_bits.extend(self.bit_buffer[1:9])
                self.word_count += 1

                if self.word_count == self.FRAME_WORDS:
                    event = self._decode_message_bits(self.message_bits)
                    self._publish_event(event)
                    self.frames_total += 1

                    if produced < out_capacity:
                        out0[produced] = float(event["decode"]["data_val"])
                        produced += 1
                        self.frames_decoded += 1
                        self._window_decode += 1
                    else:
                        # Keep decoding/logging alive even when scheduler gives no output room.
                        self.frames_dropped_output_full += 1
                        self.error_total += 1
                        self._window_errors += 1

                    self._reset_frame_collection()
                else:
                    self._reset_word_collection()

                self._publish_stats_if_due()

        self._publish_stats_if_due()
        self.consume(0, consumed)
        return produced
