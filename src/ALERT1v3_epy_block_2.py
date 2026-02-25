import json
import time
from gnuradio import gr
import pmt


class mqtt_event_publisher(gr.basic_block):
    """
    Publish ALERT decode/status events to MQTT.

    Topic layout (prefix default: alert):
      <prefix>/rx/decoded
      <prefix>/rx/raw
      <prefix>/rx/status
      <prefix>/rx/metrics
    """

    def __init__(self, broker_host='127.0.0.1', broker_port=1883, username='', password='', topic_prefix='alert'):
        gr.basic_block.__init__(self, name='ALERT MQTT Publisher', in_sig=None, out_sig=None)
        self.message_port_register_in(pmt.intern('msg_in'))
        self.set_msg_handler(pmt.intern('msg_in'), self.handle_msg)

        self.broker_host = broker_host
        self.broker_port = int(broker_port)
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix.strip('/') or 'alert'

        self._client = None
        self._connected = False
        self._published = 0
        self._dropped = 0
        self._last_metrics = 0.0

        self._setup_client()

    def _setup_client(self):
        try:
            import paho.mqtt.client as mqtt
        except Exception as exc:
            self.logger.error(f'MQTT disabled (paho-mqtt unavailable): {exc}')
            return

        self._client = mqtt.Client(client_id='alert1v3-rx', clean_session=True)
        if self.username:
            self._client.username_pw_set(self.username, self.password)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect_async(self.broker_host, self.broker_port, keepalive=30)
            self._client.loop_start()
        except Exception as exc:
            self.logger.error(f'MQTT connect failed: {exc}')
            self._client = None

    def _on_connect(self, _client, _userdata, _flags, rc):
        self._connected = (rc == 0)
        if rc != 0:
            self.logger.error(f'MQTT connect returned rc={rc}')

    def _on_disconnect(self, _client, _userdata, _rc):
        self._connected = False

    def _publish_json(self, topic_suffix, payload):
        if not self._client or not self._connected:
            self._dropped += 1
            return

        topic = f'{self.topic_prefix}/{topic_suffix}'
        try:
            self._client.publish(topic, json.dumps(payload, default=str), qos=0, retain=False)
            self._published += 1
        except Exception as exc:
            self._dropped += 1
            self.logger.error(f'MQTT publish failed ({topic}): {exc}')

    def _publish_metrics(self, event):
        now = time.time()
        if now - self._last_metrics < 5.0:
            return
        self._last_metrics = now

        metrics = {
            'schema': 'alert.mqtt.metrics.v1',
            'ts': event.get('ts', ''),
            'status': 'ok' if self._connected else 'disconnected',
            'broker': f'{self.broker_host}:{self.broker_port}',
            'published': self._published,
            'dropped': self._dropped,
        }
        self._publish_json('rx/metrics', metrics)

    def handle_msg(self, msg):
        try:
            event = pmt.to_python(msg)
        except Exception:
            event = str(msg)

        if not isinstance(event, dict):
            event = {
                'schema': 'alert.decode.v1',
                'ts': '',
                'status': 'raw',
                'summary': str(event),
                'decode': {},
                'frame': {},
            }

        decode = event.get('decode', {}) if isinstance(event.get('decode'), dict) else {}
        frame = event.get('frame', {}) if isinstance(event.get('frame'), dict) else {}

        self._publish_json('rx/decoded', event)
        self._publish_json('rx/raw', {
            'schema': event.get('schema', 'alert.decode.v1'),
            'ts': event.get('ts', ''),
            'status': event.get('status', 'unknown'),
            'frame': frame,
        })
        self._publish_json('rx/status', {
            'schema': event.get('schema', 'alert.decode.v1'),
            'ts': event.get('ts', ''),
            'status': event.get('status', 'unknown'),
            'summary': event.get('summary', ''),
            'sensor_id': decode.get('sensor_id'),
            'format_id': decode.get('format_id'),
        })
        self._publish_metrics(event)

    def stop(self):
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        return True
