#!/usr/bin/env python3
import argparse
import json
import tempfile
import time
from pathlib import Path

from gnuradio import blocks, gr

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import ALERT1v3_epy_block_0 as logger_block
import ALERT1v3_epy_block_1 as decoder_block
import ALERT1v3_epy_block_2 as mqtt_block


def payload_bits_from_fields(sensor_id: int, format_id: int, data_val: int):
    msg = 0
    msg |= (sensor_id & 0x3F) << 0
    msg |= ((sensor_id >> 6) & 0x3F) << 8
    msg |= ((sensor_id >> 12) & 0x01) << 16
    msg |= (format_id & 0x03) << 6
    msg |= (data_val & 0x1F) << 17
    msg |= ((data_val >> 5) & 0x3F) << 24
    return [int(b) for b in f"{msg:032b}"]


def encode_frame_samples(sensor_id: int, format_id: int, data_val: int):
    bits = payload_bits_from_fields(sensor_id, format_id, data_val)
    out = []
    for i in range(0, 32, 8):
        out.append(1.0)                  # start bit
        out.extend(float(x) for x in bits[i:i+8])
        out.append(0.0)                  # spare/end bit
    return out


class ReplayTB(gr.top_block):
    def __init__(self, samples, log_base, mqtt_host, mqtt_port, mqtt_user, mqtt_pass, mqtt_prefix):
        super().__init__("alert1v3_replay")
        self.src = blocks.vector_source_f(samples, False)
        self.decoder = decoder_block.alert_protocol_decoder()
        self.sink = blocks.null_sink(gr.sizeof_float)
        self.logger = logger_block.blk(base_path=log_base)
        self.mqtt = mqtt_block.mqtt_event_publisher(
            broker_host=mqtt_host,
            broker_port=mqtt_port,
            username=mqtt_user,
            password=mqtt_pass,
            topic_prefix=mqtt_prefix,
        )

        self.connect(self.src, self.decoder)
        self.connect(self.decoder, self.sink)
        self.msg_connect((self.decoder, 'debug_out'), (self.logger, 'msg_in'))
        self.msg_connect((self.decoder, 'debug_out'), (self.mqtt, 'msg_in'))


def newest_jsonl(log_root: Path):
    files = sorted(log_root.rglob('rx_events_*.jsonl'))
    return files[-1] if files else None


def main():
    ap = argparse.ArgumentParser(description='Replay synthetic ALERT frames through decoder/logger/mqtt')
    ap.add_argument('--frames', type=int, default=20)
    ap.add_argument('--sensor-start', type=int, default=100)
    ap.add_argument('--data-start', type=int, default=1000)
    ap.add_argument('--log-base', default='')
    ap.add_argument('--mqtt-host', default='127.0.0.1')
    ap.add_argument('--mqtt-port', type=int, default=1883)
    ap.add_argument('--mqtt-user', default='')
    ap.add_argument('--mqtt-pass', default='')
    ap.add_argument('--mqtt-prefix', default='alert')
    ap.add_argument('--settle-ms', type=int, default=800)
    args = ap.parse_args()

    log_base = args.log_base or tempfile.mkdtemp(prefix='alert1v3-replay-')
    Path(log_base).mkdir(parents=True, exist_ok=True)

    samples = []
    for i in range(args.frames):
        samples.extend(encode_frame_samples(args.sensor_start + i, 1, args.data_start + i))
        samples.extend([0.0] * 40)

    tb = ReplayTB(samples, log_base, args.mqtt_host, args.mqtt_port, args.mqtt_user, args.mqtt_pass, args.mqtt_prefix)
    tb.start()
    time.sleep(max(args.settle_ms, 200) / 1000.0)
    tb.stop()
    tb.wait()

    jsonl = newest_jsonl(Path(log_base))
    event_count = 0
    if jsonl and jsonl.exists():
        with jsonl.open('r', encoding='utf-8', errors='replace') as f:
            event_count = sum(1 for _ in f)

    print(json.dumps({
        'log_base': log_base,
        'jsonl': str(jsonl) if jsonl else '',
        'frames_requested': args.frames,
        'events_logged': event_count,
        'mqtt': f'{args.mqtt_host}:{args.mqtt_port}',
        'mqtt_prefix': args.mqtt_prefix,
    }))


if __name__ == '__main__':
    main()
