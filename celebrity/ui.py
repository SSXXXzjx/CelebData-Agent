# -*- coding: utf-8 -*-
"""Rich console helpers used across the CLI."""
import re
import shutil
import sys
import threading
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

console = Console(legacy_windows=False, force_interactive=None)

SPINNER_FRAMES = ('✱', '✦', '✧', '✦')


def format_elapsed(seconds):
    """Claude Code style duration: 18s / 2m 13s / 1h 04m."""
    seconds = int(seconds or 0)
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m {seconds % 60:02d}s'
    return f'{seconds // 3600}h {(seconds % 3600) // 60:02d}m'


def format_tokens(n):
    n = int(n or 0)
    return f'{n / 1000:.1f}k' if n >= 1000 else str(n)


def make_status_line(cfg, agent, start, label='Working'):
    """Working-status line: ✱ Working… (18s · ↓ 1.2k tokens)."""
    elapsed = time.monotonic() - start
    frame = SPINNER_FRAMES[int(time.monotonic() * 10) % len(SPINNER_FRAMES)]
    suffix = f'({format_elapsed(elapsed)}'
    if agent is not None and agent.usage and agent.usage.get('total_tokens'):
        suffix += f' · ↓ {format_tokens(agent.usage["total_tokens"])} tokens'
    suffix += ')'
    return f'{frame} {label}… {suffix}'


def plain_markdown(text):
    """Strip Markdown markers for clean streaming output (no raw **)."""
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'`', '', text)
    text = re.sub(r'(?m)^#+\s*', '', text)
    return text


def print_done(elapsed):
    from rich.text import Text

    console.print(Text(f'✓ Done in {format_elapsed(elapsed)}', style='bold green'))


