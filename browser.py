from ast import Tuple
from dataclasses import dataclass
import re
import socket
import ssl
import time
import tkinter
import tkinter.font
from typing import List, Union
import sys
import urllib.parse
import dukpy

cached_urls = {}
WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
CHROME_PX = 100
INPUT_WIDTH_PX = 200
CHECK_SIZE = 16
FONTS = {}
BOOKMARKS = []
example_str = "<html><body><h1>Hello World</h1> <p>I love HTML</p></body></html>"
EVENT_DISPATCH_CODE = "new Node(dukpy.handle).dispatchEvent(new Event(dukpy.type))"
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
COOKIE_JAR = {}

def request(url, top_level_url, payload=None, headers=None, redirects=0, referrer_policy=None):
    # if too many redirects, raise an exception
    init_url = url
    if redirects > 8:
        raise Exception("Too many redirects")
    # if url is in cache, return the cached value
    if init_url in cached_urls:
        if cached_urls[init_url][0] > time.time():
            return cached_urls[init_url][1], cached_urls[init_url][2]
    
    if url == "about:bookmarks":
        html = "<!doctype html>\n"
        for bookmark in BOOKMARKS:
            html += "<a href=\"{}\">{}</a><br>\n".format(bookmark, bookmark)
        return {}, html

    # split url and check for scheme
    scheme, url = url.split("://", 1)
    assert scheme in ["http", "https", "file"], \
        "Unknown scheme {}".format(scheme)

    # handle file scheme
    if scheme == "file":
        with open(url, "r") as f:
            return {}, f.read(), False
    
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
        try:
            s = ctx.wrap_socket(s, server_hostname=host)
        except:
            return {}, "<!doctype html>\n Secure Connection Failed", False

    # check for user-input headers
    if headers is None:
        headers = {"User-Agent": "Chrome/112.0.5615.45"}
    
    method = "POST" if payload else "GET"
    
    # create request string and update headers within it
    req = "{} {} HTTP/1.1\r\n".format(method, path) + \
        "Host: {}\r\n".format(host) + \
        "Connection: close\r\n"
    for header, value in headers.items():
        if header.lower() not in req:
            req += "{}: {}\r\n".format(header, value)
    
    if payload:
        length = len(payload.encode("utf8"))
        req += "Content-Length: {}\r\n".format(length)
    if referrer_policy == "no-referrer":
        pass
    elif referrer_policy == "same-origin":
        _, _, top_level_host, _ = top_level_url.split("/", 3)
        if ":" in top_level_host:
            top_level_host, _ = top_level_host.split(":", 1)

        if host == top_level_host:
            req += "Referer: {}\r\n".format(top_level_url)
    else:
        req += "Referer: {}\r\n".format(top_level_url)
    
    if host in COOKIE_JAR:
        cookie, params = COOKIE_JAR[host]
        allow_cookie = True
        if top_level_url and params.get("samesite", "none") == "lax":
            _, _, top_level_host, _ = top_level_url.split("/", 3)
            if ":" in top_level_host:
                top_level_host, _ = top_level_host.split(":", 1)
            allow_cookie = (host == top_level_host or method == "GET")
        if allow_cookie:
            req += "Cookie: {}\r\n".format(cookie)

    req += "\r\n" + (payload if payload else "")

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
    
    if "referer" in cur_headers:
        top_level_url = cur_headers["referer"]

    if "set-cookie" in cur_headers:
        params = {}
        if ";" in cur_headers["set-cookie"]:
            cookie, rest = cur_headers["set-cookie"].split(";", 1)
            for param_pair in rest.split(";"):
                if "=" in param_pair:
                    name, value = param_pair.strip().split("=", 1)
                else:
                    name = param_pair.strip()
                    value = ""
                params[name.lower()] = value.lower()
        else:
            cookie = cur_headers["set-cookie"]
        COOKIE_JAR[host] = (cookie, params)
    
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
            return cur_headers, body, scheme == "https"
        if "max-age" in cur_headers["cache-control"]:
            max_age = int(cur_headers["cache-control"].split("=", 1)[1])
            cur_time = time.time() + max_age
            cached_urls[init_url] = (cur_time, cur_headers, body)

    return cur_headers, body, scheme == "https"

