#!/usr/bin/env python3

"""
Generate docs from module docstrigs
Link #<int> to github issue
Link <repo>#<int> to github issue
List #TODO and #FIXME

debdeps: asciidoc-base (>= 8.6.9)
debdeps: python3-markdown
"""

from configparser import ConfigParser
from io import StringIO
from pathlib import Path
from subprocess import check_call
from tempfile import NamedTemporaryFile
from textwrap import dedent
from typing import List
import ast
import base64
import sys
import zlib


try:
    # debdeps: asciidoc-base (>= 9.0.0)
    sys.path.append("/usr/share/asciidoc")
    import asciidocapi

    asciidoc_available = True
except ImportError:
    asciidoc_available = False

try:
    # debdeps: python3-markdown
    import markdown
    from markdown.extensions.toc import TocExtension
    from markdown.extensions.codehilite import CodeHiliteExtension
    from markdown.extensions.fenced_code import FencedCodeExtension

    markdown_available = True
except ImportError:
    markdown_available = False

# debdeps: python3-blockdiag

HTMLTPL = dedent(
    """
    <!doctype html>
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {head_links}
    <style>
    {css}
    </style>
    </head>
    <body>
    <div class="header">
      <div class="row">
        <div class="column">
          <h2>Project documentation</h2>
        </div>
      </div>
    </div>
    <div class="container" id="content">
    """
)

conf = None


def load_conf():
    confp = ConfigParser()
    with open("build_docs.ini") as f:
        confp.read_file(f)
    return confp["DEFAULT"]


def glob_ext(ignored, ext):
    for f in sorted(Path(".").glob(f"**/*.{ext}")):
        if any(i in f.as_posix() for i in ignored):
            continue
        yield f


def _scan_ast(i, skipfirst=True):
    for y in ast.iter_child_nodes(i):
        if isinstance(y, ast.Expr) and isinstance(y.value, ast.Str):
            if skipfirst:
                skipfirst = False
            else:
                yield y.value.s, y.lineno


def extract_python_doc(inputf) -> List:
    """Extract documentation strings from a Python file"""
    a = ast.parse(inputf.read_text())
    out = []

    def unroll(g):
        for item in g:
            s = str(item).strip()
            if s:
                out.append(s)

    out.extend(_scan_ast(a, skipfirst=False))

    for i in ast.iter_child_nodes(a):
        if isinstance(i, ast.FunctionDef):
            out.extend(_scan_ast(i))

        elif isinstance(i, ast.ClassDef):
            out.extend(_scan_ast(i))
            for x in ast.iter_child_nodes(i):
                if isinstance(x, ast.FunctionDef):
                    out.extend(_scan_ast(x))

    return out


def render_adoc(orig_source_f: Path, infile: StringIO):
    outfile = conf.outdir / orig_source_f.with_suffix(".html")
    outfile.parent.mkdir(parents=True, exist_ok=True)
    ad = asciidocapi.AsciiDocAPI()
    ad.attributes["author"] = conf.get("author", "")
    infile.seek(0)
    with outfile.open("w") as outf:
        ad.execute(infile, outf, backend="html5")


def render_markdown(orig_source_f: Path, inp: str):
    outfile = conf.outdir / orig_source_f.with_suffix(".html")
    outfile.parent.mkdir(parents=True, exist_ok=True)
    print(outfile)
    content = markdown.markdown(
        inp,
        extensions=[
            TocExtension(baselevel=3),
            CodeHiliteExtension(),
            FencedCodeExtension(),
        ],
    )
    html = wrap_page(orig_source_f, content)
    outfile.write_text(html)


def generate_github_link(action: str, f: Path):
    # action: blob edit
    url_tpl = conf.get("github_url_template")
    return url_tpl.format(action=action, path=f.as_posix(), lineno=0)


def generate_github_link_unused(action, f, lineno):
    # action: blob edit
    url_tpl = conf.get("github_url_template")
    url = url_tpl.format(action=action, path=f.as_posix(), lineno=lineno)
    adoc_tpl = f"""image:{action}.svg[link="{url}"]"""
    # return f"""\nimage::https://asciidoctor.org/images/octocat.jpg[link="{url}"]\n"""
    return adoc_tpl


