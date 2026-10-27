"""The structured data contract, against hand-written pages.

Each test names the drift it catches. Every one of these pages is valid JSON in
a 200 response, which is the point: the contract exists for the failures that
look healthy. Run with `python -m pytest tests` (pytest only; no other deps).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'python'))

import pytest  # noqa: E402

from fleet_contracts.structured_data import (  # noqa: E402
    assert_structured_data, check, nodes)

BASE = 'https://blog.test'
URL = f'{BASE}/guides/ten-tips/'


def article(**over):
    data = {
        '@context': 'https://schema.org', '@type': 'Article',
        'headline': 'Ten tips for 2026',
        'description': 'Ten tips, three of them about bread.',
        'datePublished': '2026-10-01T12:00:00Z',
        'dateModified': '2026-10-05T09:30:00Z',
        'url': URL, 'mainEntityOfPage': {'@type': 'WebPage', '@id': URL},
        'publisher': {'@type': 'Organization', 'name': 'Blog', 'url': BASE},
        'author': {'@type': 'Organization', 'name': 'Blog', 'url': BASE},
        'image': f'{BASE}/media/hero.jpg',
        'breadcrumb': {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Blog', 'item': BASE},
            {'@type': 'ListItem', 'position': 2, 'name': 'Guides',
             'item': f'{BASE}/guides/'},
            {'@type': 'ListItem', 'position': 3, 'name': 'Ten tips for 2026',
             'item': URL},
        ]},
    }
    data.update(over)
    return data


def page(data, body='', h1='Ten tips for 2026'):
    blocks = data if isinstance(data, list) else [data]
    scripts = ''.join(f'<script type="application/ld+json">{json.dumps(b)}</script>'
                      for b in blocks)
    return f"""<!DOCTYPE html><html lang="en"><head>
