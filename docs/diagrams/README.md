# Editable walkthrough diagrams

The .mmd files are original Mermaid sources. PNG and SVG renderings are provided for article use. Explanatory captions belong in the surrounding article, not inside the images. The measured-results.png chart comes from the unchanged original experiment; its caption and denominator are in the walkthrough.

Render with the pinned Mermaid CLI version in manifest.json, using a supported local browser configuration if required.

```sh
mmdc -i NAME.mmd -o NAME.png -c mermaid.json --size 1800 -s 2 -b white
mmdc -i NAME.mmd -o NAME.svg -c mermaid.json --size 1800 -s 2 -b white
```

The default Mermaid browser download was skipped for this rendering; an existing browser ran in a separate headless process. No authenticated browser session was used.