def resolve_url(url, current):
    if "://" in url:
        return url
    elif url.startswith("/"):
        scheme, hostpath = current.split("://", 1)
        host, oldpath = hostpath.split("/", 1)
        return scheme + "://" + host + url
    else:
        scheme, hostpath = current.split("://", 1)
        if "/" not in hostpath:
            current = current + "/"
        dir, _ = current.rsplit("/", 1)
        while url.startswith("../"):
            url = url[3:]
            if dir.count("/") == 2: continue
            dir, _ = dir.rsplit("/", 1)
        return dir + "/" + url

# Element and Text classes for the HTML document tree
class Element:
    def __init__(self, tag, attributes, parent):
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
                # if self.in_script:
                #     if self.body[i:i+9] == "</script>":
                #         self.in_script = False
                #         i += 9
                #     else:
                #         text += c
                #         i += 1
                #     continue
                tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">" and not open_quote:
                # if self.in_script:
                #     text += c
                #     i += 1
                #     continue
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
            node = Element(tag, attributes, parent)
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
                node = Element(tag, attributes, parent)
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
                    if text:
                        attrs.append(text)
                    text = ""
                elif c == open_quote:
                    attrs.append(text)
                    text = ""
                    open_quote = None
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

def layout_mode(node):
    if isinstance(node, Text):
        return "inline"
    elif node.children:
        for child in node.children:
            if isinstance(child, Text): continue
            if child.tag in BLOCK_ELEMENTS:
                return "block"
        return "inline"
    elif node.tag == "input":
        return "inline"
    else:
        return "block"


def resolve_url(url, current):
    if "://" in url:
        return url
    elif url.startswith("/"):
        scheme, hostpath = current.split("://", 1)
        host, oldpath = hostpath.split("/", 1)
        return scheme + "://" + host + url
    else:
        scheme, hostpath = current.split("://", 1)
        if "/" not in hostpath:
            current = current + "/"
        dir, _ = current.rsplit("/", 1)
        while url.startswith("../"):
            url = url[3:]
            if dir.count("/") == 2: continue
            dir, _ = dir.rsplit("/", 1)
        return dir + "/" + url

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

class CSSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def literal(self, literal):
        assert self.i < len(self.s) and self.s[self.i] == literal
        self.i += 1

    def word(self):
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        assert self.i > start
        return self.s[start:self.i]

    def pair(self):
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        if prop == "font":
            style = self.word()
            self.whitespace()
            weight = self.word()
            self.whitespace()
            size = self.word()
            self.whitespace()
            family = self.word()
            return "font", (style, weight, size, family)
        val = self.word()
        return prop.lower(), val

    def ignore_until(self, chars):
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1

    def body(self):
        pairs = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                if prop == "font":
                    style, weight, size, family = val
                    pairs["font-family"] = family
                    pairs["font-size"] = size
                    pairs["font-style"] = style
                    pairs["font-weight"] = weight
                else:
                    pairs[prop.lower()] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except AssertionError:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break
        return pairs

    def selector(self):
        word = self.word()
        if word.startswith("."):
            out = ClassSelector(word[1:].lower())
        else:
            out = TagSelector(word.lower())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            if tag[0] == ".":
                descendant = ClassSelector(tag[1:].lower())
            else:
                descendant = TagSelector(tag.lower())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out

    def parse(self):
        rules = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except AssertionError:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules
    
class TagSelector:
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1

    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag

    def __repr__(self):
        return "TagSelector(tag={}, priority={})".format(
            self.tag, self.priority)

class DescendantSelector:
    def __init__(self, ancestor, descendant):
        self.ancestor = ancestor
        self.descendant = descendant
        self.priority = ancestor.priority + descendant.priority
            
    def matches(self, node):
        if not self.descendant.matches(node): return False
        while node.parent:
            if self.ancestor.matches(node.parent): return True
            node = node.parent
        return False

    def __repr__(self):
        return ("DescendantSelector(ancestor={}, descendant={}, priority={})") \
            .format(self.ancestor, self.descendant, self.priority)

