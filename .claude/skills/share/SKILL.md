---
name: share
description: Creates and updates shareable static HTML mini-sites from project documentation. Works from file:// — all content is inlined, no server needed. Invoke when creating a new share or updating an existing one. Say "create a share" or "update the share at docs/shares/<name>".
---

## Role

You are a documentation publisher. You read local project files and produce shareable static HTML mini-sites that work from `file://` — no server, no build step. All markdown content is inlined as escaped JS strings and rendered client-side via marked.js and mermaid.js (loaded from CDN; requires internet to render).

A **share** is a named folder under `docs/shares/<name>/` containing an `index.html` hub page, a `.shareconfig.json`, and any generated subpages. A project can have multiple independent shares.

---

## Operating Modes

Detect the mode before doing anything else:

1. Read `docs/shares/` to see what shares exist.
2. If the user named a share and `docs/shares/<name>/.shareconfig.json` exists → **Update mode**.
3. If no config found → **First Run mode**.
4. If the user did not specify a name, list existing shares and ask which to update, or ask for a name if starting fresh.

---

## First Run: Interview

Conduct a natural conversation — not a form. Cover these points:

**1. Share name**
What should this share be called? Becomes `docs/shares/<name>/`. Use kebab-case.

**2. Purpose and audience**
What is this for? Who will read it? Sets the tone, design density, and navigation style.

**3. Sections**
For each section the user describes, establish:

| Field | Values |
|---|---|
| `type` | `inline` — content rendered directly on hub page |
| | `generated` — source .md files → subpages linked from hub |
| | `passthrough` — existing HTML/folder elsewhere in repo, hub links to it, you touch nothing |
| `sources` | Glob or list of paths relative to repo root (for `inline` and `generated`) |
| `path` | Path relative to share folder (for `passthrough`) |
| `layout` | `hero`, `prose`, `table`, `accordion`, `cards`, `custom` |
| `label` | Display label in navigation |

**4. Theme**
Light or dark? Any color or brand preferences?

After the interview, summarize the planned structure and get confirmation before writing anything.

---

## Config Schema

Write `docs/shares/<name>/.shareconfig.json`:

```json
{
  "name": "<share-name>",
  "created": "YYYY-MM-DD",
  "updated": "YYYY-MM-DD",
  "theme": "light",
  "hub": {
    "title": "Display title for the hub page",
    "description": "One-line subtitle shown in the hub header"
  },
  "sections": [
    {
      "id": "unique-id",
      "label": "Display label",
      "type": "inline",
      "layout": "hero",
      "sources": ["README.md"]
    },
    {
      "id": "tech-docs",
      "label": "Technical Docs",
      "type": "generated",
      "layout": "prose",
      "sources": ["docs/system/*.md"],
      "subdir": "tech-docs"
    },
    {
      "id": "design",
      "label": "UI Design",
      "type": "passthrough",
      "path": "../../design/ui/index.html"
    }
  ]
}
```

**Path conventions:**
- `sources` paths are relative to the **repo root** (directory containing `.git`).
- `path` (passthrough) is relative to the **share folder** so the `href` works from `file://`.
- `subdir` (generated) is the subfolder under the share folder where subpages are written.

---

## HTML Generation

### Hub page — `docs/shares/<name>/index.html`

Skeleton:

```html
<!--
SHARE CONFIG
  name:    <name>
  config:  .shareconfig.json
  updated: YYYY-MM-DD

SECTIONS
  <id> | inline    | <layout> | sources: <paths>
  <id> | generated | <layout> | subdir: <subdir> | sources: <paths>
  <id> | passthrough |         | path: <path>

To update this share in a new session:
  "update the share at docs/shares/<name>"
  Claude will read .shareconfig.json, or fall back to these comments.
-->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{hub.title}}</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <style>
    /* Theme, nav, section, and layout styles here.
       Design to match the share's purpose and theme preference. */
  </style>
</head>
<body>
  <header>
    <h1>{{hub.title}}</h1>
    <p>{{hub.description}}</p>
  </header>
  <nav>
    <!-- One link per generated section (→ subdir/index.html or single subpage)
         One link per passthrough section (→ path directly)
         Inline sections are not listed in nav — they are the body content -->
  </nav>
  <main id="content">
    <!-- Inline section placeholders, filled by the script below -->
  </main>
  <script>
    mermaid.initialize({ startOnLoad: false, theme: '{{mermaid-theme}}' });

    const SECTIONS = {
      // Each inline section's markdown content, escaped for JS template literals.
      // Escape backticks as \` and ${ as \${
      "hero": `...markdown content from source file(s)...`,
      "summary": `...markdown content...`
    };

    async function render() {
      for (const [id, md] of Object.entries(SECTIONS)) {
        const el = document.getElementById('section-' + id);
        if (el) el.innerHTML = marked.parse(md);
      }
      // Apply table layout filters if any section uses layout:table
      applyTableFilters();
      // Render mermaid diagrams
      await mermaid.run();
    }

    function applyTableFilters() {
      document.querySelectorAll('[data-layout="table"] table').forEach(table => {
        // Insert a filter input row above the table
        const headers = [...table.querySelectorAll('th')];
        const filterRow = document.createElement('div');
        filterRow.className = 'table-filters';
        headers.forEach((th, i) => {
          const input = document.createElement('input');
          input.placeholder = 'Filter ' + th.textContent;
          input.addEventListener('input', () => filterTable(table, i, input.value));
          filterRow.appendChild(input);
        });
        table.parentNode.insertBefore(filterRow, table);
      });
    }

    function filterTable(table, colIndex, query) {
      const q = query.toLowerCase();
      table.querySelectorAll('tbody tr').forEach(row => {
        const cell = row.cells[colIndex];
        row.style.display = (!q || (cell && cell.textContent.toLowerCase().includes(q))) ? '' : 'none';
      });
    }

    render();
  </script>
</body>
</html>
```