def generate_badge(url, text):
    tpl = """
<a href="{url}" class="svg">
  <object type="image/svg+xml">
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="33" height="20">
<linearGradient id="b" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
<stop offset="1" stop-opacity=".1"/></linearGradient>
<clipPath id="a"><rect width="33" height="20" rx="3" fill="#fff"/></clipPath>
<g clip-path="url(#a)"><path fill="#97ca00" d="M0 0h0v20H0z"/><path fill="#97ca00" d="M0 0h33v20H0z"/>
<path fill="url(#b)" d="M0 0h33v20H0z"/></g>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="110">
<text x="165" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="230">{text}</text>
<text x="165" y="140" transform="scale(.1)" textLength="230">{text}</text></g></svg>
  </object>
</a>
    """
    return tpl.format(url=url, text=text)


def generate_header_path(inputf: Path) -> str:
    s = []
    backticker = "/".join([".."] * len(inputf.parents))
    if backticker:
        backticker += "/"
    pc = len(inputf.parents)

    for depth, x in enumerate(reversed(inputf.parents)):
        item = "link:{}{}[{}]".format(backticker, str(x), x.name)

        backticker = "/".join([".."] * (pc - depth - 1))
        item = "link:{}[{}]".format(backticker, x.name)

        s.append(item)
    last = "link:[{}]\n".format(inputf.name)
    s.append(last)
    out = " -> ".join(s)
    return out


def generate_header_path_html(inputf: Path) -> str:
    s = []
    backticker = "/".join([".."] * len(inputf.parents))
    if backticker:
        backticker += "/"
    pc = len(inputf.parents)

    for depth, x in enumerate(reversed(inputf.parents)):
        backticker = "/".join([".."] * (pc - depth - 1))
        item = "<a href='{}/index.html'>{}</a>".format(backticker, x.name)
        s.append(item)

    # last = "[{}](.)".format(inputf.name)
    last = "<a href=''>{}</a>".format(inputf.name)
    s.append(last)
    out = " » ".join(s)
    return """<div id="pagepath">""" + out + "</div>"


def generate_view_badge(f: Path):
    url = generate_github_link("blob", f)
    return generate_badge(url, "view")


def generate_edit_badge(f: Path):
    url = generate_github_link("edit", f)
    return generate_badge(url, "edit")


def generate_python_adoc(inputf: Path, pdoc: List):
    adoc = []
    adoc.append(generate_header_path(inputf))
    for content, lineno in pdoc:
        # gh_b = generate_github_link("blob", inputf, lineno)
        # f.write(gh_b)
        adoc.append("++++")
        adoc.append(generate_view_badge(inputf))
        adoc.append(generate_edit_badge(inputf))
        adoc.append("++++")
        adoc.append("\n" + content + "\n")

    return StringIO("\n".join(adoc))


def generate_html_begin(orig_source_f):
    hl = conf.get("html_imports", "")
    css = conf.get("css", "")
    return HTMLTPL.format(title=orig_source_f.name, head_links=hl, css=css)


def wrap_page(orig_source_f, content):
    begin = generate_html_begin(orig_source_f)
    header = generate_header_path_html(orig_source_f)
    footer = conf.get("footer", "")
    end = "</div>" + footer + "</body></html>"
    return begin + header + content + end


def generate_python_markdown(inputf: Path, pdoc: List):
    lines = []
    for content, lineno in pdoc:
        lines.append(generate_view_badge(inputf))
        lines.append(generate_edit_badge(inputf))
        lines.append("\n" + content + "\n")

    return "\n".join(lines)


def render_blockdiag(diag: str) -> str:
    """Render blockdiag to SVG"""
    print("Rendering blockdiag")
    inp = NamedTemporaryFile("w")
    inp.write(diag)
    inp.flush()
    out = NamedTemporaryFile("r")
    cmd = ["/usr/bin/blockdiag3", "-T", "svg", "-o", out.name, inp.name]
    check_call(cmd)
    svg = out.read()
    _, _, svg = svg.split("\n", 2)
    return svg


