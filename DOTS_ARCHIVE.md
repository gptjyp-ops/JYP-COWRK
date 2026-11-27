# DOTS design archive

Page: `dots.html`. The stable public manifest is `assets/dots/archive-manifest.json`.

- `D001` through `D128` retain the numbered selection PDF identities.
- `A01` through `A33` preserve **all** previous embedded GitHub images, including the three formerly hidden ones. Some historical images overlap recovered designs; none are silently discarded.
- WebP display copies keep the original pixel dimensions. The manifest retains the source filename, date, and original Library reference for owner recovery. Existing embedded gallery source files are preserved.
- The 26 daily concepts dated October 14 through November 8 are recorded in `missingSets`. Their image originals have not been recovered. These records are never presented as uploaded photos.

## Selection and ChatGPT handoff

Selection and notes are stored in browser localStorage. Users can export/import selection JSON. Nothing is sent to a server automatically.

The **ChatGPT에 보내기** button prepares and copies exact design IDs, per-design notes, public image links and a restorable `dots.html?pick=D006,D008` URL. The user then opens the existing conversation and pastes/sends the text. Do not describe copying or opening a chat as a successfully transmitted message.

When a user sends the selection text, JSON, or `pick` link, read the IDs from this manifest and open the selected existing images. Only user-selected references are authorized as design choices.

## Updating the archive

Append new records without renumbering existing ones. Keep all assets and stable IDs. Never use newly generated images to stand in for unavailable historical originals.

Validation: `node --test test_dots_archive.cjs` and `node --check assets/dots/archive.js`.
