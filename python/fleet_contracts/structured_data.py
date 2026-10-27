"""Structured Data Contract: JSON-LD that is complete and agrees with the page.

JSON-LD is the one part of a page no reader sees and no reviewer looks at, so
it drifts from the page beside it without anything failing. A search engine
then shows the drift: a "modified" date the page never states, a headline the
page does not carry, an author nobody can click through to, a figure in the
rich result that appears nowhere in the article. Every one of those is a 200
with valid JSON, which is why "the block parses" was never the test.

`check(html)` reads a rendered page and returns a list of problems, one plain
sentence each, empty when the page keeps the contract:

- **Complete.** Each node carries the fields its type needs (`REQUIRED`), and
  no field is present but empty — an empty string is a claim the page makes
  and does not fill.
- **Agrees with the page.** The main node's headline or name is the page's
  `<h1>`; its `url` / `mainEntityOfPage` is the canonical link; every date is
  a `<time datetime>` the reader can see; the image is the `og:image` or an
  `<img>` on the page; every breadcrumb but the last is linked from the page
  and the last is the page itself; every `ItemList` entry is linked from it.
- **Authorship is labelled honestly.** A `Person` author is named in the
  visible text and linked from the page at their `url`; an `Organization`
  author is named in the visible text. `personas=` takes the names of
  invented authors, and none of them may appear as a `Person` anywhere — a
  persona credited as a person is a false statement about who wrote it.
- **No invented numbers.** Every number in a text field, and every numeric
  value, appears in the page's visible text. Dates, URLs and list positions
  are structure, not claims, and are exempt.

`dateModified` has a consumer-specific half the helper cannot know: on the
blogs it must equal `articles.last_revised_at`, which moves only for a
substantive revision. The helper proves the date is one the page shows; the
consumer's own test proves it is the right one, using `nodes()` to read it.

Standard library only (`html.parser`, `json`), so a consumer needs nothing in
its lockfile to run it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

# Fields a node of each type must carry, non-empty. Deliberately the fields
# Google's structured-data documentation marks required, plus the ones the
# fleet always states and would be wrong without (an Article's publisher).
# A type not listed is not checked for completeness, only for agreement.
_ARTICLE = ('headline', 'datePublished', 'author', 'publisher')
REQUIRED: dict[str, tuple[str, ...]] = {
    'Article': _ARTICLE,
    'NewsArticle': _ARTICLE,
    'BlogPosting': _ARTICLE,
    'BreadcrumbList': ('itemListElement',),
    'ItemList': ('itemListElement',),
    'ListItem': ('position',),
    'CollectionPage': ('name', 'url'),
    'WebPage': (),
    'WebSite': ('name', 'url'),
    'Organization': ('name',),
    'Person': ('name',),
    'ImageObject': ('url',),
    # Google refuses a Dataset whose description is under 50 characters; the
    # length rule is in _check_node.
    'Dataset': ('name', 'description'),
    'SoftwareApplication': ('name', 'applicationCategory'),
    'WebApplication': ('name', 'applicationCategory'),
}

# Top-level types that describe the page itself, and the field that must be
# the page's <h1>. A WebSite or Organization block describes the publisher, not
# the page, so it is not compared with the heading.
_PAGE_TITLE = {
    'Article': 'headline', 'NewsArticle': 'headline', 'BlogPosting': 'headline',
    'CollectionPage': 'name', 'Dataset': 'name',
    'SoftwareApplication': 'name', 'WebApplication': 'name',
}
_ARTICLE_TYPES = {'Article', 'NewsArticle', 'BlogPosting'}

# Keys whose values are structure, never a claim a reader could check: their
# digits are not numbers the page has to show.
_STRUCTURAL_KEYS = {'position', 'query-input', 'urlTemplate', 'inLanguage',
                    'encodingFormat', 'width', 'height'}
_NUMBER = re.compile(r'(?<![\w.])\d+(?:[.,]\d+)*')
_SKIP_TEXT = {'script', 'style', 'head', 'title', 'template'}


class _Page(HTMLParser):
    """Everything on a rendered page the contract compares JSON-LD against."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raw_jsonld: list[str] = []
        self.h1: list[str] = []
        self.canonical = ''
        self.og_image = ''
        self.times: set[str] = set()
        self.images: set[str] = set()
        self.links: list[tuple[str, str]] = []      # (href, link text)
        self.text: list[str] = []
        self._skip = 0
        self._jsonld: list[str] | None = None
        self._h1: list[str] | None = None
        self._a: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or '') for k, v in attrs}
        if tag == 'script' and a.get('type', '').lower() == 'application/ld+json':
            self._jsonld = []
        if tag in _SKIP_TEXT:
            self._skip += 1
        if tag == 'link' and 'canonical' in a.get('rel', '').lower().split():
            self.canonical = a.get('href', '')
        elif tag == 'meta' and a.get('property') == 'og:image':
            self.og_image = a.get('content', '')
        elif tag == 'time' and a.get('datetime'):
            self.times.add(a['datetime'])
        elif tag in ('img', 'source'):
            for key in ('src', 'srcset'):
                for part in a.get(key, '').split(','):
                    if part.strip():
                        self.images.add(part.strip().split()[0])
        elif tag == 'h1':
            self._h1 = []
        elif tag == 'a' and 'href' in a:
            self._a.append((a['href'], []))

    def handle_startendtag(self, tag, attrs):
        # <link/> and <img/> carry no text and no end tag to pair with.
        self.handle_starttag(tag, attrs)
        if tag in _SKIP_TEXT:
            self._skip -= 1

    def handle_endtag(self, tag):
        if tag == 'script' and self._jsonld is not None:
            self.raw_jsonld.append(''.join(self._jsonld))
            self._jsonld = None
        if tag in _SKIP_TEXT and self._skip:
            self._skip -= 1
        elif tag == 'h1' and self._h1 is not None:
            self.h1.append(_norm(''.join(self._h1)))
            self._h1 = None
        elif tag == 'a' and self._a:
            href, parts = self._a.pop()
            self.links.append((href, _norm(''.join(parts))))

    def handle_data(self, data):
        if self._jsonld is not None:
            self._jsonld.append(data)
        if self._skip:
            return
        self.text.append(data)
        if self._h1 is not None:
            self._h1.append(data)
        for _href, parts in self._a:
            parts.append(data)