class StreamUI:
    """Claude Code style streaming renderer.

    The animated status line updates in place with \\r (no cursor-up, so it
    works in every terminal and never stacks). Text streams directly to
    stdout with Markdown markers stripped. Tool execution prints its own
    progress output live; completion prints as a ◆ line.
    """

    def __init__(self, cfg, agent, start, tip=None):
        self.cfg = cfg
        self.agent = agent
        self.start = start
        self.tip = tip
        self.buf = []
        self._stop = threading.Event()
        self._thread = None
        self._streamed = False
        self._label = 'Working'

    def on_stream_start(self):
        self.buf = []
        self._streamed = False
        self._label = 'Working'
        self._stop.clear()
        if sys.stdout.isatty():
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()

    def _animate(self):
        while not self._stop.is_set():
            sys.stdout.write('\r\x1b[2K' + make_status_line(
                self.cfg, self.agent, self.start, label=self._label))
            sys.stdout.flush()
            time.sleep(0.1)

    def _clear_status(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
        if sys.stdout.isatty():
            sys.stdout.write('\r\x1b[2K')
            sys.stdout.flush()

    def stop(self):
        """Cancel animation and clean the status line (error path)."""
        self._clear_status()

    def on_delta(self, delta):
        if not self._streamed:
            self._clear_status()
            if self.tip:
                print(self.tip)
            self._streamed = True
        self.buf.append(delta)
        sys.stdout.write(plain_markdown(delta))
        sys.stdout.flush()

    def on_stream_end(self, content):
        if not self._streamed:
            self._clear_status()
            if self.tip:
                print(self.tip)

    def on_tool(self, name, ok, summary):
        self._clear_status()
        line = f'◆ {name}'
        if summary:
            line += f' — {summary}'
        console.print(line, style='bold green' if ok else 'bold red')

    def on_tool_start(self, name):
        # Tools render their own progress output live; just clear any leftover
        # streaming status so the layout stays clean.
        self._clear_status()


def print_step(current, total, title, detail=''):
    text = f'[bold cyan]步骤 {current}/{total}[/bold cyan]  [bold]{title}[/bold]'
    if detail:
        text += f'\n[dim]{detail}[/dim]'
    console.print(Panel(text, border_style='cyan', expand=False))


def info(msg):
    console.print(f'[cyan]*[/cyan] {msg}')


def success(msg):
    console.print(f'[green]+[/green] {msg}')


def warn(msg):
    console.print(f'[yellow]![/yellow] {msg}')


def error(msg):
    console.print(f'[red]x[/red] {msg}')


def panel(title, text):
    console.print(Panel(str(text), title=title, border_style='green', expand=False))


def print_agent(content):
    """Render an agent reply as Markdown so ** / lists / code render cleanly."""
    from rich.markdown import Markdown

    console.print('[bold cyan]Agent:[/bold cyan]')
    console.print(Markdown(content or ''))


def table(title, rows, headers=()):
    t = Table(title=title, show_header=bool(headers), border_style='blue')
    if headers:
        for h in headers:
            t.add_column(h, style='bold cyan')
    for row in rows:
        t.add_row(*[str(c) for c in row])
    console.print(t)


def ask_text(prompt, default=None, password=False, overlay=False):
    """Text input. `overlay=True` renders full-screen and covers the terminal."""
    if overlay and sys.stdin.isatty():
        return fullscreen_input(prompt, default=default or '', password=password)
    if password:
        if sys.stdin.isatty():
            return Prompt.ask(prompt, default=default, password=True)
        # Non-TTY fallback (pipes/tests): Rich's password prompt needs a TTY.
        value = input(prompt + '> ')
        value = value.strip()
        return value if value else (default if default is not None else '')
    return Prompt.ask(prompt, default=default)


def ask_int(prompt, default=None):
    return IntPrompt.ask(prompt, default=default)


def ask_confirm(prompt, default=True):
    return Confirm.ask(prompt, default=default)


def ask_choice(prompt, choices, default=1, overlay=False):
    """Arrow-key single-select. `overlay=True` covers the terminal full-screen."""
    if sys.stdin.isatty():
        try:
            return arrow_choice(prompt, choices, default, overlay=overlay)
        except Exception:
            pass
    table = Table(show_header=False, border_style='blue', box=None)
    for idx, choice in enumerate(choices, 1):
        table.add_row(f'[bold]{idx}[/bold]', choice)
    console.print(table)
    value = Prompt.ask(prompt, default=str(default or 1))
    try:
        idx = int(value)
        if 1 <= idx <= len(choices):
            return idx, choices[idx - 1]
    except ValueError:
        pass
    lowered = value.strip().lower()
    for choice in choices:
        if choice.lower() == lowered:
            return choices.index(choice) + 1, choice
    console.print('[red]无效选择，使用第 1 项[/red]')
    return 1, choices[0]


def arrow_choice(question, choices, default=1, overlay=False):
    """prompt_toolkit 方向键单选列表（↑/↓ 选择，Enter 确认，Ctrl+C 取消）。"""
    from prompt_toolkit.application import Application
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    state = {'idx': max(0, min(default - 1, len(choices) - 1))}
    kb = KeyBindings()

    @kb.add('up')
    def _up(event):
        state['idx'] = (state['idx'] - 1) % len(choices)

    @kb.add('down')
    def _down(event):
        state['idx'] = (state['idx'] + 1) % len(choices)

    @kb.add('enter')
    def _enter(event):
        event.app.exit(result=state['idx'])

    @kb.add('c-c')
    def _cc(event):
        event.app.exit(exception=KeyboardInterrupt)

    @kb.add('escape')
    def _esc(event):
        event.app.exit(exception=KeyboardInterrupt)

    def _body():
        lines = [('', f'  {question}  \n')]
        for i, choice in enumerate(choices):
            marker = '●' if i == state['idx'] else '○'
            cls = 'class:selected' if i == state['idx'] else 'class:normal'
            lines.append((cls, f'   {marker}  {choice}\n'))
        lines.append(('class:hint', '   ↑/↓ 选择   Enter 确认   Ctrl+C 取消\n'))
        return FormattedText(lines)

    layout = Layout(Window(FormattedTextControl(_body), wrap_lines=True))
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=overlay,
        mouse_support=False,
        style=Style.from_dict({
            'selected': 'fg:#00e5ff bold bg:#22335c',
            'normal': 'fg:#9fd8ff',
            'hint': 'fg:#5f7396',
        }),
    )
    idx = app.run()
    return idx + 1, choices[idx]


