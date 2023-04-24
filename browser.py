from dataclasses import dataclass
import re
import socket
import ssl
import time
import tkinter
import tkinter.font
from typing import List, Union
import sys

cached_urls = {}
WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
FONTS = {}
example_str = "<html><body><h1>Hello World</h1> <p>I love HTML</p></body></html>"
SELF_CLOSING_TAGS = [
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
]
HEAD_TAGS = [
    "base", "basefont", "bgsound", "noscript",
    "link", "meta", "title", "style", "script",
]
BLOCK_ELEMENTS = [
    "html", "body", "article", "section", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
    "footer", "address", "p", "hr", "pre", "blockquote",
    "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
    "figcaption", "main", "div", "table", "form", "fieldset",
    "legend", "details", "summary"
]

def request(url, headers=None, redirects=0):
    # if too many redirects, raise an exception
    init_url = url
    if redirects > 8:
        raise Exception("Too many redirects")
    # if url is in cache, return the cached value
    if init_url in cached_urls:
        if cached_urls[init_url][0] > time.time():
            return cached_urls[init_url][1], cached_urls[init_url][2]

    # split url and check for scheme
    scheme, url = url.split("://", 1)
    assert scheme in ["http", "https", "file"], \
        "Unknown scheme {}".format(scheme)

    # handle file scheme
    if scheme == "file":
        with open(url, "r") as f:
            return {}, f.read()
    
    host, path = url.split("/", 1)
    path = "/" + path
    port = 80 if scheme == "http" else 443

    if ":" in host:
        host, port = host.split(":", 1)
        port = int(port)

    # connect to host and send request
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    s.connect((host, port))
    
    # wrap socket if using https
    if scheme == "https":
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)

    # check for user-input headers
    if headers is None:
        headers = {"User-Agent": "Chrome/112.0.5615.45"}
    
    # create request string and update headers within it
    req = "GET {} HTTP/1.1\r\n".format(path) + \
        "Host: {}\r\n".format(host) + \
        "Connection: close\r\n"
    for header, value in headers.items():
        if header.lower() not in req:
            req += "{}: {}\r\n".format(header, value)
    req += "\r\n"

    s.send(req.encode("utf8"))
    response = s.makefile("r", encoding="utf8", newline="\r\n")

    # read status line and check for errors
    statusline = response.readline()
    version, status, explanation = statusline.split(" ", 2)
    assert status == "200" or (status >= "300" and status < "400"), "{}: {}".format(status, explanation)

    # read headers
    cur_headers = {}
    while True:
        line = response.readline()
        if line == "\r\n":
            break
        header, value = line.split(":", 1)
        cur_headers[header.lower()] = value.strip()
    
    # handle redirects
    if status >= "300" and status < "400":
        location = cur_headers["location"]
        if not location.startswith(scheme): 
            location = scheme + "://" + host + location
        return request(location, headers, redirects + 1)
    
    assert "transfer-encoding" not in cur_headers
    assert "content-encoding" not in cur_headers

    body = response.read()
    s.close()
    
    # check for cache-control header
    if "cache-control" in cur_headers:
        if "no-store" in cur_headers["cache-control"]:
            return cur_headers, body
        if "max-age" in cur_headers["cache-control"]:
            max_age = int(cur_headers["cache-control"].split("=", 1)[1])
            cur_time = time.time() + max_age
            cached_urls[init_url] = (cur_time, cur_headers, body)

    return cur_headers, body

# Element and Text classes for the HTML document tree
class Element:
    def __init__(self, tag, parent, attributes):
        self.tag = tag
        self.children = []
        self.parent = parent
        self.attributes = attributes

    def __repr__(self):
        attrs = ""
        for attr, value in self.attributes.items():
            attrs += " {}=\"{}\"".format(attr, value)
        return "<" + self.tag + attrs + ">"

class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

Node = Union[Element, Text]

