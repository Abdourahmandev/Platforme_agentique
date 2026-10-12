"""Give the LiteLLM router a stable task identity without persisting messages."""
import hashlib
import json
from litellm.integrations.custom_logger import CustomLogger

def contains_image(messages):
    return any(isinstance(message.get('content'), list) and any(
        isinstance(part, dict) and part.get('type') in ('image_url', 'image', 'input_image')
        for part in message['content']) for message in messages)

VISION_FALLBACKS = [
    {'asia-rapide': ['gemini-3.1-flash-lite']},
    {'gemini-3.1-flash-lite': ['gemini-3.8-flash']},
    {'gemini-3.8-flash': ['gemini-3.1-flash-lite']},
    {'gemini-3.1-pro-preview': ['gemini-3.8-flash']},
]

def requires_gemini(messages, response_format=None):
    if isinstance(response_format, dict) and response_format.get('type') == 'json_schema':
        return True
    for message in messages:
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get('type') in ('input_audio', 'video_url', 'file'):
                return True
            url = part.get('image_url', {})
            if isinstance(url, dict):
                url = url.get('url', '')
            if isinstance(url, str) and url.startswith(('data:audio/', 'data:video/', 'data:application/pdf')):
                return True
    return False

def task_identity(messages):
    # The prefix ending at the newest user message stays identical throughout
    # subsequent tool calls. A new user request starts a fresh routing decision.
    end = next((i + 1 for i in range(len(messages)-1, -1, -1)
                if messages[i].get('role') == 'user'), len(messages))
    encoded = json.dumps(messages[:end], sort_keys=True, ensure_ascii=False).encode()
    return 'asia-task-' + hashlib.sha256(encoded).hexdigest()

class RoutingContext(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get('messages') or []
        # Trusted virtual-key metadata, never a flag supplied in a prompt/request.
        # Training has confirmed DeepSeek credits only: no implicit paid fallback.
        key_metadata = getattr(user_api_key_dict, 'metadata', None) or {}
        if key_metadata.get('purpose') == 'training':
            if data.get('model') != 'asia-rapide' or contains_image(messages) or requires_gemini(messages, data.get('response_format')):
                raise ValueError('Training is restricted to the verified text route')
            data.update(fallbacks=[], context_window_fallbacks=[], content_policy_fallbacks=[],
                        max_fallbacks=0, num_retries=0, reasoning_effort='none', thinking={'type':'disabled'})
            return data
        auto = data.get('model') == 'asia-auto'
        if auto and messages:
            metadata = dict(data.get('metadata') or {})
            metadata['session_id'] = task_identity(data['messages'])
            data['metadata'] = metadata
        special = requires_gemini(messages, data.get('response_format'))
        if auto and special:
            # The complexity router's modality gate covers images only. Handle
            # PDF/audio/video and strict JSON here, using the economical Gemini.
            data['model'] = 'gemini-3.1-flash-lite'
        if messages and (contains_image(messages) or special):
            # Also protect explicit Gemini selections, not just the Auto alias.
            data['fallbacks'] = VISION_FALLBACKS
        return data

guard = RoutingContext()
