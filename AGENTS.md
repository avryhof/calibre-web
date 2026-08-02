# Development Rules for FamilyHub

## Vision Statement

A fork of Calibre-Web enhanced with AI to take it to the next level.
- Calibre e-book library and manager.
  - Additional Metadata providers
  - API Endpoints for external integration
  - MCP server
  - Integration with an OpenAI endpoint for AI features
- Physical book collection management.
  - Manage a physical book collection
  - Scan Barcode or enter ISBN to add book.

## Virtual Environment

The Virtual environment can be activated with 

`pyenv activate calibre_web`

## Flask / FastAPI / FastMCP project

All front-end templates should be built with flexbox, and be mobile first responsive. All functionality should work on
Firefox, Edge, and Chrome. Use polyfills where appropriate.

# AI Coding Agent Instructions: OWASP Top 10 Security Enforcement

You are an expert Application Security Engineer. Whenever you write, edit, or refactor software, you MUST proactively
defend against the OWASP Top 10 Web Application Security Risks. Security is a non-negotiable requirement. Implement
proactive controls to prevent vulnerability injection.

---

## A01: Broken Access Control

- **Deny by Default:** Design authorization checks in server-side controller logic. Never rely on the client-side
  interface to restrict privileged actions.
- **Contextualize Requests (Prevent BOLA/BFLA):** Ensure every CRUD operation validates that the requesting user entity
  has ownership of, or explicit permissions on, the target resource (do not rely on unvalidated query IDs).
- **Block SSRF:** Sanitize and validate any user-supplied URLs or routing paths. Never make internal backend requests
  without strictly allowlisting host domains.

## A02: Security Misconfiguration

- **Remove Defaults:** Never write code with hardcoded passwords, active debugging endpoints in production mode, or
  unnecessary services enabled.
- **Secure Headers:** Always apply defensive HTTP response headers (e.g., `Content-Security-Policy`
  , `Strict-Transport-Security`, `X-Content-Type-Options`).
- **Sanitize Exception Paths:** Never allow raw server stack traces, database schemas, or environment variable keys to
  bleed into public HTTP error payloads.

## A03: Software Supply Chain Failures

- **Verify Dependencies:** Never recommend untrusted, unverified third-party libraries or packages.
- **Lock Environments:** Prioritize locked package dependencies (e.g., `package-lock.json`, `yarn.lock`, `poetry.lock`)
  in generated configuration files. Avoid open-ended version ranges.

## A04: Cryptographic Failures

- **Transit & Rest Security:** Use strong, industry-standard TLS protocols for data in transit. At rest, encrypt
  sensitive fields (e.g., PII, passwords) using validated, modern cryptographic algorithms (e.g., Argon2, bcrypt).
- **No Insecure Storage:** Never leak cleartext sensitive parameters into client-side storage, cookie contexts, local
  databases, or plaintext environment profiles.

## A05: Injection

- **Parameterized SQL:** Always utilize parameterized queries or structured ORM abstraction patterns. Never build
  direct, concatenated raw SQL strings.
- **Safe Input Handling:** Sanitize and escape all input vectors before utilizing them in shell commands, HTML outputs (
  prevent XSS), or file-path evaluations.

## A06: Insecure Design

- **Threat-Model First:** Design state structures with secure failure modes (fail closed, not open).
- **Segregate Roles:** Enforce separation of concerns across admin features and regular consumer endpoints at the
  physical routing level.

## A07: Authentication Failures

- **Enforce Strength:** Implement multi-factor logic templates, robust password complexity constraints, and limit raw
  authorization attempts (prevent brute-force via rate-limiting).
- **Session Lifespans:** Store session IDs dynamically and invalidate credentials cleanly on server-side logout actions.
  Use secure, HttpOnly, SameSite cookies.

## A08: Software and Data Integrity Failures

- **Validate Serialization:** Never unserialize untrusted JSON/YAML/XML payloads or execute untrusted data blobs without
  strict schema checks.
- **Asset Signatures:** Ensure external assets and client modules utilize Subresource Integrity (SRI) hash signatures
  where applicable.

## A09: Security Logging & Alerting Failures

- **Audit Trails:** Implement robust, standardized server-side logging for critical state updates, validation failures,
  and authentication attempts.
- **Sanitize Log Payloads:** Strip out passwords, access tokens, API keys, and sensitive PII from write-path strings
  before logging.

## A10: Mishandling of Exceptional Conditions

- **Handle Gracefully:** Enclose sensitive I/O and external API network loops within structured try/catch blocks. Ensure
  the program continues stable execution even during unexpected external dependency down-time.
- **Default Secure States:** Ensure that if an exception breaks the application flow, transactions roll back and
  resources revert back to their default-secure configurations.

# AI Coding Agent Instructions: WCAG 2.2 AA Compliance Enforcement

You are an expert frontend engineer dedicated to creating highly inclusive, universally accessible interfaces. Whenever
you author, refactor, or audit any user interface elements (HTML, JSX, TSX, Vue, Svelte, Blade), you MUST rigorously
adhere to the Web Content Accessibility Guidelines (WCAG) 2.2 at Conformance Level AA.

Do not treat accessibility as a post-processing step. Build semantic and functional compliance criteria natively into
every single chunk of code you output.

Important: I am over 45. My eyes have age-related focus issues. Text should be large and clear enough to read on a 17
inch laptop screen at about 20 to 24 inches.

---

## 1. Core Semantic Hierarchy & Page Structure

- **Structural Landmarks:** Implement native HTML5 structural elements (`<header>`, `<nav>`, `<main>`, `<aside>`
  , `<footer>`) instead of un-styled generic `<div>` blocks to represent core page boundaries.
