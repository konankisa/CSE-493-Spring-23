from dataclasses import dataclass
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

class Text:
    text: str

    def __init__(self, text): 
        self.text = text
    
    def __str__(self) -> str:
        return "Text({})".format(self.text)

@dataclass
class Tag:
    tag: str

Token = Union[Text, Tag]

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

def layout(tokens: List[Token]):
    display_list = []
    bold = False
    cur_x, cur_y = HSTEP, VSTEP
    for token in tokens:
        if isinstance(token, Text):
            font: tkinter.font.Font = tkinter.font.Font(
                family="Times",
                size=16,
                weight="bold" if bold else "normal",
                slant="italic",
            )
            text = token.text
            for word in text.split(" "):
                w = font.measure(word + " ")
                if cur_x >= WIDTH - HSTEP:
                    cur_y += font.metrics("linespace") * 1.25
                    cur_x = HSTEP
                display_list.append((cur_x, cur_y, word))
                cur_x += w
        else:
            assert isinstance(token, Tag)
            tag = token
            if tag.tag == "b":
                bold = True
            elif tag.tag == "/b":
                bold = False
    return display_list

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.bi_times = tkinter.font.Font(
            family="Times",
            size=16,
            weight="bold",
            slant="italic",
        )
        self.canvas.pack(fill="both", expand=True)
        self.scroll = 0
        self.font_size = 16
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
        self.display_list = layout(self.text)
        self.draw()
    
    def zoomout(self, ev):
        global VSTEP, HSTEP
        VSTEP //= 2
        HSTEP //= 2
        self.font_size //= 2
        self.display_list = layout(self.text)
        self.draw()
    
    def resize(self, ev):
        global WIDTH, HEIGHT
        WIDTH = ev.width
        HEIGHT = ev.height
        self.display_list = layout(self.text)
        self.draw()
    
    def draw(self):
        self.canvas.delete("all")
        for x, y, c in self.display_list:
            if y > self.scroll + HEIGHT: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c, font=self.bi_times, anchor="nw")

    def load(self, url):
        # load url and print body
        headers, body = request(url)
        self.text = lex(body)
        self.display_list = layout(self.text)
        self.draw()

if __name__ == "__main__":
    import sys
    Browser().load(sys.argv[1])
    tkinter.mainloop()