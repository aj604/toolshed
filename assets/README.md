# Workbench brand assets

| File | Use |
|---|---|
| [`social-card.png`](social-card.png) | 1280 × 640 PNG for GitHub's social preview, the root README hero, and X launch posts |
| [`social-card.html`](social-card.html) | Editable HTML/CSS source for the social card; includes its own vector mark and uses system fonts |
| [`icon.png`](../plugins/workbench/assets/icon.png) | 1024 × 1024 PNG for the plugin listing and square placements |
| [`icon.svg`](../plugins/workbench/assets/icon.svg) | Editable vector source for the Workbench mark |

The palette is dark green (`#18211f`), warm cream (`#f5f0e6`), and coral
(`#ff784f`). Keep the mark and colors aligned across the sources when editing.
The card names the five skills and their outcomes; workflow demos should show
actual runs separately.

## Upload the GitHub social preview

GitHub stores the social preview as a separate upload. Changing the README or
committing `social-card.png` does **not** replace that upload.

1. Download or select [`social-card.png`](social-card.png).
2. Open the repo's [Settings → General](https://github.com/aj604/toolshed/settings).
3. Find **Social preview**, then choose **Edit → Upload an image…**.
4. Upload the PNG and confirm the preview shows Workbench.

The PNG is 1280 × 640 and under 1 MB, matching
[GitHub's social-preview guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).
Previously shared links can retain a cached image after the upload.

To verify the image GitHub is currently serving:

```sh
gh api graphql -f query='query { repository(owner:"aj604", name:"toolshed") { usesCustomOpenGraphImage openGraphImageUrl } }'
```

Open the returned `openGraphImageUrl` and check the artwork itself.

## Re-export after editing

Open `social-card.html` in a browser. Set the viewport to **1280 × 640** CSS
pixels at **1× device scale**, wait for the page to finish drawing, then save
a viewport screenshot as `social-card.png`. The source has no external assets
or font dependencies. Check the PNG's dimensions, file size, and text before
committing it or uploading it to GitHub. The SVG icon also has a PNG export;
keep both icon files aligned if you change the mark.