def _norm(text: str) -> str:
    return ' '.join(str(text).split())


def _url(href: str, base: str) -> str:
    """An href as the absolute URL it resolves to, minus query and fragment.

    Internal links carry `utm_medium=internal` and a breadcrumb never does; the
    query string is how a link was reached, not where it goes.
    """
    parts = urlsplit(urljoin(base, href))
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or '/', '', ''))


def _numbers(text: str) -> set[str]:
    return {m.replace(',', '') for m in _NUMBER.findall(text)}


def _types(node: dict) -> set[str]:
    t = node.get('@type')
    return set(t) if isinstance(t, list) else {t} if isinstance(t, str) else set()


def _walk(value, path: str):
    """Every node (a dict with an @type) inside a JSON-LD value, with its path."""
    if isinstance(value, dict):
        if '@type' in value:
            yield path, value
        for key, child in value.items():
            yield from _walk(child, f'{path}.{key}')
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _walk(child, f'{path}[{i}]')


def _top_level(data) -> list[dict]:
    items = data if isinstance(data, list) else [data]
    out = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get('@graph'), list):
            out.extend(n for n in item['@graph'] if isinstance(n, dict))
        elif isinstance(item, dict):
            out.append(item)
    return out


def _when(value: str):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _same_moment(a: str, b: str) -> bool:
    if a == b:
        return True
    da, db = _when(a), _when(b)
    if da is None or db is None:
        return False
    if (da.tzinfo is None) != (db.tzinfo is None):
        # A naive timestamp and an aware one name the same instant only if the
        # site stores UTC, which the fleet does; compare the wall clock.
        da, db = da.replace(tzinfo=None), db.replace(tzinfo=None)
    return da == db


def _label(path: str, node: dict) -> str:
    return f"{path} ({'/'.join(sorted(_types(node))) or 'untyped'})"


def nodes(html: str) -> list[dict]:
    """The page's top-level JSON-LD nodes, `@graph` flattened, for a consumer's
    own assertions. Unparseable blocks are skipped here; `check()` reports them."""
    page = _Page()
    page.feed(html)
    out = []
    for raw in page.raw_jsonld:
        try:
            out.extend(_top_level(json.loads(raw)))
        except ValueError:
            continue
    return out


