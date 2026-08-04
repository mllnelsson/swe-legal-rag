The standard Svk Beslutsök button — one `primary` (burgundy) per view, everything else `secondary` or `ghost`.

```jsx
<Button variant="primary" size="md" iconLeft={<Icon name="search" size={16} />}>Run search</Button>
```

Variants: `primary` (burgundy fill), `secondary` (white, hairline border), `accent` (apricot fill, for marketing CTAs), `ghost` (text only), `danger`. Sizes `sm | md | lg`. Press state nudges 0.5px down and drops the shadow — never scales.
