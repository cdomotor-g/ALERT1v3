import numpy as np
from gnuradio import gr
import pmt
import datetime
import json


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

    Notes:
    - 10-bit word framing is explicitly handled as:
        start bit + 8 data bits + stop bit
    - Data bit ordering can be configured (LSB-first vs MSB-first) to
      support differing over-the-air framing conventions.
    """

    FRAME_WORDS = 4
    PAYLOAD_BITS_PER_WORD = 8
    HUNT_TIMEOUT_SAMPLES = 3000

    def __init__(
        self,
        center_freq_hz=173900000.0,
        rf_gain_db=40.0,
        rf_squelch_db=-33.0,
        start_bit=0,
        stop_bit=1,
        word_lsb_first=True,
        invert_bits=True,
        strict_mode=True,
        enforce_fixed_pairs=True,
        fixed_pair_hard_reject=False,
        fixed_pair_patterns_json='[[[1,0],[1,0],[1,1],[1,1]]]',
        demod_mode='legacy_fsk',
        afsk_mark_hz=2100.0,
        afsk_space_hz=1300.0,
    ):
        gr.basic_block.__init__(
            self,
            name="ALERT Protocol Decoder",
            in_sig=[np.float32],
            out_sig=[np.float32],
        )

        self.center_freq_hz = float(center_freq_hz)
        self.rf_gain_db = float(rf_gain_db)
        self.rf_squelch_db = float(rf_squelch_db)

        self.start_bit = 1 if int(start_bit) else 0
        self.stop_bit = 1 if int(stop_bit) else 0
        self.word_lsb_first = bool(word_lsb_first)
        self.invert_bits = bool(invert_bits)
        self.strict_mode = bool(strict_mode)
        self.enforce_fixed_pairs = bool(enforce_fixed_pairs)
        self.fixed_pair_hard_reject = bool(fixed_pair_hard_reject)
        self.demod_mode = str(demod_mode or 'legacy_fsk')
        self.afsk_mark_hz = float(afsk_mark_hz)
        self.afsk_space_hz = float(afsk_space_hz)

        self.fixed_pair_patterns = [
            [[1, 0], [1, 0], [1, 1], [1, 1]],
        ]
        try:
            parsed = json.loads(str(fixed_pair_patterns_json))
            if isinstance(parsed, list) and parsed:
                norm = []
                for pat in parsed:
                    if not isinstance(pat, list) or len(pat) != 4:
                        continue
                    p = []
                    ok = True
                    for w in pat:
                        if not isinstance(w, list) or len(w) != 2:
                            ok = False
                            break
                        p.append([1 if int(w[0]) else 0, 1 if int(w[1]) else 0])
                    if ok:
                        norm.append(p)
                if norm:
                    self.fixed_pair_patterns = norm
        except Exception:
            pass

        self.message_port_register_out(pmt.intern("debug_out"))
        self.message_port_register_out(pmt.intern("stats_out"))

        self.state = "HUNTING_S"
        self.bit_buffer = []
        self.word_sample_buffer = []
        self.message_bits = []
        self.message_symbol_samples = []
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
            "ts": self._now_iso(),
            "status": "error",
            "summary": f"ERROR: {error_code}",
            "frame": details or {},
            "errors": [{"code": error_code, "message": message}],
            "decode": {},
            "quality": {"score": 0.0, "confidence": "low"},
            "rx": {
                "center_freq_hz": self.center_freq_hz,
                "rf_gain_db": self.rf_gain_db,
                "rf_squelch_db": self.rf_squelch_db,
                "demod_mode": self.demod_mode,
                "afsk_mark_hz": self.afsk_mark_hz,
                "afsk_space_hz": self.afsk_space_hz,
            },
            "display": f"ERROR: {error_code}",
            "schema": "alert.decode.v1",
        }
        self._publish_event(event)

    def _reset_word_collection(self):
        self.state = "HUNTING_S"
        self.bit_buffer = []
        self.word_sample_buffer = []

    def _reset_frame_collection(self):
        self.word_count = 0
        self.message_bits = []
        self.message_symbol_samples = []
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

    def _assess_quality(self, bits, format_id, symbol_samples=None):
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

        snr_db = None
        eye_opening = None
        if symbol_samples and len(symbol_samples) == len(bits):
            try:
                vals = np.array(symbol_samples, dtype=np.float32)
                bb = np.array(bits, dtype=np.int8)
                v1 = vals[bb == 1]
                v0 = vals[bb == 0]
                if len(v1) >= 4 and len(v0) >= 4:
                    m1 = float(np.mean(v1))
                    m0 = float(np.mean(v0))
                    eye_opening = abs(m1 - m0)
                    sigma = float(np.sqrt((np.var(v1) + np.var(v0)) / 2.0)) + 1e-6
                    snr_lin = ((m1 - m0) ** 2) / (sigma ** 2)
                    snr_db = 10.0 * np.log10(max(snr_lin, 1e-6))
                    if snr_db < 3.0:
                        errors.append({"code": "signal.low_snr_proxy", "message": f"snr_db_proxy={snr_db:.2f}"})
                        score -= 0.2
            except Exception:
                pass

        score = max(0.0, min(1.0, score))
        confidence = "high" if score >= 0.85 else ("medium" if score >= 0.60 else "low")

        out = {
            "score": round(score, 3),
            "confidence": confidence,
            "ones_ratio": round(ratio, 3),
            "snr_db_proxy": round(float(snr_db), 3) if snr_db is not None else None,
            "eye_opening": round(float(eye_opening), 4) if eye_opening is not None else None,
            "snr_available": bool(snr_db is not None),
        }
        return out, errors

    def _bits_to_int_lsb(self, bits_lsb_first):
        v = 0
        for i, b in enumerate(bits_lsb_first):
            v |= (int(b) & 1) << i
        return int(v)

    def _decode_message_bits(self, bits, symbol_samples=None):
        # bits is expected as 32 payload bits in word order:
        # p1(8) + p2(8) + p3(8) + p4(8), each payload in LSB->MSB order.
        if len(bits) != 32:
            return {
                "schema": "alert.decode.v1",
                "ts": self._now_iso(),
                "status": "error",
                "quality": {"score": 0.0, "confidence": "low", "ones_ratio": 0.0},
                "errors": [{"code": "framing.length_mismatch", "message": f"expected 32 payload bits got {len(bits)}"}],
                "rx": {
                    "center_freq_hz": self.center_freq_hz,
                    "rf_gain_db": self.rf_gain_db,
                    "rf_squelch_db": self.rf_squelch_db,
                    "demod_mode": self.demod_mode,
                    "afsk_mark_hz": self.afsk_mark_hz,
                    "afsk_space_hz": self.afsk_space_hz,
                },
                "frame": {"payload_bits": ''.join(str(int(b)) for b in bits), "payload_hex": ""},
                "decode": {},
                "summary": "ERROR: framing.length_mismatch",
                "display": "ERROR: framing.length_mismatch",
            }

        p1, p2, p3, p4 = bits[0:8], bits[8:16], bits[16:24], bits[24:32]

        errors = []
        # ALERT Binary fixed pair bits validation:
        # p1[6:8]=10, p2[6:8]=10, p3[6:8]=11, p4[6:8]=11
        observed_pairs = [list(p1[6:8]), list(p2[6:8]), list(p3[6:8]), list(p4[6:8])]
        fixed_pair_mismatch = False
        fixed_pair_pattern_id = None
        if self.enforce_fixed_pairs:
            for i, pat in enumerate(self.fixed_pair_patterns):
                if pat == observed_pairs:
                    fixed_pair_pattern_id = i
                    break
            if fixed_pair_pattern_id is None:
                fixed_pair_mismatch = True
                for wi, pair in enumerate(observed_pairs, start=1):
                    errors.append({
                        "code": f"decode.fixed_pair_mismatch_w{wi}",
                        "message": f"w{wi} pair={pair} no configured pattern matched",
                    })

        # Extract ALERT AU binary fields (LSB-first per spec).
        a_bits = []
        a_bits.extend(p1[0:6])
        a_bits.extend(p2[0:6])
        a_bits.append(p3[0])

        d_bits = []
        d_bits.extend(p3[1:6])
        d_bits.extend(p4[0:6])

        sensor_id = self._bits_to_int_lsb(a_bits)
        data_val = self._bits_to_int_lsb(d_bits)

        # keep existing format flags as derived placeholder
        format_id = 2 if (p3[6:8] == [1, 1] and p4[6:8] == [1, 1]) else 1
        is_binary = True

        raw_bits = ''.join(str(int(b)) for b in bits)
        # Convert payload to int for hex display in arrival bit order
        msg_int = np.uint32(0)
        for b in bits:
            msg_int = (msg_int << 1) | np.uint32(int(b))
        raw_hex = f"{int(msg_int):08X}"

        quality, q_errors = self._assess_quality(bits, format_id, symbol_samples=symbol_samples)
        errors.extend(q_errors)

        hard_reject = False
        if self.strict_mode:
            if int(msg_int) == 0:
                errors.append({"code": "decode.zero_payload", "message": "payload is all zero"})
                hard_reject = True
            if int(sensor_id) == 0:
                errors.append({"code": "decode.zero_sensor_id", "message": "sensor_id is zero"})
                hard_reject = True
            if fixed_pair_mismatch and self.fixed_pair_hard_reject:
                hard_reject = True

        status = "ok" if not errors else ("warn" if quality["score"] >= 0.60 else "error")
        if hard_reject:
            status = "error"
        summary = f"{int(sensor_id):04d}, {int(data_val):06d}"

        return {
            "ts": self._now_iso(),
            "status": status,
            "summary": summary,
            "frame": {
                "bits_per_word": self.bits_per_word,
                "word_count": self.FRAME_WORDS,
                "payload_bits": raw_bits,
                "payload_hex": raw_hex,
                "start_bit": self.start_bit,
                "stop_bit": self.stop_bit,
                "word_lsb_first": self.word_lsb_first,
                "invert_bits": self.invert_bits,
                "enforce_fixed_pairs": self.enforce_fixed_pairs,
                "fixed_pair_hard_reject": self.fixed_pair_hard_reject,
                "fixed_pair_patterns": self.fixed_pair_patterns,
                "fixed_pair_observed": observed_pairs,
                "fixed_pair_pattern_id": fixed_pair_pattern_id,
                "symbol_samples": [round(float(x), 4) for x in (symbol_samples or [])],
            },
            "errors": errors,
            "decode": {
                "sensor_id": int(sensor_id),
                "format_id": format_id,
                "is_binary": bool(is_binary),
                "data_val": int(data_val),
                "fixed_pair_pattern_id": fixed_pair_pattern_id,
            },
            "quality": quality,
            "rx": {
                "center_freq_hz": self.center_freq_hz,
                "rf_gain_db": self.rf_gain_db,
                "rf_squelch_db": self.rf_squelch_db,
                "demod_mode": self.demod_mode,
                "afsk_mark_hz": self.afsk_mark_hz,
                "afsk_space_hz": self.afsk_space_hz,
            },
            "display": summary,
            "schema": "alert.decode.v1",
        }

    def _normalize_bit(self, float_sample):
        b = 1 if float_sample > 0.5 else 0
        if self.invert_bits:
            b = 0 if b else 1
        return b

    def _extract_word_payload_bits(self, word_bits):
        # word_bits length = 10: [start][8 data][stop]
        # ALERT spec says payload bits are transmitted LSB->MSB.
        data_bits = list(word_bits[1:9])
        # If word_lsb_first=False, reinterpret as MSB-first and reverse into LSB order.
        if not self.word_lsb_first:
            data_bits = list(reversed(data_bits))
        return data_bits

    def general_work(self, input_items, output_items):
        in0 = input_items[0]
        out0 = output_items[0]

        consumed = 0
        produced = 0
        out_capacity = len(out0)

        for float_sample in in0:
            logical_bit = self._normalize_bit(float_sample)
            consumed += 1
            self._samples_since_frame += 1

            if self.state == "HUNTING_S":
                if logical_bit == self.start_bit:
                    self.state = "COLLECTING_WORD"
                    self.bit_buffer = [logical_bit]
                    self.word_sample_buffer = [float(float_sample)]

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
                self.word_sample_buffer.append(float(float_sample))

                if len(self.bit_buffer) < self.bits_per_word:
                    continue

                # Validate explicit start/stop framing for each 10-bit word.
                if self.bit_buffer[0] != self.start_bit or self.bit_buffer[-1] != self.stop_bit:
                    self.error_total += 1
                    self._window_errors += 1
                    self._publish_decode_error(
                        "framing.word_start_stop_mismatch",
                        "word start/stop bits invalid",
                        details={
                            "word_bits": ''.join(str(int(b)) for b in self.bit_buffer),
                            "expected_start": int(self.start_bit),
                            "expected_stop": int(self.stop_bit),
                            "symbol_samples": [round(float(x), 4) for x in self.word_sample_buffer],
                        },
                    )
                    self._reset_word_collection()
                    self._publish_stats_if_due()
                    continue

                payload_bits = self._extract_word_payload_bits(self.bit_buffer)
                payload_samples = list(self.word_sample_buffer[1:9])
                if not self.word_lsb_first:
                    payload_samples = list(reversed(payload_samples))

                self.message_bits.extend(payload_bits)
                self.message_symbol_samples.extend(payload_samples)
                self.word_count += 1

                if self.word_count == self.FRAME_WORDS:
                    event = self._decode_message_bits(self.message_bits, self.message_symbol_samples)
                    self._publish_event(event)
                    self.frames_total += 1

                    if event.get("errors"):
                        self.error_total += len(event.get("errors"))
                        self._window_errors += len(event.get("errors"))

                    # Keep strict mode behavior for numeric output stream,
                    # but do not suppress visibility in event logs.
                    if not (self.strict_mode and event.get("status") == "error"):
                        self._samples_since_frame = 0
                        self._hunt_timeout_raised = False
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