def check(html: str, *, require=(), author: str | None = None,
          personas=()) -> list[str]:
    """Problems with the page's JSON-LD, one sentence each; [] when it keeps
    the contract.

    require  -- @types that must be present somewhere (e.g. {'Article',
                'BreadcrumbList'}). A page that should carry structured data
                and carries none passes every other rule vacuously.
    author   -- 'Person' or 'Organization': what an Article's author must be.
    personas -- names of invented authors; none may appear as a Person.
    """
    page = _Page()
    page.feed(html)
    page.close()
    problems: list[str] = []
    base = page.canonical or 'https://invalid.example/'
    canonical = _url(page.canonical, base) if page.canonical else ''
    visible = _norm(' '.join(page.text))
    visible_numbers = _numbers(visible)
    linked = {_url(href, base): text for href, text in page.links}
    images = {_url(src, base) for src in page.images}
    if page.og_image:
        images.add(_url(page.og_image, base))
    personas = {_norm(p) for p in personas}

    if not page.raw_jsonld:
        if require:
            problems.append('the page carries no JSON-LD block')
        return problems

    found: set[str] = set()
    for b, raw in enumerate(page.raw_jsonld):
        try:
            data = json.loads(raw)
        except ValueError as exc:
            problems.append(f'JSON-LD block {b} does not parse: {exc}')
            continue
        for top in _top_level(data):
            ctx = top.get('@context') or (data.get('@context')
                                          if isinstance(data, dict) else None)
            if str(ctx).rstrip('/') not in ('https://schema.org', 'http://schema.org'):
                problems.append(f'block {b}: @context is {ctx!r}, not https://schema.org')
            for path, node in _walk(top, f'block{b}'):
                found |= _types(node)
                _check_node(path, node, problems, visible, visible_numbers,
                            linked, images, page, canonical, personas)
            _check_page_node(f'block{b}', top, problems, page, canonical,
                             visible, linked, author)

    for missing in sorted(set(require) - found):
        problems.append(f'no {missing} node, and this page type requires one')
    return problems


def _check_node(path, node, problems, visible, visible_numbers, linked,
                images, page, canonical, personas):
    label = _label(path, node)
    types = _types(node)
    for t in types:
        for field in REQUIRED.get(t, ()):
            if field not in node or node[field] in ('', None, [], {}):
                problems.append(f'{label}: missing required field {field!r}')
    for key, value in node.items():
        if value == '' or value == []:
            problems.append(f'{label}: {key!r} is present but empty')

    if 'Dataset' in types and isinstance(node.get('description'), str):
        if not 50 <= len(node['description']) <= 5000:
            problems.append(f'{label}: a Dataset description must be 50–5000 '
                            f'characters, this one is {len(node["description"])}')

    for key in ('datePublished', 'dateModified', 'dateCreated'):
        if key in node and node[key]:
            value = str(node[key])
            if _when(value) is None:
                problems.append(f'{label}: {key} {value!r} is not an ISO 8601 date')
            elif not any(_same_moment(value, t) for t in page.times):
                problems.append(f'{label}: {key} {value!r} is not a <time datetime> '
                                f'the page shows')
    if node.get('datePublished') and node.get('dateModified'):
        pub, mod = _when(node['datePublished']), _when(node['dateModified'])
        if pub and mod and _comparable(pub, mod) and mod < pub:
            problems.append(f'{label}: dateModified is earlier than datePublished')

    if 'Person' in types and _norm(node.get('name', '')) in personas:
        problems.append(f'{label}: {node["name"]!r} is a persona, labelled as a Person')

    if types & _ARTICLE_TYPES:
        for image in _image_urls(node.get('image')):
            if _url(image, canonical or image) not in images:
                problems.append(f'{label}: image {image!r} is neither the og:image '
                                f'nor an <img> on the page')

    if 'BreadcrumbList' in types:
        _check_list(label, node, problems, linked, canonical, breadcrumb=True)
    elif 'ItemList' in types:
        _check_list(label, node, problems, linked, canonical, breadcrumb=False)

    for key, value in node.items():
        if key.startswith('@') or key in _STRUCTURAL_KEYS or 'date' in key.lower():
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            claimed = {str(value).removesuffix('.0')}
        elif isinstance(value, str) and not _looks_like_url(value):
            claimed = _numbers(value)
        else:
            continue
        for n in sorted(claimed - visible_numbers):
            problems.append(f'{label}: {key} states {n}, which appears nowhere '
                            f'in the visible page')


