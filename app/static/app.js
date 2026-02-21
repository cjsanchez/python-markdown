const mdInput = document.getElementById("mdInput");
const preview = document.getElementById("preview");
const btnClear = document.getElementById("btnClear");
const btnServer = document.getElementById("btnServer");
const modeLabel = document.getElementById("modeLabel");

function renderClientSide() {
  // marked parses markdown -> HTML in the browser
  // NOTE: This demo does not sanitize HTML. For untrusted input, sanitize.
  preview.innerHTML = marked.parse(mdInput.value || "");
  modeLabel.textContent = "Mode: client-side";
}

async function renderServerSide() {
  const form = new FormData();
  form.append("markdown_text", mdInput.value || "");

  const res = await fetch("/render", { method: "POST", body: form });
  if (!res.ok) {
    preview.innerHTML = `<p>Server render failed (${res.status}).</p>`;
    return;
  }
  const data = await res.json();
  preview.innerHTML = data.html;
  modeLabel.textContent = "Mode: server-side";
}

mdInput.addEventListener("input", renderClientSide);

btnClear.addEventListener("click", () => {
  mdInput.value = "";
  renderClientSide();
});

btnServer.addEventListener("click", () => {
  renderServerSide();
});

// initial render
renderClientSide();