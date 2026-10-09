DESIGN KIT

brand-guide.html  Visual rules, colors, type, logo usage and platform references.
components.html   Working buttons, cards, tables, inputs and editorial styles.
cover-builder.html  Make custom post images; export PNG and editable SVG.
tokens.css / tokens.json  Shared colors, type, spacing and layout values.
components.css    Reusable CSS classes, responsive layouts and focus states.
ChipstratMark.tsx  Optional React/TypeScript component (React 18+ useId).
mark-sprite.svg   Optional SVG symbol for websites.
palettes/        Original palette CSS and JSON, with contrast ratios.

Load tokens.css before components.css. Local font URLs refer to ../fonts/.
The website-starter folder is self-contained and duplicates the necessary files.
Use supplied outlined horizontal logo SVGs for accurate Montserrat spacing.
Use logo-stacked for the original-style chip-above-name composition.
The React component and sprite are convenience source files; the provided
website starter uses standalone SVG images and does not require React.

Primary palette: Fjord & Clay. Alternate: Sea & Poppy.
The detailed circuit mark is for 64px+; the compact drawing is for 32–64px.
Use the supplied micro icons below 32px. Horizontal lockups use the compact mark.
Use dark ink for small text and paper for its background. Clay is a graphical
accent; its contrast on Chalk is 4.33:1, so avoid it for normal small body text.
Use the light/reversed mark on a dark field. Do not recolor one part arbitrarily.