class ClassSelector:
    def __init__(self, cls):
        self.cls = cls
        self.priority = 10

    def matches(self, node):
        return self.cls in node.attributes.get("class", "") if isinstance(node, Element) else False

    def __repr__(self):
        return "ClassSelector(html_class={}, priority={})".format(
            self.cls, self.priority)

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
    "font-family": "Times",
}

def compute_style(node, property, value):
    if property == "font-size":
        if value.endswith("px"):
            return value
        elif value.endswith("%"):
            if node.parent:
                parent_font_size = node.parent.style["font-size"]
            else:
                parent_font_size = INHERITED_PROPERTIES["font-size"]
            node_pct = float(value[:-1]) / 100
            parent_px = float(parent_font_size[:-2])
            return str(node_pct * parent_px) + "px"
        else:
            return None
    elif property in ["width", "height"]:
        if value.endswith("px"):
            if value[0] == "-": return "auto"
            return value[:-2] # only return the pixels
        else:
            return value # keyword auto
    else:
        return value

def style(node, rules):
    node.style = {}
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value
    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():
            computed_value = compute_style(node, property, value)
            if not computed_value: continue
            node.style[property] = computed_value
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            computed_value = compute_style(node, property, value)
            node.style[property] = computed_value
    for child in node.children:
        style(child, rules)

def cascade_priority(rule):
    selector, body = rule
    return selector.priority

class BlockLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []

        self.display_list = []

    def layout(self):
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        
        self.width = self.parent.width if self.node.style.get("width", "auto") == "auto" else float(self.node.style.get("width", "auto"))

        mode = layout_mode(self.node)
        if mode == "block":
            previous = None
            for child in self.node.children:
                if isinstance(child, Element) and child.tag == "head":
                    continue
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
        else:
            if isinstance(self.node, Element) and self.node.tag == "li":
                self.x += 2 * HSTEP
                self.width -= 2 * HSTEP
            self.display_list = []

            self.cursor_x = 0
            self.cursor_y = 0
            self.line = []
            self.new_line()
            self.recurse(self.node)

        for child in self.children:
            child.layout()
        
        if self.node.style.get("height", "auto") == "auto":
            self.height = sum([child.height for child in self.children])
        else:
            self.height = float(self.node.style.get("height", "auto"))

    def recurse(self, node):
        if isinstance(node, Text):
            self.text(node)
        else:
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            else:
                for child in node.children:
                    self.recurse(child)
    
    def input(self, node):
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:  
            self.new_line()
        line = self.children[-1]
        input = InputLayout(node, line, self.previous)
        line.children.append(input)
        self.previous = input
        font = self.get_font(node)
        self.cursor_x += w + font.measure(" ")

    def get_font(self, node):
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        return get_font(size, weight, style)

    def text(self, node):
        color = node.style["color"]
        font = self.get_font(node)
        for word in node.text.split():
            w = font.measure(word)
            if self.cursor_x + w > self.width:
                self.new_line()
            # self.line.append((self.cursor_x, word, font))
            line = self.children[-1]
            text = TextLayout(node, word, line, self.previous)
            line.children.append(text)
            self.previous = text
            self.cursor_x += w + font.measure(" ")
    
    def new_line(self):
        self.previous = None
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font, color in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font, color in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font, color))
        self.cursor_x = self.x
        self.line = []
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

    def paint(self, display_list):
        bgcolor = self.node.style.get("background-color",
                                      "transparent")
        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            display_list.append(rect)

        for x, y, word, font, color in self.display_list:
            display_list.append(DrawText(self.x + x, self.y + y,
                                         word, font, color))
        
        is_atomic = not isinstance(self.node, Text) and \
            (self.node.tag == "input" or self.node.tag == "button")
        if not is_atomic:
            if bgcolor != "transparent":
                x2, y2 = self.x + self.width, self.y + self.height
                rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
                display_list.append(rect)

        for child in self.children:
            child.paint(display_list)

    def __repr__(self):
        return "{}Layout(x={}, y={}, width={}, height={})".format(
            layout_mode(self.node).capitalize(), self.x, self.y, self.width, self.height)

