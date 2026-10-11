"""Local accounting only: never store prompts, responses or credentials."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from litellm.integrations.custom_logger import CustomLogger

class LocalMetrics(CustomLogger):
    def __init__(self):
        self.lock = threading.Lock()

    def record(self, kwargs, response, start_time, end_time, status):
        usage = getattr(response, 'usage', None)
        params = kwargs.get('litellm_params') or {}
        metadata = params.get('metadata') or {}
        decision = metadata.get('routing_decision') or {}
        if not isinstance(decision, dict):
            decision = {}
        cost = kwargs.get('response_cost')
        event = {
            'time': datetime.now(timezone.utc).isoformat(),
            'request_id': kwargs.get('litellm_call_id'),
            'profile': metadata.get('model_group'),
            'model': kwargs.get('model'),
            'routed_model': decision.get('routed_model'),
            'tier': decision.get('tier'),
            'routing_cause': decision.get('cause'),
            'status': status,
            'latency_ms': round((end_time - start_time).total_seconds() * 1000),
            'input_tokens': getattr(usage, 'prompt_tokens', None),
            'output_tokens': getattr(usage, 'completion_tokens', None),
            'cost_usd': cost if isinstance(cost, (int, float)) else None,
            'error_type': type(kwargs['exception']).__name__ if kwargs.get('exception') else None,
        }
        default = Path(os.environ.get('LOCALAPPDATA', '/var/lib')) / 'AsiaLiteLLM' / 'usage.jsonl'
        target = Path(os.environ.get('ASIA_USAGE_PATH', str(default)))
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if target.exists() and target.stat().st_size > 10_000_000:
                target.replace(target.with_name('usage.previous.jsonl'))
            with target.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + '\n')

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.record(kwargs, response_obj, start_time, end_time, 'success')

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.record(kwargs, response_obj, start_time, end_time, 'error')

logger = LocalMetrics()
