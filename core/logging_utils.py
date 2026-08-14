"""Formatter de log estruturado em JSON (Sprint 19, RNF-07)."""

import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)

        # campos extras passados via logger.info(..., extra={'instance_id': 1, ...})
        campos_padrao = set(logging.LogRecord('', 0, '', 0, '', (), None).__dict__) | {'message', 'asctime'}
        for chave, valor in record.__dict__.items():
            if chave not in campos_padrao:
                payload[chave] = valor

        return json.dumps(payload, ensure_ascii=False, default=str)