def fullscreen_input(prompt_text, default='', password=False):
    """Full-screen single-line input (overlay). ESC/Ctrl+C -> KeyboardInterrupt."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.processors import PasswordProcessor
    from prompt_toolkit.styles import Style

    buffer = Buffer(document=Document(default))
    kb = KeyBindings()

    @kb.add('enter')
    def _enter(event):
        event.app.exit(result=buffer.text)

    @kb.add('escape')
    def _esc(event):
        event.app.exit(exception=KeyboardInterrupt)

    @kb.add('c-c')
    def _cc(event):
        event.app.exit(exception=KeyboardInterrupt)

    processors = [PasswordProcessor()] if password else []
    body = HSplit([
        Window(height=6),
        Window(FormattedTextControl(
            FormattedText([('class:question', prompt_text)])), height=1),
        HSplit([
            Window(FormattedTextControl(
                FormattedText([('class:prompt', '> ')])), width=2),
            Window(BufferControl(
                buffer=buffer,
                focusable=True,
                input_processors=processors,
                include_default_input_processors=not password,
            ), height=1),
        ]),
    ])
    app = Application(
        layout=Layout(body),
        key_bindings=kb,
        full_screen=True,
        style=Style.from_dict({
            'question': 'bold cyan',
            'prompt': 'fg:#00e5ff bold',
        }),
    )
    return app.run()


class SlashCompleter:
    """Autocomplete for '/'-prefixed commands.

    Typing /m matches 'model' (and aliases like 'm'); the inserted text is
    always the canonical command name.
    """

    def __init__(self, commands=None):
        self.commands = commands or {}

    def get_completions(self, document, complete_event=None):
        from prompt_toolkit.completion import Completion
        from prompt_toolkit.formatted_text import FormattedText

        text = document.text
        if not text.startswith('/') or ' ' in text:
            return
        word = text[1:].lower()
        for name, aliases in self.commands.items():
            if not (name.startswith(word) or (word and word in name)
                    or any(a.startswith(word) or (word and word in a) for a in aliases)):
                continue
            display = FormattedText([('class:completion-name', '/' + name)])
            meta = None
            if aliases:
                meta = FormattedText([
                    ('class:completion-meta', '  ' + ' '.join('/' + a for a in aliases)),
                ])
            yield Completion(
                name,
                start_position=-len(word),
                display=display,
                display_meta=meta,
            )


def _chat_key_bindings():
    """Standalone ESC raises KeyboardInterrupt so callers can pop a level."""
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    @kb.add('escape')
    def _escape(event):
        raise KeyboardInterrupt

    return kb


def chat_input(commands=None, prompt_text='> ', progress='', status='', hints='', history=None):
    """Single-line input framed by two clean border lines.

    Typing "/" opens an autocomplete dropdown of commands (↑/↓ to move,
    Enter to accept). `progress` renders above the frame, `status` below it.
    ESC / Ctrl+C raise KeyboardInterrupt (caller pops to the previous level).
    Falls back to plain input() on non-TTY streams.
    """
    width = min(shutil.get_terminal_size((80, 24)).columns, 100)
    border = '─' * max(width, 20)

    if not sys.stdin.isatty():
        if progress:
            print(progress)
        print(border)
        line = sys.stdin.readline()
        print()
        print(border)
        if status:
            print(status)
        if hints:
            print(hints)
        return line.strip() if line else ''

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.shortcuts import CompleteStyle
    from prompt_toolkit.styles import Style

    commands = commands or {}
    _style = Style.from_dict({
        'border': 'fg:#3a7bff',
        'prompt': 'fg:#00e5ff bold',
        'progress': 'fg:#5f7396',
        'status': 'fg:#5f7396',
        'hints': 'fg:#7a8699',
        'completion-menu': 'bg:#0a0f1e border:#3a7bff',
        'completion-menu.completion': 'fg:#9fd8ff bg:#0a0f1e',
        'completion-menu.completion.current': 'bg:#22335c fg:#ffffff bold',
        'completion-menu.meta': 'fg:#9aa8c8 bg:#0a0f1e',
        'completion-menu.meta.completion.current': 'fg:#ffb3f0 bg:#22335c',
        'bottom-toolbar': 'fg:#5f7396 bg:default noreverse',
    })

    message_parts = []
    if progress:
        message_parts.append(('class:progress', progress + '\n'))
    message_parts.append(('class:border', border + '\n\n'))
    message_parts.append(('class:prompt', prompt_text))

    toolbar_parts = [('', '\n'), ('class:border', border)]
    if status:
        toolbar_parts.extend([('', '\n'), ('class:status', status)])
    if hints:
        toolbar_parts.extend([('', '\n'), ('class:hints', hints)])

    return pt_prompt(
        FormattedText(message_parts),
        completer=SlashCompleter(commands),
        complete_while_typing=True,
        complete_style=CompleteStyle.READLINE_LIKE,
        style=_style,
        key_bindings=_chat_key_bindings(),
        history=history,
        bottom_toolbar=FormattedText(toolbar_parts) if toolbar_parts else None,
    )


def make_progress():
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
    return Progress(
        SpinnerColumn(),
        TextColumn('[bold cyan]{task.description}[/bold cyan]'),
        BarColumn(bar_width=40),
        TextColumn('{task.completed}/{task.total}'),
        TextColumn('[dim]{task.percentage:>3.0f}%[/dim]'),
        TimeRemainingColumn(),
        console=console,
    )


def make_download_progress():
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
    return Progress(
        SpinnerColumn(),
        TextColumn('[bold cyan]{task.description}[/bold cyan]'),
        BarColumn(bar_width=40),
        TextColumn('[dim]{task.percentage:>3.0f}%[/dim]'),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def notify_complete(title, lines):
    body = '\n'.join(f'[green]{line}[/green]' for line in lines)
    console.print(Panel(body, title=f'[bold]{title}[/bold]', border_style='green', expand=False))
    try:
        sys.stdout.write('\a')
        sys.stdout.flush()
    except Exception:
        pass
