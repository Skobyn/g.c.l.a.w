# Accessibility Guidelines

## WCAG 2.1 Quick Reference

### Level AA (Minimum)
- **Color contrast**: 4.5:1 for normal text, 3:1 for large text
- **Focus indicators**: Visible focus states on all interactive elements
- **Keyboard navigation**: All functionality accessible via keyboard
- **Alt text**: Descriptive alt for images, empty for decorative
- **Form labels**: All inputs have associated labels
- **Error identification**: Clear error messages with instructions

### Level AAA (Enhanced)
- **Color contrast**: 7:1 for normal text, 4.5:1 for large text
- **No timing**: No time limits or ability to extend
- **No interruptions**: Suppresable non-essential alerts

## Common ARIA Patterns

### Buttons
```html
<button aria-label="Close dialog" aria-pressed="false">
  <svg aria-hidden="true">...</svg>
</button>
```

### Loading States
```html
<div aria-live="polite" aria-busy="true">
  Loading content...
</div>
```

### Dialogs/Modals
```html
<div role="dialog" aria-modal="true" aria-labelledby="title">
  <h2 id="title">Dialog Title</h2>
  ...
</div>
```

### Progress
```html
<div role="progressbar" aria-valuenow="50" aria-valuemin="0" aria-valuemax="100">
  50%
</div>
```

### Form Errors
```html
<input aria-invalid="true" aria-describedby="error-msg">
<span id="error-msg" role="alert">Please enter a valid URL</span>
```

## Focus Management

1. **Trap focus in modals** — Tab should cycle within modal
2. **Return focus** — After modal closes, return to trigger
3. **Skip links** — Allow skipping navigation
4. **Focus order** — Logical tab order matches visual order

## Color Contrast Tools

- WebAIM Contrast Checker
- Stark (Figma plugin)
- axe DevTools (browser extension)

## Testing Checklist

- [ ] Navigate entire flow with keyboard only
- [ ] Test with screen reader (VoiceOver, NVDA)
- [ ] Check color contrast ratios
- [ ] Verify focus indicators visible
- [ ] Test at 200% zoom
- [ ] Validate form error announcements