def _check_page_node(path, node, problems, page, canonical, visible, linked, author):
    label = _label(path, node)
    types = _types(node)
    title_keys = {_PAGE_TITLE[t] for t in types if t in _PAGE_TITLE}
    if not title_keys:
        return
    for key in title_keys:
        title = _norm(node.get(key, ''))
        if not page.h1:
            problems.append(f'{label}: the page has no <h1> for {key} to agree with')
        elif title and title not in page.h1:
            problems.append(f'{label}: {key} {title!r} is not the page <h1> '
                            f'({page.h1[0]!r})')

    claimed_urls = []
    if isinstance(node.get('url'), str):
        claimed_urls.append(('url', node['url']))
    main = node.get('mainEntityOfPage')
    if isinstance(main, str):
        claimed_urls.append(('mainEntityOfPage', main))
    elif isinstance(main, dict) and isinstance(main.get('@id'), str):
        claimed_urls.append(('mainEntityOfPage.@id', main['@id']))
    for key, value in claimed_urls:
        if not canonical:
            problems.append(f'{label}: {key} is set but the page has no canonical link')
        elif _url(value, canonical) != canonical:
            problems.append(f'{label}: {key} {value!r} is not the canonical URL '
                            f'{page.canonical!r}')

    if types & _ARTICLE_TYPES:
        for who in (node.get('author') if isinstance(node.get('author'), list)
                    else [node.get('author')]):
            if isinstance(who, dict):
                _check_author(label, who, problems, visible, linked, canonical, author)


def _check_author(label, who, problems, visible, linked, canonical, expected):
    kinds = _types(who)
    name = _norm(who.get('name', ''))
    if expected and expected not in kinds:
        problems.append(f'{label}: author is {"/".join(sorted(kinds)) or "untyped"}, '
                        f'this page requires {expected}')
    if name and name not in visible:
        problems.append(f'{label}: author {name!r} is not named on the page')
    if 'Person' in kinds and isinstance(who.get('url'), str):
        target = _url(who['url'], canonical or who['url'])
        if target not in linked:
            problems.append(f'{label}: author {name!r} has url {who["url"]!r}, '
                            f'which the page does not link to')
        elif name and linked[target] != name:
            problems.append(f'{label}: the page links {who["url"]!r} as '
                            f'{linked[target]!r}, not {name!r}')


def _check_list(label, node, problems, linked, canonical, breadcrumb):
    items = node.get('itemListElement')
    if not isinstance(items, list):
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f'{label}: itemListElement[{i}] is not a ListItem')
            continue
        if item.get('position') != i + 1:
            problems.append(f'{label}: itemListElement[{i}] has position '
                            f'{item.get("position")!r}, expected {i + 1}')
        target = item.get('item') or item.get('url')
        if isinstance(target, dict):
            target = target.get('@id') or target.get('url')
        last = i == len(items) - 1
        if breadcrumb and not item.get('name'):
            problems.append(f'{label}: breadcrumb {i + 1} has no name')
        if not target:
            if not (breadcrumb and last):
                problems.append(f'{label}: entry {i + 1} has no item URL')
            continue
        resolved = _url(str(target), canonical or str(target))
        if breadcrumb and last:
            if canonical and resolved != canonical:
                problems.append(f'{label}: the last breadcrumb {target!r} is not '
                                f'this page')
        elif resolved not in linked:
            kind = 'breadcrumb' if breadcrumb else 'entry'
            problems.append(f'{label}: {kind} {i + 1} {target!r} is not linked '
                            f'from the page')


def _image_urls(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [value['url']] if isinstance(value.get('url'), str) else []
    if isinstance(value, list):
        return [u for v in value for u in _image_urls(v)]
    return []


def _looks_like_url(value: str) -> bool:
    return value.startswith(('http://', 'https://', '/', 'mailto:'))


def _comparable(a: datetime, b: datetime) -> bool:
    return (a.tzinfo is None) == (b.tzinfo is None)


def assert_structured_data(html: str, **kwargs) -> list[dict]:
    """`check()`, raising one AssertionError listing every problem.

    Returns the top-level nodes so a consumer can go on to assert what only it
    knows (`dateModified == last_revised_at`).
    """
    problems = check(html, **kwargs)
    assert not problems, ('JSON-LD breaks the structured data contract:\n  - '
                          + '\n  - '.join(problems))
    return nodes(html)