def process_diagrams(md: str) -> str:
    """Extract diagrams and replace them with SVG/PNG images"""
    out = ""
    for block in md.split("\nblockdiag {"):
        try:
            diag, post = block.split("\n}", 1)
            diag = "blockdiag {\n" + diag + "\n}\n"
            # url = generate_kroki_url(diag, "blockdiag")
            # exp = "https://kroki.io/blockdiag/svg/eNpdzDEKQjEQhOHeU4zpPYFoYesRxGJ9bwghMSsbUYJ4d10UCZbDfPynolOek0Q8FsDeNCestoisNLmy-Qg7R3Blcm5hPcr0ITdaB6X15fv-_YdJixo2CNHI2lmK3sPRA__RwV5SzV80ZAegJjXSyfMFptc71w=="
            # assert url == exp, url
            # url = f"""<img src="{url}">"""
            # out += url
            svg = render_blockdiag(diag)
            out += f"\n<div>{svg}</div>"
            out += post

        except ValueError as e:
            out += block

    return out


# assert process_diagrams("") == ""
# svg = process_diagrams("a\nblockdiag {\n}\nb")
# assert svg == """a
# <svg viewBox="0 0 256 120" xmlns="http://www.w3.org/2000/svg" xmlns:inkspace="http://www.inkscape.org/namespaces/inkscape" xmlns:xlink="http://www.w3.org/1999/xlink">
#   <defs id="defs_block">
#     <filter height="1.504" id="filter_blur" inkspace:collect="always" width="1.1575" x="-0.07875" y="-0.252">
#       <feGaussianBlur id="feGaussianBlur3780" inkspace:collect="always" stdDeviation="4.2" />
#     </filter>
#   </defs>
#   <title>blockdiag</title>
#   <desc>blockdiag {
#
# }
# </desc>
# </svg>
#
# b""", svg


def generate_kroki_url(content, method: str) -> str:
    """Generate URL for https://kroki.io/"""
    # FIXME: Broken
    if method != "blockdiag":
        raise NotImplementedError

    baseurl = "https://kroki.io/graphviz/svg/"
    content = content.encode()
    path = base64.urlsafe_b64encode(zlib.compress(content, 9))
    path = path.decode()
    return baseurl + path


def create_index_html(basedir: Path):
    """Recursively create index.html files"""
    for d in basedir.iterdir():
        if d.is_dir():
            create_index_html(d)

    out = generate_html_begin(basedir)
    out += generate_header_path_html(basedir)
    out += "<ul>"
    for f in sorted(basedir.iterdir()):
        n = f.with_suffix("").name
        if f.is_dir():
            out += "<li><a href='{}/index.html'>» {}</a></li>".format(f.name, n)
        elif f.suffix == ".html":
            out += "<li><a href='{}'>{}</a></li>".format(f.name, n)

    footer = conf.get("footer", "")
    footer = "</ul></div>" + footer + "</body></html>"
    out += footer
    indexf = basedir / "index.html"
    indexf.write_text(out)


def main():
    global conf
    conf = load_conf()
    ignored = conf.get("ignore_paths_substr", "").split()
    markup_format = conf.get("markup_format", "markdown")
    conf.outdir = Path(conf.get("outdir", "build_docs_output"))
    conf.outdir.mkdir(parents=True, exist_ok=True)

    if markup_format == "asciidoc":
        print("Rendering AsciiDoc files")
        for adocf in glob_ext(ignored, "adoc"):
            # render_adoc(renderer, adocf)
            pass

    elif markup_format == "markdown":
        print("Rendering MarkDown files")
        for f in glob_ext(ignored, "md"):
            md = f.read_text()
            md = process_diagrams(md)
            render_markdown(f, md)
            pass

    print("Rendering Python files")
    for pyfile in glob_ext(ignored, "py"):
        try:
            pdoc = extract_python_doc(pyfile)
            if not len(pdoc):
                continue

            if markup_format == "asciidoc":
                raise NotImplementedError
                adocf = generate_python_adoc(pyfile, pdoc)
                render_adoc(pyfile, adocf)

            elif markup_format == "markdown":
                md = generate_python_markdown(pyfile, pdoc)
                md = process_diagrams(md)
                render_markdown(pyfile, md)

        except Exception as e:
            print(e)

    create_index_html(conf.outdir)

    print("Done")


if __name__ == "__main__":
    main()