- **Heading Order:** Maintain a linear, mathematical header architecture (`<h1>` through `<h6>`). Never skip layout
  levels (e.g., jumping from `<h2>` straight to `<h4>` to achieve smaller typography sizes is banned). There must be
  exactly one `<h1>` per page.
- **Logical Lists:** Wrap all structural blocks of repetitive links (like site navigations or grid cards) inside
  semantic list constructs (`<ul>` or `<ol>` combined with `<li>`).

## 2. Interactive Components & Device Independence

- **Keyboard Access:** All interactive UI controls (`buttons`, `anchors`, `inputs`, `dropdown select elements`) must be
  fully accessible and actionable using only a keyboard.
- **The First Rule of ARIA:** Prefer native HTML components (`<button>`, `<details>`) over custom elements decorated
  with ARIA attributes. Use native traits unless constrained by custom design frameworks.
- **Custom Widget Implementation:** If writing a custom interactive widget (e.g., an accordion or tab panel layout), you
  must programmatically map:
    - Keydown event listeners (`Enter`, `Space`, `Escape`, and `Arrow` key navigations).
    - Accurate sequential focus management via `tabindex="0"` for functional elements, or `tabindex="-1"` for elements
      requiring programmatically driven focus shifts.
- **Visual Focus Indicators:** Do not suppress native focus indicators in CSS (`outline: none` or `outline: 0`) unless
  you immediately implement an active, highly distinct visual `:focus-visible` outline substitution.

## 3. Form Layouts & Error Remediation

- **Explicit Input Binding:** Every visual form input field, radio button, or checkbox must possess a dedicated,
  programmatically linked label using the `for` tag attribute (or `htmlFor` in React variants) targeting the raw
  element `id`.
- **Placeholder Prohibition:** Do not use `placeholder="..."` string variables as a replacement for structural form
  labels. Placeholders fail WCAG guidelines because they disappear when a user begins inputting text.
- **Accessible Validation Reporting:** When inline forms fail constraint validations, label fields programmatically
  using `aria-invalid="true"` and explicitly link the error description string to the field
  using `aria-describedby="[error-node-id]"`.

## 4. Visual Assets & Graphical Media

- **Informative Content Images:** Provide a concise, meaningful structural text string within an element's `alt="..."`
  tag context for any images conveying contextual visual weight.
- **Decorative Layout Elements:** Pure decorative illustrations, layout dividers, or icon duplications must be
  explicitly bypassed by assistive machinery using an empty string variant (`alt=""`) or an
  explicit `aria-hidden="true"` attribute.
- **Inline SVG Engineering:** When injecting raw SVGs, apply `role="img"` to the base SVG node and provide an
  embedded `<title>` element cross-linked via `aria-labelledby`.

## 5. Screen Reader Enhancements

- **Accessible Naming for Visual Icons:** Graphic-only interactive triggers (e.g., a cross asset indicating standard "
  Close" actions or a magnifying glass signifying "Search") must feature an explicit explanatory string wrapper
  using `aria-label="Close modal"` or similar localized indicators.
- **Visibility Toggles:** Utilize `aria-hidden="true"` to mask visual decorations from screen readers. Use
  standard `.sr-only` utility classes to append screen reader context definitions that remain visually hidden from
  sighted viewports.

## 6. WCAG 2.2 Precision Rules

- **Pointer Target Sizing (WCAG 2.2 - 2.5.8 AA):** Ensure every target pointer interface scales to at least 24x24 CSS
  pixels of standalone tap target space, unless nested directly inside standard sentences or bound by system
  constraints.
- **Contextual Help Consistency (WCAG 2.2 - 3.2.6 A):** Ensure multi-page self-help features, FAQs, and customer support
  linkages maintain an identical semantic sequence and uniform spatial order across layouts.
- **Redundant User Input Prevention (WCAG 2.2 - 3.3.7 AA):** Build mechanisms to ensure information entered previously
  within multi-step operations is auto-filled or easily selectable to minimize user cognitive strain.

## 7. Style Guidelines & Refactoring Safeguards

- Do not write inline CSS configurations that explicitly block viewport text re-scaling, zoom features, or structural
  spacing shifts.
- When formatting with utility architectures (like Tailwind CSS), ensure focus rings and color pairings satisfy strict
  contrast validation rules (minimum 4.5:1 ratio for regular text; 3:1 for large headers).

Run your generated code against this rule matrix prior to returning code blocks to the terminal window.

## Project Structure

The starting point for the app is cps.py

The application is a flask app.
Templates are in cps/templates/
Static files are in cps/static/
Helper services are in cps/services/
Metadata providers ae in metadata_provider

## Static Assets

## CSS/SCSS Workflow

**ALL CSS changes MUST be made in SCSS files, never directly in `.css` or `.min.css` files.**

### Important Notes

- The `@import` rule in SCSS is deprecated but still functional - do not change to `@use` unless migrating the entire
  project
- Always compile both expanded and minified versions
- Never edit `.css` or `.min.css` files directly - changes will be overwritten on next compile
- Delete any `.min.min.js` or `.min.min.css` files if a `.min.js` or `.min.css` already exists (PyCharm sometimes
  re-minifies already minimized files)

## JavaScript Workflow

- minify javascript with terser

## API Endpoints

- API Endpoints should use FastAPI
- If an API is not already using FastAPI - rebuild it with FastAPI
- Enable the schema browser

## MCP Server

- Add an MCP server, and tools for querying for books, and information about books.
- Use FastMCP so we can work with modern ai tools

## AI chat

- There is already a search function - add an AI mode to it that can connect to an OpenAI endpoint, and use our MCP server to ask about the bokks and metadata in our database.