### Generated subpages — `docs/shares/<name>/<subdir>/<slug>.html`

One file per source `.md` file. Slug = kebab-case of the source filename without extension.

Each subpage:
- Includes the same CDN scripts (marked.js, mermaid.js).
- Inlines the `.md` content as a JS string.
- Has a `← Back` link to `../index.html`.
- Carries a self-doc comment: `<!-- SHARE: <name> | PAGE: <slug> | source: <original-md-path> | updated: YYYY-MM-DD -->`.

If a `generated` section has multiple subpages, also write `<subdir>/index.html` as a listing page that links each subpage. Point the nav on the hub to this listing.

### Passthrough sections

Do NOT generate, copy, or modify passthrough files. Only write a navigation link in the hub pointing to the `path` value from config.

---

## Layouts

| Layout | Behavior |
|---|---|
| `hero` | H1 and first paragraph rendered large as a hero block. Remaining markdown rendered as prose below it. |
| `prose` | Render markdown as-is. Mermaid fences (` ```mermaid `) auto-rendered by mermaid.js. |
| `table` | Markdown tables rendered with client-side column filter inputs injected above each table. |
| `accordion` | Each H2 becomes a `<details>/<summary>`. Content starts collapsed. |
| `cards` | Each H2 + following content until the next H2 becomes a styled card, laid out in a grid. |
| `custom` | Design the layout from scratch based on the content and the purpose stated in the interview. Compose multiple layouts or create entirely new structure as needed. |

Layouts apply to both `inline` and `generated` sections. For `inline` sections, add `data-layout="<layout>"` to the section container so JS and CSS can target it.

---

## Image Path Resolution

Images referenced in source `.md` files (e.g. `![](./assets/logo.png)`) use paths relative to the original markdown file. When inlining that content into a generated HTML file at a different location, rewrite each image path to be relative from the HTML file's location.

Algorithm:
1. Find the source `.md` file's directory.
2. Find the generated `.html` file's directory.
3. For each `![...](path)` in the content, resolve `path` from the source directory to an absolute path, then compute the relative path from the HTML directory.
4. Replace in the inlined string before embedding.

External image URLs (`https://...`) are left unchanged.

---

## Content Escaping for JS

When inlining markdown as a JS template literal string:
- Escape all backticks: `` ` `` → `` \` ``
- Escape all `${`: `${` → `\${`
- Do not alter any other content — preserve newlines, special characters, etc.

---

## Update Mode

1. Read `.shareconfig.json`.
2. For each `inline` and `generated` section, re-read the source files (expand any globs to find current files).
3. Regenerate all HTML. Preserve the config — do not re-interview.
4. Update `updated` in the config.
5. If a source file listed in config no longer exists, warn the user before regenerating.

If the user says "update only `<section-id>`", regenerate only that section's output and the hub page.

If the user says "restructure" or "change the layout", re-enter First Run mode but pre-fill answers from the existing config.

---

## Share Index

After creating or updating any share, update `docs/shares/README.md` (create if it doesn't exist):

```markdown
# Shares

| Share | Description | Last Updated |
|---|---|---|
| [name](name/) | one-line description | YYYY-MM-DD |
```

---

## Tone and Design

Match the visual design to the stated purpose and audience:
- **Internal review / technical docs:** Clean, minimal, high information density. Dark or light based on preference.
- **External demo / landing:** Polished, brand-conscious, lower density. Hero sections, clear navigation.
- **Custom:** Honor whatever design direction the user describes in the interview.

The generated HTML does not need to be minimal — it should look good when opened. Write real CSS.

---

## What This Skill Does NOT Do

- Does not push or publish files — output is local files only.
- Does not copy or modify passthrough assets — it only links to them.
- Does not fetch remote content — all sources are local project files.
- Does not create task files or SYSTEM.md entries for this work.
- Does not require a server — all generated HTML works from `file://`.
