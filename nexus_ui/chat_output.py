"""Separate displayable assistant output from llama-completion framing."""
from dataclasses import dataclass
import re

OPEN, CLOSE = '<think>', '</think>'
END = '[end of text]'
MARKERS = (OPEN, CLOSE, '<|im_start|>assistant', '<|im_start|>', '<|im_end|>',
           '<|endoftext|>', '<|eot_id|>', '<|end_of_text|>')
MARKER = re.compile('|'.join(map(re.escape, MARKERS)))
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})([^\n]*)$')
INLINE = re.compile(r'(?<!`)(`+)(?!`)([^\n]*?)(?<!`)\1(?!`)')


@dataclass
class Reply:
    answer: str
    thinking: str
    thinking_open: bool


def fenced_lines(text):
    """Yield lines with their enclosing CommonMark fence, including incomplete blocks."""
    fence = ''
    for line in text.splitlines(keepends=True):
        match = FENCE.fullmatch(line.rstrip('\r\n'))
        if fence:
            if match and match[1].startswith(fence) and not match[2].strip():
                yield line, 'close'
                fence = ''
            else:
                yield line, 'code'
        elif match and (match[1][0] == '~' or '`' not in match[2]):
            fence = match[1]
            yield line, 'open'
        else:
            yield line, ''


def code_blocks(text):
    block = []
    for line, kind in fenced_lines(text):
        if kind == 'open':
            block = []
        elif kind == 'code':
            block.append(line)
        elif kind == 'close' and block:
            yield ''.join(block)
            block = []
    if block:
        yield ''.join(block)


def split_reply(text, *, prefilled=False, complete=False, legacy=False, console_prompt=False):
    # The console prints this prompt in interactive single-turn mode (Windows).
    if console_prompt or legacy:
        for prefix in ('\n> ', '\r\n> '):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
            if not complete and prefix.startswith(text):
                text = ''
                break
    end = re.search(r' \[end of text\][\r\n]*\Z', text)
    if end:
        text = text[:end.start()]

    answer = []
    thinking = []
    in_thinking = prefilled
    saw_tag = False

    def add(part):
        (thinking if in_thinking else answer).append(part)

    def parse(part, last=False):
        nonlocal in_thinking, saw_tag
        pos = 0
        for match in MARKER.finditer(part):
            add(part[pos:match.start()])
            marker = match[0]
            if marker == OPEN:
                in_thinking = True
                saw_tag = True
            elif marker == CLOSE:
                # Older saved Qwen replies may only carry the closing marker.
                if legacy and not saw_tag and not in_thinking:
                    thinking.extend(answer)
                    answer.clear()
                in_thinking = False
                saw_tag = True
            pos = match.end()
        tail = part[pos:]
        if last:
            # Hold back a partial delimiter across render ticks. At EOF discard
            # truncated protocol fragments while keeping ordinary punctuation.
            tags = (*MARKERS, ' ' + END)
            minimum = 2 if complete else 1
            for size in range(min(len(tail), max(map(len, tags)) - 1), minimum - 1, -1):
                if any(tag.startswith(tail[-size:]) for tag in tags):
                    tail = tail[:-size]
                    break
        add(tail)

    consumed = 0
    for line, fenced in fenced_lines(text):
        consumed += len(line)
        if fenced:
            add(line)
            continue
        pos = 0
        for literal in INLINE.finditer(line):
            parse(line[pos:literal.start()])
            add(literal[0])
            pos = literal.end()
        parse(line[pos:], last=consumed == len(text))
    return Reply(''.join(answer).lstrip('\r\n'), ''.join(thinking).strip(), in_thinking)
