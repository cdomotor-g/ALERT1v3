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

    Message outputs:
      - debug_out (PMT dict with structured decode payload)
      - stats_out (operator-friendly string counters)
    """

    FRAME_WORDS = 4
    PAYLOAD_BITS_PER_WORD = 8
    HUNT_TIMEOUT_SAMPLES = 3000  # ~10s at ~300 sym/s from current chain

    def __init__(self):
        gr.basic_block.__init__(
            self,
            name="ALERT Protocol Decoder",
            in_sig=[np.float32],
            out_sig=[np.float32],
        )

        self.message_port_register_out(pmt.intern("debug_out"))
        self.message_port_register_out(pmt.intern("stats_out"))

        self.state = "HUNTING_S"
        self.bit_buffer = []
        self.message_bits = []
        self.bits_per_word = 10
        self.word_count = 0

        self.frames_decoded = 0
        self.frames_dropped_output_full = 0
        self.frames_total = 0
        self.error_total = 0
        self._window_decode = 0
        self._window_errors = 0
        self._window_started = datetime.datetime.utcnow()

        self._samples_since_frame = 0
        self._hunt_timeout_raised = False

    def _publish_event(self, event_dict):
        try:
            msg = pmt.to_pmt(event_dict)
        except Exception:
            msg = pmt.intern(str(event_dict))
        self.message_port_pub(pmt.intern("debug_out"), msg)

    def _now_iso(self):
        return datetime.datetime.utcnow().isoformat() + "Z"

    def _publish_decode_error(self, error_code, message, details=None):
        event = {
            "schema": "alert.decode.v1",
            "ts": self._now_iso(),
            "status": "error",
            "quality": {
                "score": 0.0,
                "confidence": "low",
            },
            "errors": [{
                "code": error_code,
                "message": message,
            }],
            "frame": details or {},
            "decode": {},
            "summary": f"ERROR: {error_code}",
            "display": f"ERROR: {error_code}",
        }
        self._publish_event(event)

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

    def _assess_quality(self, bits, format_id):
        errors = []
        score = 1.0

        expected_len = self.FRAME_WORDS * self.PAYLOAD_BITS_PER_WORD
        if len(bits) != expected_len:
            errors.append({"code": "framing.length_mismatch", "message": f"expected {expected_len} bits got {len(bits)}"})
            score -= 0.6

        if format_id not in (0, 1, 2, 3):
            errors.append({"code": "decode.invalid_format_id", "message": f"invalid format_id={format_id}"})
            score -= 0.6

        ones = sum(int(b) for b in bits)
        ratio = ones / len(bits) if bits else 0.0
        if ratio < 0.10 or ratio > 0.90:
            errors.append({"code": "signal.bit_balance_extreme", "message": f"ones_ratio={ratio:.3f}"})
            score -= 0.25

        score = max(0.0, min(1.0, score))
        confidence = "high" if score >= 0.85 else ("medium" if score >= 0.60 else "low")

        return {
            "score": round(score, 3),
            "confidence": confidence,
            "ones_ratio": round(ratio, 3),
        }, errors

    def _decode_message_bits(self, bits):
        msg_int = np.uint32(0)
        for b in bits:
            msg_int = (msg_int << 1) | np.uint32(b)

        sensor_id = (msg_int >> 0) & 0x3F
        sensor_id |= ((msg_int >> 8) & 0x3F) << 6
        sensor_id |= ((msg_int >> 16) & 0x01) << 12

        format_id = int((msg_int >> 6) & 0x03)
        is_binary = format_id == 2

        data_val = (msg_int >> 17) & 0x1F
        data_val |= ((msg_int >> 24) & 0x3F) << 5

        raw_bits = ''.join(str(int(b)) for b in bits)
        raw_hex = f"{int(msg_int):08X}"

        quality, errors = self._assess_quality(bits, format_id)
        status = "ok" if not errors else ("warn" if quality["score"] >= 0.60 else "error")

        summary = f"{int(sensor_id):04d}, {int(data_val):06d}"

        return {
            "schema": "alert.decode.v1",
            "ts": self._now_iso(),
            "status": status,
            "quality": quality,
            "errors": errors,
            "frame": {
                "bits_per_word": self.bits_per_word,
                "word_count": self.FRAME_WORDS,
                "payload_bits": raw_bits,
                "payload_hex": raw_hex,
            },
            "decode": {
                "sensor_id": int(sensor_id),
                "format_id": format_id,
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
            self._samples_since_frame += 1

            if self.state == "HUNTING_S":
                if logical_bit == 1:
                    self.state = "COLLECTING_WORD"
                    self.bit_buffer = [logical_bit]

                if self._samples_since_frame >= self.HUNT_TIMEOUT_SAMPLES and not self._hunt_timeout_raised:
                    self._publish_decode_error(
                        "timing.hunt_timeout",
                        "no complete frame detected within hunt timeout",
                        details={
                            "samples_since_frame": int(self._samples_since_frame),
                            "timeout_samples": int(self.HUNT_TIMEOUT_SAMPLES),
                        },
                    )
                    self.error_total += 1
                    self._window_errors += 1
                    self._hunt_timeout_raised = True
                continue

            if self.state == "COLLECTING_WORD":
                self.bit_buffer.append(logical_bit)

                if len(self.bit_buffer) < self.bits_per_word:
                    continue

                self.message_bits.extend(self.bit_buffer[1:9])
                self.word_count += 1

                if self.word_count == self.FRAME_WORDS:
                    event = self._decode_message_bits(self.message_bits)
                    self._publish_event(event)
                    self.frames_total += 1
                    self._samples_since_frame = 0
                    self._hunt_timeout_raised = False

                    if event.get("errors"):
                        self.error_total += len(event.get("errors"))
                        self._window_errors += len(event.get("errors"))

                    if produced < out_capacity:
                        out0[produced] = float(event["decode"]["data_val"])
                        produced += 1
                        self.frames_decoded += 1
                        self._window_decode += 1
                    else:
                        self.frames_dropped_output_full += 1
                        self.error_total += 1
                        self._window_errors += 1
                        self._publish_decode_error(
                            "pipeline.output_overflow",
                            "output buffer full; decode output sample dropped",
                            details={"out_capacity": int(out_capacity)},
                        )

                    self._reset_frame_collection()
                else:
                    self._reset_word_collection()

                self._publish_stats_if_due()

        self._publish_stats_if_due()
        self.consume(0, consumed)
        return produced
