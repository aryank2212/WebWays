# Branding

## The name

**WebWays**: capital **W** at the start of *both* words, everything else lowercase, no space, no hyphen.

| where | write | not |
|---|---|---|
| prose, UI copy, docs, README, release notes, GitHub repo name and description | `WebWays` | `Webways`, `webways`, `WEBWAYS`, `Web Ways`, `Web-Ways` |
| the UI | the `<Brand />` component (`ui/src/Brand.tsx`), never a hand-typed name | |
| code identifiers and commands | lowercase by convention: `webways_core`, `webways-core`, `~/.config/webways` | |
| environment variables | upper case by convention: `WEBWAYS_ADMIN_TOKEN` | |

Identifiers follow the language/OS conventions (package names, CLIs and env vars have their own casing rules); the
*name as displayed to people* is always `WebWays`.

"swarm" in lowercase is **not** the product name any more; it only appears as the BitTorrent term for the group of
peers sharing a torrent.

## The wordmark

The name is set in **Bodoni Moda Bold (700)**, a bold, high-contrast Didone serif, with letter-spacing `-0.02em`.
The same face and tracking are used everywhere the name is displayed:

| place | how |
|---|---|
| web UI header, headings, in-text mentions | `<Brand />` → CSS class `.wordmark` (`ui/src/styles.css`); font loaded from the bundled package `@fontsource/bodoni-moda` (`latin-700.css`), so **no request goes to Google Fonts or any CDN** |
| README banner | `docs/assets/webways-wordmark.svg` (dark text) and `webways-wordmark-light.svg` (light text), chosen by `prefers-color-scheme` |
| browser tab icon | `ui/src/assets/favicon.svg`: the "W", dark on light tabs and light on dark tabs |

The SVGs are outlined paths (text converted to shapes with real kerning), so they look identical on GitHub, in
browsers and in any viewer, with no font installed. Regenerate them with:

```
.venv/bin/pip install fonttools uharfbuzz
.venv/bin/python scripts/gen_wordmark.py
```

Body text in the UI stays in the system sans-serif for readability; only the name uses the wordmark face. To use the
serif for headings too, change `.wordmark` usage in `styles.css`; don't introduce a third font.

## Colours and usage

Wordmark colour is `#111111` on light backgrounds and `#ffffff` on dark ones, nothing else. Keep clear space of at
least the height of the "e" around it, don't stretch it, outline it, add effects, or re-typeset it in another font.

## Licensing of the assets

Bodoni Moda is © its authors and licensed under the **SIL Open Font License 1.1**, which permits using it in a
product and embedding outlines in artwork. The license text is in `THIRD_PARTY_NOTICES.md`. The generated SVGs are our
artwork derived from that font. This look is a deliberate typographic style (bold Didone serif) and is **not** a copy of
any third party's logo.
