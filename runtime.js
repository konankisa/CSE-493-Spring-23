LISTENERS = {}

console = {
    log: function(x) {
        call_python('log', x);
    }
}

document = {
    querySelectorAll: function(s) {
        var handles = call_python('querySelectorAll', s);
        return handleNodes(handles)
    },
    createElement: function(tag) {
        var handle = call_python("create_element", tag)
        return new Node(handle)
    }
}

function handleNodes(handles) {
    return handles.map(function(h) {
        return new Node(h);
    });
}

Object.defineProperty(Node.prototype, 'innerHTML', {
    set: function(s) {
        call_python("innerHTML_set", this.handle, s.toString());
    }
});

Object.defineProperty(Node.prototype, 'children', {
    get: function() {
        return handleNodes(call_python("get_children", this.handle));
    }
});

function Event(type) {
    this.type = type
    this.do_default = true;
    this.stop_propagation = false;
}

Event.prototype.preventDefault = function() {
    this.do_default = false;
}

Event.prototype.stopPropagation = function() {
    this.stop_propagation = true;
}

function Node(handle) {
    this.handle = handle;
}

Node.prototype.getAttribute = function(attr) {
    return call_python('getAttribute', this.handle, attr);
}

Node.prototype.addEventListener = function(type, listener) {
    if (!LISTENERS[this.handle]) LISTENERS[this.handle] = {};
    var dict = LISTENERS[this.handle];
    if (!dict[type]) dict[type] = [];
    var list = dict[type];
    list.push(listener);
}

Node.prototype.dispatchEvent = function(type) {
    var handle = this.handle;
    var list = (LISTENERS[handle] && LISTENERS[handle][type]) || [];
    for (var i = 0; i < list.length; i++) {
        list[i].call(this);
    }
}

Node.prototype.dispatchEvent = function(evt) {
    var type = evt.type;
    var handle = this.handle;
    var list = (LISTENERS[handle] && LISTENERS[handle][type]) || [];
    for (var i = 0; i < list.length; i++) {
        list[i].call(this, evt);
    }
    return [evt.do_default, evt.stop_propagation];
}

Node.prototype.appendChild = function(child) {
    call_python("append_child", this.handle, child.handle)
    return child
}

Node.prototype.insertBefore = function(newNode, refNode) {
    if (refNode === null) {
        call_python("append_child", this.handle, newNode.handle)
        return newNode
    }
    call_python("insert_before", this.handle, newNode.handle, refNode.handle)
    return newNode
}

inputs = document.querySelectorAll('input')
for (var i = 0; i < inputs.length; i++) {
    var name = inputs[i].getAttribute("name");
    var value = inputs[i].getAttribute("value");
    if (value.length > 100) {
        console.log("Input " + name + " has too much text.")
    }
}

function lengthCheck() {
    var name = this.getAttribute("name");
    var value = this.getAttribute("value");
    if (value.length > 100) {
        console.log("Input " + name + " has too much text.")
    }
}

var inputs = document.querySelectorAll("input");
for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("keydown", lengthCheck);
}

