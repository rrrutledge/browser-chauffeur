# Chart Sizing in Reveal.js

Charts use the [reveal.js-plugins/chart](https://github.com/rajgoel/reveal.js-plugins) plugin (Chart.js). The scaffold includes Chart.js and the plugin by default.

## Required Sizing Pattern

Chart.js defaults to a 2:1 aspect ratio, which causes overflow in slide layouts. Every chart needs this pattern:

1. **Flexbox section**: `display: flex; flex-direction: column; height: 100%;`
2. **Container div**: `flex: 1; position: relative; min-height: 0;` (add `min-width: 0` in grid layouts)
3. **`maintainAspectRatio: false`** in chart options

```html
<section style="display: flex; flex-direction: column; height: 100%;">
  <h2>Chart Title</h2>
  <div style="flex: 1; position: relative; min-height: 0;">
    <canvas data-chart="bar">
    <!--
    {
      "data": {
        "labels": ["Q1", "Q2", "Q3", "Q4"],
        "datasets": [{ "label": "Revenue", "data": [45, 52, 61, 78], "backgroundColor": "#2196F3" }]
      },
      "options": { "maintainAspectRatio": false }
    }
    -->
    </canvas>
  </div>
</section>
```

For side-by-side layouts (chart + content), use CSS grid inside the flex container:

```html
<div style="flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 30px; min-height: 0; min-width: 0;">
  <div><!-- content --></div>
  <div style="position: relative; min-height: 0; min-width: 0;">
    <canvas data-chart="pie"><!-- config --></canvas>
  </div>
</div>
```

Always run `node scripts/check-overflow.js` after adding charts.
