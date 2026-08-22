# Assets

This folder is reserved for visual assets. It is **intentionally empty** right now — the logo is still a draft, and no README references an image yet.

## When the logo is ready

1. Drop the files here:

   ```text
   docs/assets/logo.svg          preferred — scales everywhere
   docs/assets/logo.png          512 × 512, transparent background, fallback
   docs/assets/logo-dark.svg     optional, if the mark needs a dark variant
   ```

2. Uncomment the placeholder at the top of [`../../README.md`](../../README.md) — twice: once above the English half, once above the Russian half:

   ```html
   <img src="docs/assets/logo.svg" width="128" alt="MVS Analyzer" />
   ```

   Keep it inside the existing `<div align="center">` block, above the title.

3. For GitHub's social preview card, use a 1280 × 640 PNG uploaded in **Settings → General → Social preview** — it does not belong in the repository.

## Screenshots

Same folder, same rules:

```text
docs/assets/screenshot-results.png
docs/assets/screenshot-calibration.png
docs/assets/screenshot-audit.png
```

Guidelines that keep the README fast and honest:

- PNG, no larger than ~300 KB each — run them through a compressor;
- capture at 100 % display scaling, light **and** dark theme if you show both;
- use the bundled `examples/` datasets, never real measurement data;
- always set meaningful `alt` text;
- keep them in `docs/`, not in the repository root.

## What not to put here

- Build outputs, run folders, or anything from `%LocalAppData%\MVS_Analyzer\`.
- Real datasets or anything with identifiable device serials or subject ids.
- Large binaries — GitHub renders a README slowly when it has to fetch megabytes of images.

> `.gitignore` deliberately does **not** exclude this folder, but Git will not track an empty directory, which is why this file exists.
