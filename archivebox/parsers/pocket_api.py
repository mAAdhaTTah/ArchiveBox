__package__ = 'archivebox.parsers'


import re

from typing import IO, Iterable, Optional
from datetime import datetime
from configparser import ConfigParser

from pathlib import Path
from pocket import Pocket
import requests

from ..index.schema import Link
from ..util import (
    enforce_types,
)

_COUNT_PER_PAGE = 500
_SINCE_FILENAME = 'since.db'

def get_pocket_articles(api: Pocket, since=None, page=0):
    body, headers = api.get(
        state='archive',
        sort='oldest',
        since=since,
        count=_COUNT_PER_PAGE,
        offset=page * _COUNT_PER_PAGE,
    )

    
    articles = body['list'].values() if isinstance(body['list'], dict) else body['list']
    returned_count = len(articles)

    yield from articles

    if returned_count == _COUNT_PER_PAGE:
        yield from get_pocket_articles(api, since=since, page=page + 1)
    else:
        api.last_since = body['since']


def link_from_article(article: dict, sources: list):
    url: str = article['resolved_url'] or article['given_url']
    if url.startswith('http:/www'):
        url = url.replace('http:/', 'http://')
    title = article['resolved_title'] or article['given_title'] or url

    return Link(
        url=url,
        timestamp=article['time_read'],
        title=title,
        tags=article.get('tags'),
        sources=sources
    )

def write_since(username: str, since: str):
    from ..system import atomic_write
    from ..config import (
        OUTPUT_DIR
    )

    since_path = Path(OUTPUT_DIR) /  _SINCE_FILENAME
    
    if not since_path.exists():
        atomic_write(since_path, '')

    since_file = ConfigParser()
    since_file.optionxform = str
    since_file.read(since_path)

    since_file[username] = {
        'since': since
    }

    with open(since_path, 'w+') as new:
        since_file.write(new)

def read_since(username) -> Optional[str]:
    from ..system import atomic_write
    from ..config import (
        OUTPUT_DIR
    )

    since_path = Path(OUTPUT_DIR) /  _SINCE_FILENAME
    
    if not since_path.exists():
        atomic_write(since_path, '')

    config_file = ConfigParser()
    config_file.optionxform = str
    config_file.read(since_path)

    return config_file.get(username, 'since', fallback=None)

@enforce_types
def should_parse_as_pocket_api(text: str) -> bool:
    return text.startswith('pocket://')

@enforce_types
def parse_pocket_api_export(input_buffer: IO[str], **_kwargs) -> Iterable[Link]:
    """Parse bookmarks from the Pocket API"""

    input_buffer.seek(0)
    pattern = re.compile("^pocket:\/\/(\w+)")
    for line in input_buffer:
      if should_parse_as_pocket_api(line):
        from ..config import (
          POCKET_CONSUMER_KEY,
          POCKET_ACCESS_TOKENS,
        )
        username = pattern.search(line).group(1)
        api = Pocket(POCKET_CONSUMER_KEY, POCKET_ACCESS_TOKENS[username])
        api.last_since = None

        for article in get_pocket_articles(api, since=read_since(username)):
          yield link_from_article(article, sources=[line])

        write_since(username, api.last_since)