<title>Ten tips — Blog</title>
<link rel="canonical" href="{URL}">
<meta property="og:image" content="{BASE}/media/hero.jpg">
{scripts}
</head><body>
<header><a class="site-brand" href="/">Blog</a></header>
<article>
<a href="/guides/?utm_medium=internal">Guides</a>
<h1>{h1}</h1>
<p>Published by <em>Blog</em> ·
<time datetime="2026-10-01T12:00:00Z">October 1</time> ·
Last Edited <time datetime="2026-10-05T09:30:00Z">October 5</time></p>
<p>Ten tips, three of them about bread.</p>
{body}
</article></body></html>"""


def test_a_page_that_keeps_the_contract_has_no_problems():
    assert check(page(article()), require={'Article', 'BreadcrumbList'}) == []


def test_assert_returns_the_nodes_for_a_consumers_own_assertions():
    found = assert_structured_data(page(article()))
    assert found[0]['dateModified'] == '2026-10-05T09:30:00Z'


def test_a_page_with_no_block_fails_only_when_one_is_required():
    """Without `require`, a template that lost its JSON-LD block would pass
    every other rule vacuously — the most complete drift there is."""
    html = page([]).replace('<script', '<x')
    assert check(html) == []
    assert check(html, require={'Article'}) == ['the page carries no JSON-LD block']


def test_a_required_type_that_is_missing_is_named():
    data = article()
    del data['breadcrumb']
    assert check(page(data), require={'Article', 'BreadcrumbList'}) == [
        'no BreadcrumbList node, and this page type requires one']


def test_an_unparseable_block_is_reported_not_skipped():
    html = page(article()).replace('"@type": "Article"', '"@type": Article')
    assert any('does not parse' in p for p in check(html))


@pytest.mark.parametrize('field', ['headline', 'datePublished', 'author', 'publisher'])
def test_an_article_missing_a_required_field_is_reported(field):
    data = article()
    del data[field]
    assert any(f"missing required field '{field}'" in p for p in check(page(data)))


def test_an_empty_value_is_a_claim_the_page_does_not_fill():
    """The blogs' WebSite block shipped `"description": ""` for every site
    with no tagline."""
    problems = check(page(article(alternativeHeadline='')))
    assert any("'alternativeHeadline' is present but empty" in p for p in problems)


def test_the_headline_must_be_the_pages_h1():
    """seo_meta can retitle an article; a headline the page does not carry is
    a rich result for a page that does not exist."""
    problems = check(page(article(), h1='Eleven tips'))
    assert any("is not the page <h1>" in p for p in problems)


def test_the_url_must_be_the_canonical():
    problems = check(page(article(url=f'{BASE}/articles/ten-tips/')))
    assert any('is not the canonical URL' in p for p in problems)


def test_date_modified_must_be_a_date_the_page_shows():
    """`updated_at` moves for score and image changes; a dateModified built
    from it tells a search engine the prose changed when the reader is told
    nothing did."""
    problems = check(page(article(dateModified='2026-10-20T00:00:00Z')))
    assert problems == ["block0 (Article): dateModified '2026-10-20T00:00:00Z' "
                        "is not a <time datetime> the page shows"]


def test_a_date_written_differently_but_naming_the_same_moment_agrees():
    assert check(page(article(datePublished='2026-10-01T12:00:00+00:00'))) == []


def test_a_date_that_is_not_iso_8601_is_reported():
    problems = check(page(article(dateModified='5 October 2026')))
    assert any('is not an ISO 8601 date' in p for p in problems)


def test_modified_before_published_is_reported():
    html = page(article(dateModified='2026-09-01T00:00:00Z'),
                body='<time datetime="2026-09-01T00:00:00Z">x</time>')
    assert any('earlier than datePublished' in p for p in check(html))


def test_a_number_the_page_never_states_is_reported():
    """The model writes the meta description; a figure in it that the article
    never states is a claim with no source, shown in a search result."""
    problems = check(page(article(description='Ten tips, 40% faster bread.')))
    assert problems == ["block0 (Article): description states 40, which "
                        "appears nowhere in the visible page"]


def test_numbers_match_with_thousands_separators_either_way():
    html = page(article(description='Feeds 1,500 readers.'), body='<p>1500 readers</p>')
    assert check(html) == []


def test_dates_urls_and_positions_are_not_claims():
    # Every date, URL and breadcrumb position above carries digits the page
    # does not print as such; none of them may be reported.
    assert check(page(article())) == []


def test_a_numeric_value_must_appear_on_the_page():
    problems = check(page(article(wordCount=1530)))
    assert any('wordCount states 1530' in p for p in problems)
    assert check(page(article(wordCount=1530), body='<p>1530 words</p>')) == []


def test_a_persona_is_never_labelled_a_person():
    """Persona credentials are invented. A visible "By Marcus Webb" credit is
    honest; a Person claim in structured data is not."""
    data = article(author={'@type': 'Person', 'name': 'Marcus Webb'})
    html = page(data, body='<p>By <a href="/author/ab12/">Marcus Webb</a></p>')
    problems = check(html, personas={'Marcus Webb'})
    assert any('is a persona, labelled as a Person' in p for p in problems)


def test_the_author_kind_is_what_the_page_requires():
    problems = check(page(article()), author='Person')
    assert any('author is Organization, this page requires Person' in p
               for p in problems)


def test_a_person_author_must_be_named_and_linked_by_that_name():
    who = {'@type': 'Person', 'name': 'Jane Doe', 'url': f'{BASE}/writer/jane-doe/'}
    good = page(article(author=who),
                body='<a href="/writer/jane-doe/">Jane Doe</a>')
    assert check(good, author='Person') == []

    unlinked = page(article(author=who), body='<p>Jane Doe</p>')
    assert any('which the page does not link to' in p for p in check(unlinked))

    misnamed = page(article(author=who),
                    body='<p>Jane Doe</p><a href="/writer/jane-doe/">J. Doe</a>')
    assert any("as 'J. Doe', not 'Jane Doe'" in p for p in check(misnamed))


def test_an_organization_author_must_be_named_on_the_page():
    data = article(author={'@type': 'Organization', 'name': 'Other Press'})
    assert any("author 'Other Press' is not named" in p for p in check(page(data)))


def test_an_image_the_page_does_not_show_is_reported():
    problems = check(page(article(image=f'{BASE}/media/other.jpg')))
    assert any('is neither the og:image nor an <img>' in p for p in problems)


def test_an_image_in_a_srcset_counts():
    html = page(article(image={'@type': 'ImageObject', 'url': f'{BASE}/media/b.webp'}),
                body='<img srcset="/media/a.webp 480w, /media/b.webp 960w" alt="">')
    assert check(html) == []


def test_a_breadcrumb_the_page_does_not_link_is_reported():
    data = article()
    data['breadcrumb']['itemListElement'][1]['item'] = f'{BASE}/recipes/'
    assert any("breadcrumb 2 'https://blog.test/recipes/' is not linked" in p
               for p in check(page(data)))


def test_the_last_breadcrumb_must_be_this_page():
    data = article()
    data['breadcrumb']['itemListElement'][2]['item'] = f'{BASE}/guides/other/'
    assert any('the last breadcrumb' in p for p in check(page(data)))


def test_breadcrumb_positions_must_count_from_one():
    data = article()
    data['breadcrumb']['itemListElement'][0]['position'] = 0
    assert any('has position 0, expected 1' in p for p in check(page(data)))


def test_an_item_list_entry_must_be_linked_from_the_page():
    listing = {
        '@context': 'https://schema.org', '@type': 'CollectionPage',
        'name': 'Ten tips for 2026', 'url': URL,
        'mainEntity': {'@type': 'ItemList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'url': f'{BASE}/guides/a/'},
            {'@type': 'ListItem', 'position': 2, 'url': f'{BASE}/guides/b/'},
        ]},
    }
    html = page(listing, body='<a href="/guides/a/?utm_content=category">A</a>')
    assert check(html) == [
        "block0.mainEntity (ItemList): entry 2 'https://blog.test/guides/b/' "
        "is not linked from the page"]


def test_a_dataset_description_must_be_long_enough_for_google():
    data = {'@context': 'https://schema.org', '@type': 'Dataset',
            'name': 'Ten tips for 2026', 'description': 'Too short.'}
    assert any('50–5000 characters' in p for p in check(page(data)))


def test_a_graph_is_checked_node_by_node():
    data = {'@context': 'https://schema.org', '@graph': [
        {k: v for k, v in article().items() if k != '@context'}]}
    assert check(page(data), require={'Article'}) == []


def test_a_wrong_context_is_reported():
    problems = check(page(article(**{'@context': 'https://example.org'})))
    assert any('@context' in p for p in problems)


def test_nodes_skips_a_block_it_cannot_parse():
    html = page(article()).replace('</head>',
                                   '<script type="application/ld+json">{</script></head>')
    assert [n['@type'] for n in nodes(html)] == ['Article']
