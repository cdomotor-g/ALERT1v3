import json
from gnuradio import gr
import pmt
import datetime
import os
import csv


class blk(gr.basic_block):
    """
    ALERT decode logger.

    Accepts structured PMT messages on 'msg_in' and writes:
      - CSV summary rows
      - JSONL full events

    File layout:
      <base_path>/<YYYY-MM-DD>/
        rx_data_<HHMMSS>.csv
        rx_events_<HHMMSS>.jsonl
    """

    def __init__(self, base_path='/home/pi/rf_logs'):
        gr.basic_block.__init__(self, name='ALERT Event Logger', in_sig=None, out_sig=None)
        self.message_port_register_in(pmt.intern('msg_in'))
        self.set_msg_handler(pmt.intern('msg_in'), self.handle_msg)

        self.base_path = base_path
        self.current_date = ''
        self.csv_file = None
        self.jsonl_file = None
        self.csv_writer = None

    def _open_session_files(self):
        now = datetime.datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        session_str = now.strftime('%H%M%S')

        target_dir = os.path.join(self.base_path, date_str)
        os.makedirs(target_dir, exist_ok=True)

        csv_path = os.path.join(target_dir, f'rx_data_{session_str}.csv')
        jsonl_path = os.path.join(target_dir, f'rx_events_{session_str}.jsonl')

        self.csv_file = open(csv_path, 'a', newline='')
        self.jsonl_file = open(jsonl_path, 'a')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            'timestamp', 'status', 'sensor_id', 'format_id', 'is_binary', 'data_val', 'payload_hex', 'summary'
        ])
        self.current_date = date_str

    def _ensure_files(self):
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        if self.csv_file is None or self.jsonl_file is None or date_str != self.current_date:
            self._close_files()
            self._open_session_files()

    def _close_files(self):
        if self.csv_file:
            try:
                self.csv_file.flush()
                self.csv_file.close()
            except Exception:
                pass
        if self.jsonl_file:
            try:
                self.jsonl_file.flush()
                self.jsonl_file.close()
            except Exception:
                pass
        self.csv_file = None
        self.jsonl_file = None
        self.csv_writer = None

    def _normalize_event(self, msg):
        now_ts = datetime.datetime.utcnow().isoformat() + 'Z'
        try:
            event = pmt.to_python(msg)
        except Exception:
            event = str(msg)

        if not isinstance(event, dict):
            event = {
                'schema': 'alert.decode.v1',
                'ts': now_ts,
                'status': 'raw',
                'summary': str(event),
                'display': str(event),
                'decode': {},
                'frame': {},
            }

        event.setdefault('schema', 'alert.decode.v1')
        event.setdefault('ts', now_ts)
        event.setdefault('status', 'unknown')
        event.setdefault('decode', {})
        event.setdefault('frame', {})

        if not isinstance(event.get('decode'), dict):
            event['decode'] = {}
        if not isinstance(event.get('frame'), dict):
            event['frame'] = {}

        if 'summary' not in event:
            event['summary'] = str(event.get('display', ''))
        if 'display' not in event:
            event['display'] = str(event.get('summary', ''))

        return event

    def handle_msg(self, msg):
        try:
            self._ensure_files()
            event = self._normalize_event(msg)

            decode = event.get('decode', {})
            frame = event.get('frame', {})

            row = [
                event.get('ts', datetime.datetime.utcnow().isoformat() + 'Z'),
                event.get('status', 'unknown'),
                decode.get('sensor_id', ''),
                decode.get('format_id', ''),
                decode.get('is_binary', ''),
                decode.get('data_val', ''),
                frame.get('payload_hex', ''),
                event.get('summary', ''),
            ]

            self.csv_writer.writerow(row)
            self.csv_file.flush()

            self.jsonl_file.write(json.dumps(event, default=str) + '\n')
            self.jsonl_file.flush()

        except Exception as e:
            self.logger.error(f'Logging error: {e}')

    def stop(self):
        self._close_files()
        return True