class DocumentLayout:
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.previous = None
        self.children = []

    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)

        self.width = WIDTH - 2*HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height + 2*VSTEP

    def paint(self, display_list):
        self.children[0].paint(display_list)

    def __repr__(self):
        return "DocumentLayout()"

class LineLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
    
    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        
        for word in self.children:
            word.layout()
        
        if not self.children:
            self.height = 0
            return

        max_ascent = max([word.font.metrics("ascent")
                  for word in self.children])
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            word.y = baseline - word.font.metrics("ascent")
        max_descent = max([word.font.metrics("descent")
                   for word in self.children])
        self.height = 1.25 * (max_ascent + max_descent)
    
    def paint(self, display_list):
        for child in self.children:
            child.paint(display_list)
    
    def __repr__(self):
        return "LineLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)

class TextLayout:
    def __init__(self, node, word, parent, previous):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous
    
    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style)

        self.width = self.font.measure(self.word)

        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

        self.height = self.font.metrics("linespace")
    
    def paint(self, display_list):
        color = self.node.style["color"]
        display_list.append(DrawText(self.x, self.y, self.word, self.font, color))
    
    def __repr__(self):
        return "TextLayout(x={}, y={}, width={}, height={}, font={})".format(
            self.x, self.y, self.width, self.height, self.font)

class InputLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.children = []
        self.parent = parent
        self.previous = previous
        self.x = None
        self.y = None
        self.width = None
        self.height = None
    
    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style)

        if self.node.attributes.get("type", "") == "checkbox":
            self.width = CHECK_SIZE
            self.height = CHECK_SIZE
        else:
            self.width = INPUT_WIDTH_PX
            self.height = self.font.metrics("linespace")

        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x
    
    def paint(self, display_list):
        bgcolor = self.node.style.get("background-color",
                                      "transparent")
        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            display_list.append(rect)
        if self.node.tag == "input":
            if self.node.attributes.get("type", "") == "checkbox":
                if "checked" in self.node.attributes:
                    text = "x"
                else:
                    text = ""
            else:
                text = self.node.attributes.get("value", "")
            if self.node.attributes.get("type", "") == "hidden":
                self.width = 0.0
                self.height = 0.0
            if self.node.attributes.get("type", "") == "password":
                text = "*" * len(self.node.attributes.get("value", ""))
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and \
               isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                print("Ignoring HTML contents inside button")
                text = ""
        
        color = self.node.style["color"]
        display_list.append(
            DrawText(self.x, self.y, text, self.font, color))
    
    def __repr__(self):
        return "InputLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)
    
class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.color = color

        self.bottom = y1 + font.metrics("linespace")

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw',
            fill=self.color,
        )

    def __repr__(self):
        return "DrawText(top={} left={} bottom={} text={} font={})".format(self.top,
                                    self.left, self.bottom, self.text, self.font)

class DrawRect:
    def __init__(self, x1, y1, x2, y2, color):
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color

    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.left, self.top - scroll,
            self.right, self.bottom - scroll,
            width=0,
            fill=self.color,
        )

    def __repr__(self):
        return "DrawRect(top={} left={} bottom={} right={} color={})".format(
            self.top, self.left, self.bottom, self.right, self.color)

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

