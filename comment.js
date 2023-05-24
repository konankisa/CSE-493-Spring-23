var label = document.querySelectorAll("label")[0];

function lengthCheck() {
    var value = this.getAttribute("value");
    if (value.length > 100) {
        label.innerHTML = "Comment too long!";
    }
}

var inputs = document.querySelectorAll("input");
for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("keydown", lengthCheck);
}

var allow_submit = true;

function lengthCheck() {
    var value = this.getAttribute("value");
    allow_submit = value.length <= 100;
    if (!allow_submit) {
        label.innerHTML = "Comment too long!";
    } else {
        label.innerHTML = "";
    }
}

var form = document.querySelectorAll("form")[0];
form.addEventListener("submit", function(e) {
    if (!allow_submit) e.preventDefault();
});