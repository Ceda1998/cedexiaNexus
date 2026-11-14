import unittest

from nexus_ui.chat_output import code_blocks, split_reply


class ChatOutputTests(unittest.TestCase):
    def test_prefilled_thinking_stays_hidden_at_every_stream_boundary(self):
        prefix = '\n> Grüße planen</think>'
        stream = prefix + '\n\n**Hallo** [end of text]\n'
        for index in range(len(stream) + 1):
            reply = split_reply(stream[:index], prefilled=True, console_prompt=True)
            self.assertNotIn('planen', reply.answer)
            self.assertNotIn('</', reply.thinking)
            self.assertNotIn('[end', reply.answer)
            if index <= len(prefix):
                self.assertEqual(reply.answer, '')
        reply = split_reply(stream, prefilled=True, complete=True, console_prompt=True)
        self.assertEqual((reply.answer, reply.thinking), ('**Hallo**', 'Grüße planen'))

    def test_explicit_open_missing_close_no_reasoning_and_legacy(self):
        self.assertEqual(split_reply('<thi').answer, '')
        reply = split_reply('<think>Nur Analyse</thi', complete=True)
        self.assertEqual((reply.answer, reply.thinking, reply.thinking_open), ('', 'Nur Analyse', True))
        reply = split_reply('<|im_start|>assistant\n2 < 3<|im_end|>', complete=True)
        self.assertEqual((reply.answer, reply.thinking), ('2 < 3', ''))
        reply = split_reply('Alte Notiz</think>\nAntwort', complete=True, legacy=True)
        self.assertEqual((reply.answer, reply.thinking), ('Antwort', 'Alte Notiz'))

    def test_code_preserves_literal_tags_and_line_breaks(self):
        source = '<main>Restaurant</main>\n<script>console.log("<think>");</script>\n'
        answer = 'Literal `</think>` und HTML:\n\n```html\n' + source + '```'
        result = split_reply('<think>Plan</think>\n' + answer + ' [end of text]\n',
                             complete=True)
        self.assertEqual(result.answer, answer)
        self.assertEqual(result.thinking, 'Plan')
        self.assertEqual(list(code_blocks(result.answer)), [source])
