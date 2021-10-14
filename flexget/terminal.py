import contextlib
import threading
from textwrap import wrap
from typing import Iterator, List, Optional, TextIO

import rich
import rich.box
import rich.console
import rich.segment
import rich.table
import rich.text

from flexget.options import ArgumentParser

local_context = threading.local()
rich_console = rich.console.Console()

PORCELAIN_BOX: rich.box.Box = rich.box.Box(
    """\
    
  | 
    
  | 
    
    
  | 
    
""",
    ascii=True,
)

GITHUB_BOX: rich.box.Box = rich.box.Box(
    """\
    
| ||
|-||
| ||
|-||
|-||
| ||
    
""",
    ascii=True,
)


class TerminalTable:
    """
    A data table suited for CLI output, created via its sent parameters. For example::

        header = ['Col1', 'Col2']
        table_data = [header]
        for item in iterable:
            table_data.append([item.attribute1, item.attribute2])
        table = TerminalTable('plain', table_data)
        print table.output

    Optional values are setting table title, and supplying wrap_columns list and
    drop_column list. If table does not fit into terminal any columns listed in
    wrap_columns will be tried to wrap and if resulting columns are below MIN_WIDTH(10)
    columns listed in drop_column will be removed from output.

    Example::

        header = ['Col1', 'Col2']
        table_data = [header]
        for item in iterable:
            table_data.append([item.attribute1, item.attribute2])
        table = TerminalTable('plain', table_data, 'Table title', wrap_columns=[1,2],
                              drop_columns=[4,2])
        print table.output

    :param table_type: A string matching supported_table_types() keys.
    :param table_data: Table data as a list of lists of strings. See `terminaltables` doc.
    :param title: Optional title for table
    :param wrap_columns: A list of column numbers which will can be wrapped.
        In case of multiple values even split is used.
    :param drop_columns: A list of column numbers which can be dropped if needed.
        List in order of priority.
    """

    # TODO: Add other new types
    TABLE_TYPES = {
        'plain': {'box': rich.box.ASCII},
        'porcelain': {'box': PORCELAIN_BOX, 'show_edge': False},
        'single': {'box': rich.box.SQUARE},
        'double': {'box': rich.box.DOUBLE},
        'github': {'box': GITHUB_BOX},
    }

    def __init__(
        self,
        table_type: str,
        table_data: List[List[str]],
        title: Optional[str] = None,
        wrap_columns: Optional[List[int]] = None,
        drop_columns: Optional[List[int]] = None,
    ) -> None:
        self.title = title
        self.table_data = table_data
        self.type = table_type
        self._init_table()

    def _init_table(self) -> None:
        """Assigns self.table with the built table based on data."""
        self.table: rich.table.Table = rich.table.Table(
            title=self.title, **self.TABLE_TYPES[self.type]
        )
        for col in self.table_data[0]:
            self.table.add_column(col)
        for row in self.table_data[1:]:
            self.table.add_row(*row)

    def __rich_console__(self, console, options):
        segments = self.table.__rich_console__(console, options)
        if self.type not in ['porcelain', 'github']:
            yield from segments
            return
        # Strips out blank lines from our custom types
        lines = rich.segment.Segment.split_lines(segments)
        for line in lines:
            if any(seg.text.strip() for seg in line):
                yield from line
                yield rich.segment.Segment.line()


class TerminalTableError(Exception):
    """A CLI table error"""


table_parser = ArgumentParser(add_help=False)
table_parser.add_argument(
    '--table-type',
    choices=list(TerminalTable.TABLE_TYPES),
    default='single',
    help='Select output table style',
)
table_parser.add_argument(
    '--porcelain',
    dest='table_type',
    action='store_const',
    const='porcelain',
    help='Make the output parseable. Similar to using `--table-type porcelain`',
)


def word_wrap(text: str, max_length: int) -> str:
    """A helper method designed to return a wrapped string.

    :param text: Text to wrap
    :param max_length: Maximum allowed string length
    :return: Wrapped text or original text
    """
    if len(text) >= max_length:
        return '\n'.join(wrap(text, max_length))
    return text


def colorize(color: str, text: str) -> str:
    """
    A simple override of Color.colorize which sets the default auto colors value to True, since it's the more common
    use case. When output isn't TTY just return text

    :param color: Color tag to use
    :param text: Text to color
    :param auto: Whether to apply auto colors

    :return: Colored text or text
    """
    return f'[{color}]{text}[/]'


def disable_colors():
    rich_console.no_color = True


@contextlib.contextmanager
def capture_console(filelike: TextIO) -> Iterator:
    old_output = get_console_output()
    local_context.output = filelike
    try:
        yield
    finally:
        local_context.output = old_output


def get_console_output() -> Optional[TextIO]:
    return getattr(local_context, 'output', None)


def _patchable_console(text, *args, **kwargs):
    # Nobody will import this directly, so we can monkeypatch it for IPC calls
    rich_console.file = get_console_output()
    try:
        rich_console.print(text, *args, **kwargs)
    finally:
        rich_console.file = None


def console(text: str, *args, **kwargs) -> None:
    """
    Print to console safely. Output is able to be captured by different streams in different contexts.

    Any plugin wishing to output to the user's console should use this function instead of print so that
    output can be redirected when FlexGet is invoked from another process.

    Accepts arguments like the `rich.console.Console.print` function does.
    """
    _patchable_console(text, *args, **kwargs)
