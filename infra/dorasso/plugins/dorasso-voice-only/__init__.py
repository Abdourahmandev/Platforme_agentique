"""Mark inbound voice notes so Dorasso can answer with a voice bubble only.

Hermes hands a transcribed voice note to the agent as plain quoted text, and its
auto voice reply always sends the text as well. This hook tags voice notes
before dispatch; SOUL.md then has the agent call text_to_speech and return only
the tool's [[audio_as_voice]] / MEDIA: lines, which the gateway delivers as a
voice bubble with no text message. Text messages are left untouched.
"""

MARKER = '[NOTE_VOCALE]'
NOTE = (MARKER + " Le proprietaire a envoye une note vocale : reponds uniquement "
        "par une note vocale, selon tes regles.")


def _is_voice(event):
    kind = getattr(event, 'message_type', None)
    return str(getattr(kind, 'value', kind) or '').lower() == 'voice'


def tag_voice_notes(event=None, **kwargs):
    if event is None or getattr(event, 'internal', False) or not _is_voice(event):
        return None
    text = getattr(event, 'text', None) or ''
    if MARKER in text:
        return None
    return {'action': 'rewrite', 'text': f'{NOTE}\n\n{text}'.rstrip()}


def register(ctx):
    ctx.register_hook('pre_gateway_dispatch', tag_voice_notes)
