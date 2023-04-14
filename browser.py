from dataclasses import dataclass
import re
import socket
import ssl
import time
import tkinter
import tkinter.font
from typing import List, Union

cached_urls = {}
WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
FONTS = {}

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

@dataclass
class Text:
    text: str
    
    def __repr__(self) -> str:
        return "Text('{}')".format(self.text)

@dataclass
class Tag:
    tag: str
    
    def __repr__(self) -> str:
        return "Tag('{}')".format(self.tag)

Token = Union[Text, Tag]

class Layout:
    def __init__(self, tokens):
        self.display_list = []
        self.line = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight = "normal"
        self.style = "roman"
        self.centered = False
        self.superscript = False
        self.small_cap = False
        self.size = 16
        for token in tokens:
            self.token(token)
        self.flush()
    
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
            self.display_list.append((x + shift, y, text, font))
        
        self.cursor_x = HSTEP
        self.line = []
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

    def token(self, tok):
        if isinstance(tok, Text):
            self.text(tok)
        else:
            assert isinstance(tok, Tag)
            if tok.tag == "i":
                self.style = "italic"
            elif tok.tag == "/i":
                self.style = "roman"
            elif tok.tag == "b":
                self.weight = "bold"
            elif tok.tag == "/b":
                self.weight = "normal"
            elif tok.tag == "small":
                self.size -= 2
            elif tok.tag == "/small":
                self.size += 2
            elif tok.tag == "big":
                self.size += 4
            elif tok.tag == "/big":
                self.size -= 4
            elif tok.tag == "br":
                self.flush()
            elif tok.tag == "/p":
                self.flush()
                self.cursor_y += VSTEP
            elif tok.tag.startswith("h1"):
                self.flush()
                self.centered = True
            elif tok.tag.startswith("/h1"):
                self.flush()
                self.centered = False
            elif tok.tag.startswith("sup"):
                self.superscript = True
            elif tok.tag.startswith("/sup"):
                self.superscript = False
            elif tok.tag.startswith("abbr"):
                self.small_cap = True
            elif tok.tag.startswith("/abbr"):
                self.small_cap = False
    
    def text(self, token):
        if self.superscript:
            size = self.size // 2
        else:
            size = self.size
        font = get_font(size, self.weight, self.style)
        text = token.text
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

                    if self.cursor_x + w > WIDTH - HSTEP:
                        self.cursor_y += font.metrics("linespace") * 1.25
                        self.cursor_x = HSTEP
                        self.flush()
                    self.cursor_x += w
                if word.split():
                    self.cursor_x += font.measure(" ")
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
                tokens.append(Text(text))
                text = ""
            tag = True
        elif t == ">":
            tokens.append(Tag(text))
            text = ""
            tag = False
        else:
            text += t
    if not tag and text:
        tokens.append(Text(text))
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
        layout = Layout(self.tokens)
        self.display_list = layout.display_list
        self.draw()
    
    def zoomout(self, ev):
        global VSTEP, HSTEP
        VSTEP //= 2
        HSTEP //= 2
        self.font_size //= 2
        self.display_list = Layout(self.tokens).display_list
        self.draw()
    
    def resize(self, ev):
        global WIDTH, HEIGHT
        WIDTH = ev.width
        HEIGHT = ev.height
        self.display_list = Layout(self.tokens).display_list
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
        self.tokens = lex(body)
        self.display_list = Layout(self.tokens).display_list
        self.draw()

if __name__ == "__main__":
    import sys
    Browser().load(sys.argv[1])
    tkinter.mainloop()