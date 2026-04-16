# Component Patterns

## Input Fields

### Text Input
```
┌─────────────────────────────────────┐
│ Label                               │
│ ┌─────────────────────────────────┐ │
│ │ Placeholder text                │ │
│ └─────────────────────────────────┘ │
│ Helper text or error message        │
└─────────────────────────────────────┘

States: default, hover, focus, error, disabled
```

### URL Input (Brand DNA style)
```css
.url-input {
  background: var(--bg-input);
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 16px 20px;
  font-size: 16px;
  color: var(--text-primary);
  width: 100%;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.url-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(212, 201, 138, 0.2);
  outline: none;
}
```

## Buttons

### Primary Button
```css
.btn-primary {
  background: var(--accent);
  color: var(--bg-primary);
  border: none;
  border-radius: 8px;
  padding: 14px 32px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, transform 0.1s;
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-primary:active {
  transform: scale(0.98);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### Button Sizes
```
Small:   padding: 8px 16px;   font-size: 14px;
Medium:  padding: 12px 24px;  font-size: 16px;
Large:   padding: 16px 32px;  font-size: 18px;
```

## Cards

### Content Card
```css
.card {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}
```

### Card with Glow (Pomelli style)
```css
.card-glow {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 40px;
  position: relative;
}

.card-glow::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 17px;
  background: linear-gradient(
    135deg,
    rgba(212, 201, 138, 0.3),
    transparent 50%
  );
  z-index: -1;
  filter: blur(20px);
}
```

## Status Indicators

### Status Pill
```html
<span class="status-pill status-processing">
  <span class="status-icon">✨</span>
  Analyzing your website
</span>
```

```css
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 20px;
  background: rgba(212, 201, 138, 0.15);
  color: var(--accent);
  font-size: 14px;
}
```

### Progress Indicator
```html
<div class="progress-status">
  <div class="spinner"></div>
  <span>About 5 minutes left</span>
</div>
```

## Image/Preview Components

### Website Preview Frame
```css
.preview-frame {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  max-width: 100%;
}

.preview-frame img {
  display: block;
  width: 100%;
  height: auto;
}
```

### Image Grid (for selecting images)
```
┌─────┐ ┌─────┐ ┌─────┐
│     │ │  ✓  │ │     │
│ img │ │ img │ │ img │
└─────┘ └─────┘ └─────┘
┌─────┐ ┌─────┐ ┌─────┐
│     │ │     │ │  ✓  │
│ img │ │ img │ │ img │
└─────┘ └─────┘ └─────┘

- Click to toggle selection
- Checkmark overlay on selected
- Hover shows slight scale/glow
```

## Layout Patterns

### Centered Content (Wizard flow)
```css
.wizard-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--bg-primary);
}

.wizard-card {
  width: 100%;
  max-width: 520px;
}
```

### Split View (Results)
```
┌──────────────────┬──────────────────┐
│                  │                  │
│   Brand DNA      │   Generated      │
│   Summary        │   Outputs        │
│                  │                  │
│   - Colors       │   [Image 1]      │
│   - Fonts        │   [Image 2]      │
│   - Images       │   [Image 3]      │
│                  │   [Image 4]      │
│                  │                  │
└──────────────────┴──────────────────┘
```
