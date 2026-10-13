const paths = {
  pokemon: ["Pokémon", "pokemon/default"],
  variant: ["Variants", "pokemon/variant"],
  transformation: ["Transformations", "pokemon/transformation"],
  cosmetic: ["Cosmetic forms", "pokemon/cosmetic"],
  ability: ["Abilities", "ability"],
  move: ["Moves", "move"],
  item: ["Items", "item"],
};
const ui = Object.fromEntries(
  ["generation", "resource", "filter", "status", "error", "results", "pagination", "previous", "next", "page", "endpoint", "example", "json"].map(
    (id) => [id, document.getElementById(id)],
  ),
);
let index;
let rows = [];
const pageSize = 50;
let page = 1;
let catalogRequest;
let recordRequest;

async function loadJSON(path, signal) {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error(`Request failed (${response.status}): ${path}`);
  return response.json();
}

function showError(error) {
  if (error.name === "AbortError") return;
  ui.error.textContent = error.message;
  ui.error.hidden = false;
}

function clearPreview() {
  recordRequest?.abort();
  ui.endpoint.hidden = true;
  ui.example.textContent = "Select a resource to see a fetch example.";
  ui.json.textContent = "No resource selected.";
}

async function preview(record, button) {
  clearPreview();
  ui.error.hidden = true;
  recordRequest = new AbortController();
  const path = `gen${ui.generation.value}/${paths[ui.resource.value][1]}/${encodeURIComponent(record.name)}.json`;
  const url = new URL(path, document.baseURI).href;
  ui.endpoint.href = url;
  ui.endpoint.textContent = path;
  ui.endpoint.hidden = false;
  ui.example.textContent = `const response = await fetch(${JSON.stringify(url)});\nif (!response.ok) throw new Error(response.status);\nconst data = await response.json();`;
  ui.json.textContent = "Loading…";
  for (const item of ui.results.children) item.setAttribute("aria-pressed", String(item === button));
  try {
    const data = await loadJSON(path, recordRequest.signal);
    ui.json.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    if (error.name !== "AbortError") ui.json.textContent = "Could not load this resource. Select it again to retry.";
    showError(error);
  }
}

function render() {
  clearPreview();
  const term = ui.filter.value.trim().toLowerCase();
  const filtered = rows.filter((row) => row.name.toLowerCase().includes(term) || String(row.id) === term);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  page = Math.min(page, pages);
  const start = (page - 1) * pageSize;
  ui.results.replaceChildren();
  for (const record of filtered.slice(start, start + pageSize)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = record.name;
    button.setAttribute("aria-pressed", "false");
    const id = document.createElement("span");
    id.textContent = `#${record.id}`;
    button.append(id);
    button.addEventListener("click", () => preview(record, button));
    ui.results.append(button);
  }
  ui.results.scrollTop = 0;
  ui.pagination.hidden = filtered.length === 0;
  ui.previous.disabled = page === 1;
  ui.next.disabled = page === pages;
  ui.page.textContent = `Page ${page} of ${pages.toLocaleString()}`;
  ui.status.textContent = filtered.length
    ? `Showing ${(start + 1).toLocaleString()}–${Math.min(start + pageSize, filtered.length).toLocaleString()} of ${filtered.length.toLocaleString()} matching records · Schema ${index.metadata.schema_version}`
    : `No matching records · Schema ${index.metadata.schema_version}`;
}

function selectResource() {
  ui.error.hidden = true;
  rows = index[ui.resource.value] ?? [];
  page = 1;
  render();
}

async function selectGeneration() {
  catalogRequest?.abort();
  catalogRequest = new AbortController();
  clearPreview();
  ui.error.hidden = true;
  ui.resource.disabled = true;
  ui.filter.disabled = true;
  ui.results.replaceChildren();
  ui.pagination.hidden = true;
  ui.status.textContent = "Loading generation index…";
  const selected = ui.resource.value;
  try {
    index = await loadJSON(`gen${ui.generation.value}/index.json`, catalogRequest.signal);
    ui.resource.replaceChildren();
    for (const [key, [label]] of Object.entries(paths)) {
      if (!Array.isArray(index[key])) continue;
      ui.resource.add(new Option(`${label} (${index[key].length.toLocaleString()})`, key));
    }
    if (Object.hasOwn(paths, selected) && Array.isArray(index[selected])) ui.resource.value = selected;
    ui.resource.disabled = false;
    ui.filter.disabled = false;
    selectResource();
  } catch (error) {
    if (error.name !== "AbortError") ui.status.textContent = "Generation unavailable. Choose another generation or reload to retry.";
    showError(error);
  }
}

ui.generation.addEventListener("change", selectGeneration);
ui.resource.addEventListener("change", selectResource);
ui.filter.addEventListener("input", () => { page = 1; render(); });
function changePage(offset) {
  page += offset;
  render();
  if (document.activeElement.disabled) ui.results.querySelector("button")?.focus();
}
ui.previous.addEventListener("click", () => changePage(-1));
ui.next.addEventListener("click", () => changePage(1));

try {
  const catalog = await loadJSON("catalog.json");
  for (const entry of catalog.generations) {
    ui.generation.add(new Option(`Generation ${entry.generation}`, entry.generation));
  }
  ui.generation.value = String(catalog.generations.at(-1).generation);
  ui.generation.disabled = false;
  await selectGeneration();
} catch (error) {
  ui.status.textContent = "Catalogs unavailable. Use the direct links below or reload to retry.";
  showError(error);
}
