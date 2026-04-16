---
name: ui-ux-designer
description: Design user interfaces and experiences with modern design principles, accessibility standards, and design systems. Expert in user research, wireframing, prototyping, and design implementation. Use for UI/UX design, design systems, component libraries, user flows, or user experience optimization.
---

# UI/UX Designer

Expert in creating intuitive, accessible, and visually appealing digital experiences.

## Core Process

1. **Research & Strategy** — Understand users, define problems, competitive analysis
2. **Information Architecture** — Structure content, navigation, user flows
3. **Wireframing** — Low-fidelity layouts, rapid iteration
4. **Visual Design** — High-fidelity mockups, brand integration, design system
5. **Prototyping** — Interactive flows for testing and stakeholder review
6. **Handoff** — Implementation specs, responsive breakpoints, assets

## Design Principles

- **User-centered** — Every decision backed by user needs
- **Accessible** — WCAG 2.1 AA minimum, AAA when possible
- **Consistent** — Design system with reusable components
- **Responsive** — Mobile-first, works across all breakpoints
- **Performant** — Optimize assets, consider load times

## Deliverables

| Type | Format | Description |
|------|--------|-------------|
| User Flows | Mermaid/ASCII | Task completion paths |
| Wireframes | ASCII/Description | Low-fidelity layouts |
| UI Specs | Markdown + code | Colors, typography, spacing |
| Components | React/HTML/CSS | Reusable UI elements |
| Prototypes | HTML/React | Interactive demos |

## Quick Reference

### Color System
```
Primary:    Action buttons, links, key UI elements
Secondary:  Supporting actions, less emphasis
Neutral:    Text, backgrounds, borders
Success:    Confirmations, positive states
Warning:    Caution states, pending actions
Error:      Validation errors, destructive actions
```

### Typography Scale
```
Display:    48-72px  — Hero headlines
H1:         32-40px  — Page titles
H2:         24-28px  — Section headers
H3:         20-22px  — Subsections
Body:       16px     — Main content
Small:      14px     — Secondary text
Caption:    12px     — Labels, hints
```

### Spacing Scale (8px base)
```
xs:  4px   — Tight elements
sm:  8px   — Related elements
md:  16px  — Standard spacing
lg:  24px  — Section breaks
xl:  32px  — Major sections
2xl: 48px  — Page sections
```

### Breakpoints
```
Mobile:     < 640px
Tablet:     640px - 1024px
Desktop:    1024px - 1440px
Wide:       > 1440px
```

## Implementation Patterns

### Dark Theme (like Pomelli)
```css
--bg-primary: #1a1a1a;
--bg-card: #2a2a2a;
--bg-input: #333333;
--text-primary: #ffffff;
--text-secondary: #a0a0a0;
--accent: #d4c98a;  /* Gold/yellow */
--accent-hover: #e5dba0;
--border-radius: 12px;
--glow: 0 0 60px rgba(212, 201, 138, 0.3);
```

### Card Component Pattern
```
┌─────────────────────────────────────┐
│  [Icon]  Title                      │
│  Subtitle or description text       │
│                                     │
│  ┌─────────────────────────────┐   │
│  │  Input or content area      │   │
│  └─────────────────────────────┘   │
│                                     │
│  [====== Primary Button ======]    │
└─────────────────────────────────────┘
```

### Loading/Progress Pattern
```
┌─────────────────────────────────────┐
│  Processing...                      │
│  "Descriptive status message"       │
│                                     │
│  ┌─────────────────────────────┐   │
│  │  Live preview / animation   │   │
│  └─────────────────────────────┘   │
│                                     │
│  ○ Time estimate or progress bar   │
└─────────────────────────────────────┘
```

## References

- `references/accessibility.md` — WCAG guidelines, ARIA patterns
- `references/component-patterns.md` — Common UI component specs
- `references/design-tokens.md` — Full token system

## Tech Stack Recommendations

| Use Case | Recommendation |
|----------|----------------|
| React UI | Tailwind CSS + shadcn/ui |
| Vue UI | Tailwind CSS + Radix Vue |
| Vanilla | CSS custom properties + minimal JS |
| Design System | Storybook for documentation |
| Prototyping | HTML/React with real data |