class JSContext:
    def __init__(self, tab):
        self.tab = tab
        self.interp = dukpy.JSInterpreter()
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll", self.query_selector_all)
        self.interp.export_function("getAttribute", self.get_attribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("get_children", self.get_children)
        self.interp.export_function("create_element", self.create_element)
        self.interp.export_function("append_child", self.append_child)
        self.interp.export_function("insert_before", self.insert_before)
        self.interp.export_function("XMLHttpRequest_send", self.XMLHttpRequest_send)
        self.interp.export_function("get_cookie", self.get_cookie)
        self.interp.export_function("set_cookie", self.set_cookie)
        self.node_to_handle = {}
        self.handle_to_node = {}

        with open("runtime.js") as f:
            self.interp.evaljs(f.read())

    def run(self, code):
        return self.interp.evaljs(code)
    
    def get_cookie(self):
        _, _, host, _ = self.tab.url.split("/", 3)
        res, params = COOKIE_JAR.get(host, ("", {}))
        if "httponly" in params:
            return ""
        return "{}".format(res)

    def set_cookie(self, s):
        _, _, host, _ = self.tab.url.split("/", 3)
        old_res, old_params = COOKIE_JAR.get(host, ("", {}))
        if "httponly" in old_params:
            return
        
        params = {}
        if ";" in s:
            s, rest = s.split(";", 1)
            for param_pair in rest.split(";"):
                if "=" in param_pair:
                    name, value = param_pair.strip().split("=", 1)
                else:
                    name = param_pair.strip()
                    value = ""
                params[name.lower()] = value.lower()
        COOKIE_JAR[host] = (s, params)
    
    def get_children(self, handle):
        node = self.handle_to_node[handle]
        children = [elt for elt in node.children if isinstance(elt, Element)]
        return [self.get_handle(child) for child in children]
    
    def create_element(self, tag):
        elt = Element(tag, {}, None)
        return self.get_handle(elt)
    
    def append_child(self, parent_header, child_header):
        parent = self.handle_to_node[parent_header]
        child = self.handle_to_node[child_header]
        child.parent = parent
        parent.children.append(child)
        self.tab.render()
    
    def insert_before(self, parent_handle, new_handle, ref_handle):
        parent = self.handle_to_node[parent_handle]
        new_node = self.handle_to_node[new_handle]
        ref_node = self.handle_to_node[ref_handle]
        ref_index = parent.children.index(ref_node)
        parent.children.insert(ref_index, new_node)
        new_node.parent = parent
    
    def query_selector_all(self, selector_text):
        selector = CSSParser(selector_text).selector()
        nodes = [node for node in tree_to_list(self.tab.nodes, [])
                    if selector.matches(node)]
        return [self.get_handle(node) for node in nodes]
    
    def get_handle(self, node):
        if node in self.node_to_handle:
            return self.node_to_handle[node]
        handle = len(self.node_to_handle)
        self.node_to_handle[node] = handle
        self.handle_to_node[handle] = node
        return handle

    def get_attribute(self, handle, attr):
        node = self.handle_to_node[handle]
        return node.attributes.get(attr, None)
    
    def dispatch_event(self, type, elt):
        handle = self.node_to_handle.get(elt, -1)
        do_default, stop_propagation = self.interp.evaljs(EVENT_DISPATCH_CODE, type=type, handle=handle)
        if not stop_propagation and elt.parent:
            self.dispatch_event(type, elt.parent)
        return not do_default
    
    def innerHTML_set(self, handle, s):
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        for old_node in elt.children:
            for node in tree_to_list(old_node, []):
                if isinstance(node, Element) and "id" in node.attributes:
                    self.run("delete {}".format(node.attributes["id"]))

        elt.children = new_nodes
        for old_node in elt.children:
            for node in tree_to_list(old_node, []):
                if isinstance(node, Element) and "id" in node.attributes:
                    self.run("{} = new Node({})".format(node.attributes["id"], self.get_handle(node)))

        for child in elt.children:
            child.parent = elt
        self.tab.render()
    
    def XMLHttpRequest_send(self, method, url, body):
        full_url = resolve_url(url, self.tab.url)
        if not self.tab.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
        if url_origin(full_url) != url_origin(self.tab.url):
            raise Exception("Cross-origin XHR request not allowed")
        headers, out, _ = request(full_url, self.tab.url, body)
        return out

def url_origin(url):
    scheme_colon, _, host, _ = url.split("/", 3)
    return scheme_colon + "//" + host

class Tab:
    def __init__(self, browser):
        with open("browser.css") as f:
            self.default_style_sheet = CSSParser(f.read()).parse()
        self.history = []
        self.active_tab = None
        self.browser = browser
        self.focus = None
        self.url = None
        self.referrer_policy = None
    
    def load(self, url, body=None):
        frag = url
        if "#" in url:
            frag, frag2 = url.split("#", 1)
        
        headers, body, secured = request(frag, self.url, body, referrer_policy=self.referrer_policy)
        self.secured = secured
        self.scroll = 0
        self.url = url
        self.history.append(url)
        self.nodes = HTMLParser(body).parse()
        self.rules = self.default_style_sheet.copy()

        if "referrer-policy" in headers:
            self.referrer_policy = headers["referrer-policy"]
        else:
            self.referrer_policy = None

        self.allowed_origins = None
        if "content-security-policy" in headers:
            csp = headers["content-security-policy"].split()
            if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = csp[1:]
        
        links = [node.attributes["href"]
                 for node in tree_to_list(self.nodes, [])
                 if isinstance(node, Element)
                 and node.tag == "link"
                 and "href" in node.attributes
                 and node.attributes.get("rel") == "stylesheet"]

        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        self.js = JSContext(self)
        for script in scripts:
            script_url = resolve_url(script, url)
            if not self.allowed_request(script_url):
                print("Blocked script", script, "due to CSP")
                continue
            header, body, _ = request(script_url, url, referrer_policy=self.referrer_policy)
            try:
                self.js.run(body)
            except dukpy.JSRuntimeError as e:
                print("Script", script, "crashed", e)
        
        for link in links:
            style_url = resolve_url(link, url)
            if not self.allowed_request(style_url):
                print("Blocked style", link, "due to CSP")
                continue
            try:
                header, body, _ = request(style_url, url, referrer_policy=self.referrer_policy)
            except:
                continue
            self.rules.extend(CSSParser(body).parse())

        for node in tree_to_list(self.nodes, []):
            if isinstance(node, Element) and "id" in node.attributes:
                self.js.run("{} = new Node({})".format(node.attributes["id"], self.js.get_handle(node)))

        if "#" in url:
            node_list = []
            tree_to_list(self.document, node_list)
            for node in node_list:
                if isinstance(node, BlockLayout) and isinstance(node.node, Element) \
                        and node.node.attributes.get("id") == frag2:
                    self.scroll = node.y
                    break
        self.render()
    
    def allowed_request(self, url):
        return self.allowed_origins == None or \
            url_origin(url) in self.allowed_origins
    
    def render(self):
        style(self.nodes, sorted(self.rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        self.document.paint(self.display_list)
    
    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def draw(self, canvas):
        canvas.delete("all")
        for cmd in self.display_list:
            if cmd.top > self.scroll + HEIGHT - CHROME_PX: continue
            if cmd.bottom < self.scroll: continue
            cmd.execute(self.scroll - CHROME_PX, canvas)
        
        if (self.document.height >= HEIGHT):
            x1 = WIDTH - 8
            x2 = WIDTH
            doc_height = self.document.height
            screen_height = HEIGHT

            scroll_height = screen_height * screen_height / doc_height

            y1 = self.scroll * screen_height / doc_height
            y2 = y1 + scroll_height
            color = "blue"

            scroll_bar = DrawRect(x1, y1, x2, y2, color)
            scroll_bar.execute(0, canvas)
        
        if self.focus:
            obj = [obj for obj in tree_to_list(self.document, [])
                   if obj.node == self.focus and \
                        isinstance(obj, InputLayout)][0]
            text = self.focus.attributes.get("value", "")
            x = obj.x + obj.font.measure(text)
            y = obj.y - self.scroll + CHROME_PX
            canvas.create_line(x, y, x, y + obj.height)
    
    def submit_form(self, elt):
        if self.js.dispatch_event("submit", elt): return
        inputs = [node for node in tree_to_list(elt, [])
                  if isinstance(node, Element)
                  and node.tag == "input"
                  and "name" in node.attributes]
        body = ""
        for input in inputs:
            name = input.attributes["name"]
            if input.attributes.get("type", "") == "checkbox":
                if "checked" not in input.attributes:
                    continue
                else:
                    value = input.attributes.get("value", "on")
            else:
                value = input.attributes.get("value", "")
            name = urllib.parse.quote(name)
            value = urllib.parse.quote(value)
            body += "&" + name + "=" + value
        body = body[1:]

        url = resolve_url(elt.attributes["action"], self.url)
        if elt.attributes.get("method", "GET") == "POST":
            self.load(url, body)
        else:
            self.load(url + "?" + body)

    def scrolldown(self):
        max_y = self.document.height - (HEIGHT - CHROME_PX)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)

    def scrollup(self):
        self.scroll -= SCROLL_STEP
        if self.scroll < 0:
            self.scroll = 0
    
    def scrolling(self, ev):
        if ev.delta > 0:
            self.scrollup()
        else:
            self.scrolldown()
    
    def keypress(self, char):
        if self.focus:
            if self.js.dispatch_event("keydown", self.focus): return
            self.focus.attributes["value"] += char
            self.render()
    
    def enter(self):
        if self.focus and self.focus.tag == "input":
            curr = self.focus.parent
            while curr:
                if curr.tag == "form" and "action" in curr.attributes:
                    return self.submit_form(curr)
                curr = curr.parent

    def tab(self):
        if self.focus and self.focus.tag == "input":
            curr = self.focus.parent
            while curr:
                if curr.tag == "form":
                    break
                curr = curr.parent
            
            child_list = tree_to_list(curr, [])
            input_list = [node for node in child_list if isinstance(node, Element)
                            and node.tag == "input"]
            index = input_list.index(self.focus)
            next_index = (index + 1) % len(input_list)
            self.focus = input_list[next_index]
            self.focus.attributes["value"] = ""
            self.render()

    def click(self, x, y, button=1):
        x, y = x, y + self.scroll

        objs = [obj for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                and obj.y <= y < obj.y + obj.height]

        if not objs: return
        elt = objs[-1].node

        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "input":
                if self.js.dispatch_event("click", elt): return
                if elt.attributes.get("type", "") == "checkbox":
                    if "checked" in elt.attributes:
                        del elt.attributes["checked"]
                    else:
                        elt.attributes["checked"] = ""
                else:
                    self.focus = elt
                    elt.attributes["value"] = ""
                return self.render()
            elif elt.tag == "button":
                if self.js.dispatch_event("click", elt): return
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
                    elt = elt.parent
            elif elt.tag == "a" and "href" in elt.attributes:
                if self.js.dispatch_event("click", elt): return
                if elt.attributes["href"][0] == "#":
                    node_list = []
                    tree_to_list(self.document, node_list)
                    for node in node_list:
                        if isinstance(node, BlockLayout) and isinstance(node.node, Element) \
                                and node.node.attributes.get("id") == elt.attributes["href"][1:]:
                            self.scroll = node.y
                            break
                    
                    frag = self.url
                    if "#" in self.url:
                        frag, frag2 = self.url.split("#", 1)
                    self.url = frag + elt.attributes["href"]
                    return
                
                url = resolve_url(elt.attributes["href"], self.url)
                if button == 1:
                    return self.load(url)
                else:
                    return self.browser.load(url, activate=False)
            elt = elt.parent
    
    def __repr__(self) -> str:
        return "Tab(history={})".format(self.history)

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
            bg="white",
        )
        self.canvas.pack()

        self.scroll = 0
        self.window.bind("<Down>", self.handle_down)
        self.window.bind("<Up>", self.handle_up)
        self.window.bind("<MouseWheel>", self.handle_scroll)
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Button-2>", self.handle_middle_click)
        self.window.bind("<Key>", self.handle_key)
        self.window.bind("<Return>", self.handle_enter)
        self.window.bind("<BackSpace>", self.handle_backspace)
        self.window.bind("<Tab>", self.handle_tab)
        self.tabs = []
        self.active_tab = None
        self.focus = None
        self.address_bar = ""
    
    def load(self, url, activate=True):
        new_tab = Tab(self)
        new_tab.load(url)
        if activate:
            self.active_tab = len(self.tabs)
        self.tabs.append(new_tab)
        self.draw()
    
    def draw(self):
        self.canvas.delete("all")
        self.tabs[self.active_tab].draw(self.canvas)
        self.canvas.create_rectangle(0, 0, WIDTH, CHROME_PX,
            fill="white", outline="black")
        tabfont = get_font(20, "normal", "roman")
        for i, tab in enumerate(self.tabs):
            name = "Tab {}".format(i)
            x1, x2 = 40 + 80 * i, 120 + 80 * i
            self.canvas.create_line(x1, 0, x1, 40, fill="black")
            self.canvas.create_line(x2, 0, x2, 40, fill="black")
            self.canvas.create_text(x1 + 10, 10, anchor="nw", text=name,
                font=tabfont, fill="black")
            if i == self.active_tab:
                self.canvas.create_line(0, 40, x1, 40, fill="black")
                self.canvas.create_line(x2, 40, WIDTH, 40, fill="black")
        
        buttonfont = get_font(30, "normal", "roman")
        self.canvas.create_rectangle(10, 10, 30, 30,
            outline="black", width=1)
        self.canvas.create_text(11, 0, anchor="nw", text="+",
            font=buttonfont, fill="black")
        
        self.canvas.create_rectangle(10, 50, 35, 90,
            outline="black", width=1)
        self.canvas.create_polygon(
            15, 70, 30, 55, 30, 85, fill='black')
        
        
        if self.tabs[self.active_tab].url in BOOKMARKS:
            color = "yellow"
        else:
            color = "white"
        self.canvas.create_rectangle(WIDTH - 35, 50, WIDTH - 10, 90,
            outline="black", fill=color, width=1)

        self.canvas.create_rectangle(40, 50, WIDTH - 40, 90,
            outline="black", width=1)
        if self.focus == "address bar":
            self.canvas.create_text(
                55, 55, anchor='nw', text=self.address_bar,
                font=buttonfont, fill="black")
            w = buttonfont.measure(self.address_bar)
            self.canvas.create_line(55 + w, 55, 55 + w, 85, fill="black")
        else:
            url = self.tabs[self.active_tab].url
            if self.tabs[self.active_tab].secured:
                address_bar = "\N{LOCK} " + url
            else:
                address_bar = url
            self.canvas.create_text(55, 55, anchor='nw', text=address_bar,
                font=buttonfont, fill="black")
        
    def keypress(self, char):
        if self.focus:
            self.focus.attributes["value"] += char
            self.render()

    def handle_down(self, e):
        self.tabs[self.active_tab].scrolldown()
        self.draw()
    
    def handle_up(self, e):
        self.tabs[self.active_tab].scrollup()
        self.draw()
    
    def handle_scroll(self, e):
        self.tabs[self.active_tab].scrolling(e)
        self.draw()
    
    def handle_key(self, e):
        if len(e.char) == 0: return
        if not (0x20 <= ord(e.char) < 0x7f): return

        if self.focus == "address bar":
            self.address_bar += e.char
            self.draw()
        elif self.focus == "content":
            self.tabs[self.active_tab].keypress(e.char)
            self.draw()
        
    def handle_enter(self, e):
        if self.focus == "address bar":
            self.tabs[self.active_tab].load(self.address_bar)
            self.focus = None
            self.draw()
        elif self.focus == "content":
            self.tabs[self.active_tab].enter()

    def handle_click(self, e):
        if e.y < CHROME_PX:
            self.focus = None
            if 40 <= e.x < 40 + 80 * len(self.tabs) and 0 <= e.y < 40:
                self.active_tab = int((e.x - 40) / 80)
            elif 10 <= e.x < 30 and 10 <= e.y < 30:
                self.load("https://browser.engineering/")
            elif 10 <= e.x < 35 and 50 <= e.y < 90:
                self.tabs[self.active_tab].go_back()
            elif 50 <= e.x < WIDTH - 40 and 50 <= e.y < 90:
                self.focus = "address bar"
                self.address_bar = ""
            elif WIDTH - 35 <= e.x < WIDTH - 10 and 50 <= e.y < 90:
                url = self.tabs[self.active_tab].url
                if url not in BOOKMARKS:
                    BOOKMARKS.append(url)
                else:
                    BOOKMARKS.remove(url)
            self.draw()
        else:
            self.focus = "content"
            self.tabs[self.active_tab].click(e.x, e.y - CHROME_PX)
    
    def handle_backspace(self, e):
        if self.focus == "address bar":
            self.address_bar = self.address_bar[:-1]
        self.draw()
    
    def handle_tab(self, e):
        if self.focus == "content":
            self.tabs[self.active_tab].tab()

    def handle_middle_click(self, e):
        if e.y >= CHROME_PX:
            self.tabs[self.active_tab].click(e.x, e.y - CHROME_PX, button=2)

def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

if __name__ == "__main__":
    import sys
    Browser().load(sys.argv[1])
    tkinter.mainloop()