class HTMLParser:
    def __init__(self, body):
        self.body = body
        self.unfinished = []
        self.in_script = False
    
    def parse(self) -> Node:
        text = ""
        tag = False
        comment = False
        open_quote = None
        i = 0
        while i < len(self.body):
            c = self.body[i]
            if tag and (c == "\"" or c == "'"):
                if open_quote == c:
                    open_quote = None
                elif not open_quote:
                    open_quote = c
            if not comment and self.body[i:i+4] == "<!--":
                if text: self.add_text(text)
                text = ""
                comment = True
                i += 4
                continue
            elif comment and self.body[i:i+3] == "-->":
                comment = False
                i += 3
                continue
            elif comment:
                i += 1
                continue
            elif c == "<" and not open_quote:
                if self.in_script:
                    if self.body[i:i+9] == "</script>":
                        self.in_script = False
                        i += 9
                    else:
                        text += c
                        i += 1
                    continue
                tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">" and not open_quote:
                if self.in_script:
                    text += c
                    i += 1
                    continue
                tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
            i += 1
        if not tag and text:
            self.add_text(text)
        return self.finish()

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in HEAD_TAGS:
                    self.add_tag("head")
                    if tag == "script":
                        self.in_script = True
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

    def add_text(self, text):
        if text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"): return
        self.implicit_tags(tag)

        if tag.startswith("/"):
            if len(self.unfinished) == 1: return
            popped = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(popped)
        elif tag in SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, parent, attributes)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            if tag == "p" and self.open_p():
                closed_tags = []
                while self.unfinished[-1].tag != "p":
                    cur_node = self.unfinished[-1]
                    self.add_tag("/" + cur_node.tag)
                    closed_tags.append(cur_node.tag)
                self.add_tag("/p")
                self.add_tag("p")
                for tag in reversed(closed_tags):
                    self.add_tag(tag)
            else:
                node = Element(tag, parent, attributes)
                self.unfinished.append(node)
    
    def open_p(self):
        for node in reversed(self.unfinished):
            if isinstance(node, Element) and node.tag == "p":
                return True
        return False

    def get_attributes(self, text):
        parts = text.split(" ", 1)
        tag = parts[0].lower()
        attrs = []
        if len(parts) > 1:

            text = ""
            open_quote = None

            for c in parts[1]:
                if c == ' ' and not open_quote:
                    attrs.append(text)
                    text = ""
                elif c == open_quote:
                    attrs.append(text)
                    text = ""
                elif (c == "'" or c == '"') and not open_quote:
                    open_quote = c
                else:
                    text += c

            if text:
                attrs.append(text)

        attributes = {}

        for attrpair in attrs:
            if attrpair.startswith("="):
                if "=" in attrpair[1:]:
                    key, value = attrpair[1:].split("=", 1)
                else:
                    key, value = attrpair[1:], ""
                key = "=" + key
                attributes[key.lower()] = value
            elif "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
                attributes[key.lower()] = value
            else:
                attributes[attrpair.lower()] = ""
        return tag, attributes

    def finish(self) -> Node:
        if len(self.unfinished) == 0:
            self.add_tag("html")
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

@dataclass
class TokText:
    text: str
    
    def __repr__(self) -> str:
        return "Text('{}')".format(self.text)

@dataclass
class Tag:
    tag: str
    
    def __repr__(self) -> str:
        return "Tag('{}')".format(self.tag)

Token = Union[TokText, Tag]

class DocumentLayout:
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []
        
    
    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        child.layout()
        self.display_list = child.display_list
        self.width = WIDTH - 2*HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height + 2*VSTEP

class BlockLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
    
    def layout(self):
        mode = self.layout_mode(self.node)
        self.display_list = []
        self.x = self.parent.x
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        self.width = self.parent.width
        if mode == "block":
            self.height = sum(child.height for child in self.children)
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
            for child in self.children:
                child.layout()
            for child in self.children:
                self.display_list.extend(child.display_list)
        else:
            assert mode == "inline"

            self.display_list = []
            self.line = []

            self.cursor_x = 0
            self.cursor_y = 0
            self.weight = "normal"
            self.style = "roman"
            self.height = self.cursor_y

            self.centered = False
            self.superscript = False
            self.small_cap = False
            self.size = 16

            self.recurse(self.node)
            self.flush()
    
    def layout_intermediate(self):
        previous = None
        for child in self.node.children:
            next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next
    
    def layout_mode(self, node):
        if isinstance(node, Text):
            return "inline"
        elif node.children:
            if any(isinstance(child, Element) and \
                    child.tag in BLOCK_ELEMENTS
                    for child in node.children):
                return "block"
            else:
                return "inline"
        else:
            return "block"

    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        if tag == "b":
            self.weight = "bold"
        if tag == "small":
            self.size -= 2
        if tag == "big":
            self.size += 4
        if tag == "br":
            self.flush()
        if tag == "h1":
            self.flush()
            self.centered = True
        if tag == "sup":
            self.superscript = True
        if tag == "abbr":
            self.small_cap = True
    
    def close_tag(self, tag):
        if tag == "i":
            self.style = "roman"
        if tag == "b":
            self.weight = "normal"
        if tag == "small":
            self.size += 2
        if tag == "big":
            self.size -= 4
        if tag == "h1":
            self.flush()
            self.centered = False
        if tag == "sup":
            self.superscript = False
        if tag == "abbr":
            self.small_cap = False
    

    def recurse(self, tree):
        if isinstance(tree, Text):
            self.text(tree)
        else:
            assert isinstance(tree, Element)
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)
    
    def flush(self):
        if not self.line: return

        line_length = self.cursor_x - HSTEP
        shift = 0
        if self.centered:
            shift = (WIDTH - line_length) / 2 - 5
        
        metrics = [font.metrics() for x, text, font, sup in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent

        for x, text, font, sup in self.line:
            if sup:
                y = baseline - max_ascent
            else:
                y = baseline - font.metrics("ascent")
            self.display_list.append((x + shift + self.x, y + self.y, text, font))
        
        self.cursor_x = 0
        self.line = []
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent
    
    def text(self, node):
        if self.superscript:
            size = self.size // 2
        else:
            size = self.size
        font = get_font(size, self.weight, self.style)
        text = node.text
        for word in text.split():
            if self.small_cap:
                for i in re.split(r"([a-z]+)", word):
                    if not i:
                        continue
                    if i[0].islower():
                        i = i.upper()
                        font = get_font(self.size // 2, "bold", self.style)
                    else:
                        font = get_font(self.size, self.weight, self.style)
                    w = font.measure(i)
                    
                    self.line.append((self.cursor_x, i, font, self.superscript))

                    if self.cursor_x + w > self.width:
                        self.cursor_y += font.metrics("linespace") * 1.25
                        self.cursor_x = HSTEP
                        self.flush()
                    self.cursor_x += w
                if word.split():
                    big_font = get_font(self.size, self.weight, self.style)
                    self.cursor_x += big_font.measure(" ")
            else:
                w = font.measure(word)
                if self.cursor_x + w > WIDTH - HSTEP:
                    if '\N{soft hyphen}' in word:
                        word = word.replace('\N{soft hyphen}', '\n')
                        hws = word.split('\n')
                        hsent = ""
                        
                        for hw in hws:
                            if self.cursor_x + font.measure(hsent + hw + "-") > WIDTH - HSTEP:
                                self.line.append((self.cursor_x, hsent + "-", font, self.superscript))
                                self.flush()
                                hsent = ""
                            hsent += hw
                        
                        if hsent:
                            self.line.append((self.cursor_x, hsent, font, self.superscript))
                            self.cursor_x += font.measure(hsent + " ")
                    else:
                        self.flush()
                else:
                    self.line.append((self.cursor_x, word, font, self.superscript))
                    self.cursor_x += w + font.measure(" ")

def get_font(size, weight, slant):
    key = (size, weight, slant)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=slant)
        FONTS[key] = font
    return FONTS[key]

def lex(body) -> List[Token]:
    tokens: List[Token] = []
    text = ""
    tag = False
    for t in body:
        if t == "<":
            if text:
                tokens.append(TokText(text))
                text = ""
            tag = True
        elif t == ">":
            tokens.append(Tag(text))
            text = ""
            tag = False
        else:
            text += t
    if not tag and text:
        tokens.append(TokText(text))
    return tokens

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack(fill="both", expand=True)
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<Configure>", self.resize)
        self.window.bind("<MouseWheel>", self.scrolling)
        self.window.bind("+", self.zoomin)
        self.window.bind("-", self.zoomout)
    
    def scrolldown(self, ev):
        self.scroll += SCROLL_STEP
        self.draw()
    
    def scrollup(self, ev):
        self.scroll -= SCROLL_STEP
        if self.scroll < 0:
            self.scroll = 0
        self.draw()
    
    def scrolling(self, ev):
        if ev.delta > 0:
            self.scrollup(ev)
        else:
            self.scrolldown(ev)
    
    def zoomin(self, ev):
        global VSTEP, HSTEP
        VSTEP *= 2
        HSTEP *= 2
        self.font_size *= 2
        self.display_list = self.document.display_list
        self.draw()
    
    def zoomout(self, ev):
        global VSTEP, HSTEP
        VSTEP //= 2
        HSTEP //= 2
        self.font_size //= 2
        self.display_list = self.document.display_list
        self.draw()
    
    def resize(self, ev):
        global WIDTH, HEIGHT
        WIDTH = ev.width
        HEIGHT = ev.height
        self.display_list = self.document.display_list
        self.draw()
    
    def draw(self):
        self.canvas.delete("all")
        for x, y, c, f in self.display_list:
            if y > self.scroll + HEIGHT: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c, font=f, anchor="nw")

    def load(self, url):
        # load url and print body
        headers, body = request(url)
        self.nodes = HTMLParser(body).parse()
        self.document = BlockLayout(self.nodes, None, None)
        self.document.layout()
        self.display_list = self.document.display_list
        self.draw()


def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

if __name__ == "__main__":
    import sys
    Browser().load(sys.argv[1])
    tkinter.mainloop()