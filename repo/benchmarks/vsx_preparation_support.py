"""Read-only public-source retrieval for the dated VSX preparation dossier."""
from html.parser import HTMLParser
from pathlib import Path
import requests
from vstar.io import now, read_json, write_json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'repo/runs/vsx-preparation-2026-11-23'


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links, self.fields = [], [], []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'br', 'tr', 'td', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n')
        if tag == 'a' and values.get('href'):
            self.links.append(values['href'])
        if tag in ('input', 'select', 'form', 'option'):
            self.fields.append((tag, values))

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return '\n'.join(x.strip() for x in ''.join(self.parts).splitlines() if x.strip())


def parsed(name):
    receipt = read_json(OUT / 'sources' / (name + '.json'))
    parser = HTMLText()
    parser.feed(receipt.get('body', ''))
    return parser


def fetch(name, url, params=None, *, data=None, timeout=30):
    """Save transport failures distinctly; never interpret them as no matches."""
    path = OUT / 'sources' / (name + '.json')
    if path.exists():
        return read_json(path)
    receipt = {'at': now(), 'url': url, 'params': params or {}, 'data': data,
               'method': 'POST' if data is not None else 'GET'}
    try:
        response = requests.request(receipt['method'], url, params=params, data=data, timeout=timeout)
        receipt.update(resolved_url=response.url, status_code=response.status_code, body=response.text)
    except requests.RequestException as exc:
        receipt['error'] = str(exc)
    write_json(path, receipt)
    return receipt
