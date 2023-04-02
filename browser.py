import socket
import ssl
import time
import sys

cached_urls = {}

def request(url, headers=None, redirects=0):
    # if too many redirects, raise an exception
    init_url = url
    if redirects > 8:
        raise Exception("Too many redirects")
    # if url is in cache, return the cached value
    if init_url in cached_urls:
        return cached_urls[init_url]

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
        headers = {"user-agent": "Chrome/112.0.5615.45"}
    else:
        map(str.lower, headers.keys())
    
    # create request string and update headers within it
    req = "GET {} HTTP/1.1\r\n".format(path).encode("utf8") + \
        "Host: {}\r\n".format(host).encode("utf8") + \
        "Connection: close\r\n".encode("utf8")
    for header, value in headers.items():
        req += "{}: {}\r\n".format(header, value).encode("utf8")

    s.send(req)
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
            cached_urls[init_url] = (cur_headers, body)
            max_age = int(cur_headers["cache-control"].split("=", 1)[1])
            # if max_age > 0:
            #     time.sleep(max_age)
            #     del cached_urls[init_url]
    return cur_headers, body

def show(body):
    # print body without tags
    tag = False
    for t in body:
        if t == "<":
            tag = True
        elif t == ">":
            tag = False
        elif not tag:
            print(t, end="")

def load(url):
    # load url and print body
    headers, body = request(url)
    show(body)

if __name__ == "__main__":
    load(sys.argv[1])