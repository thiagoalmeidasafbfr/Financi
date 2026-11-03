Azure Finance is a clear, confident interface for personal finance with an AI layer: white pages and deep navy app screens, four brand blues, one neutral grotesque, and insights written as plain findings.

## Content fundamentals

- Headlines are short, declarative and sentence case, often in two beats: "Know what changed. Understand what matters." / "A smarter start to personal finance".
- Insights are written as findings, then meaning: "Subscriptions are down 18%" + "Great job cutting recurring costs".
- Labels are one word (Send, Transfer, Budget, More); hints are two (Transfer money, Track spending).
- Section labels are uppercase overlines in `ink-faint`: "SPENDING INSIGHTS", "ONBOARDING FLOW".
- Steps are numbered "01 — Create Account".
- Amounts: "$37,240.00"; changes always signed ("-18%", "+12%", "12.5% vs last month").
- Address the user as "you"; greet by first name ("Welcome back, Alex"). No exclamation marks, no emoji.

## Color

- Brand blues, darkest to lightest: `midnight-navy` (app ground, dark sections), `royal-blue` (links, badges, score ring, primary on light), `bright-azure` (primary in the app, active and AI accents), `cloud-blue` (wells, chips, the AI card).
- Light theme: pages on `surface` (#fafafa), cards on `surface-raised` (white) with `shadow-card`, text in `ink` (#0d151e) and `ink-muted`.
- Navy theme: wrap app screens in `data-theme="navy"`; ground is Midnight Navy, inputs sit on `surface-sunken`, primary buttons are Bright Azure.
- Mix them as the brand does: a white page with a navy panel or phone, or a navy header sliding into a white sheet (home screen).
- Direction is carried by arrows, signs and words, not by green and red.
- Watch the source's weak pairs: white on Bright Azure is 3.3:1 (large labels only) and `ink-faint` overlines are decorative.

## Type

- One family: Helvetica Neue, falling back to Helvetica and Arial. Two weights only: 400 Regular and 500 Medium.
- Presentation pages: `display` for section headlines, `headline` for secondary ones, `heading` for card titles, `lead` in `ink-muted` for intros, `overline` uppercase in `ink-faint`.
- App: `balance` for the total, `title` for screen titles, `body` for rows, `label` for buttons and chips, `caption` for descriptions, `micro` for tab labels.
- Use tabular numerals for every figure.

## Spacing, radius, depth

- App gutter `space-4`; card padding `space-4` in the app, `space-6` on pages; page margins `space-18`.
- `radius-sm` (8px) for buttons, inputs and square icon buttons; `radius-md` (12px) for in-app cards; `radius-lg` (20px) for page cards; `radius-pill` for chips, segmented tabs and round wells.
- Depth is one soft shadow (`shadow-card`); only the AI Copilot button glows (`shadow-fab`).
- Focus: 2px solid `focus-ring` with a 2px offset.

## Iconography

- Line icons, 1.8px stroke, round caps, 16–22px, in `link` inside Cloud Blue wells or in `ink` on buttons.
- The four-point sparkle marks AI features only.
- The preview icons are simple stand-ins drawn for this system; replace them with your chosen line-icon library at the same sizes and stroke.

## Imagery

- Product shots of the phone on white or navy, with a soft blue gradient behind; hands holding the device.
- Large faded letterforms behind content are part of the original brand's logo world and are not used here.

## Logo

- No logo is included. Set the name "Azure Finance" in Helvetica Neue Medium in `ink` (or white on navy) until an official mark is added under `assets/Logos/`.

## Components

Styles live in `components/bundle.css` with the `az-` prefix; there is no JavaScript bundle. Each component's guidelines are in its README: Button, Chip, Badge, IconWell, ScoreRing, InsightRow, AiInsightCard, BalanceHeader, QuickActions, TabBar, SegmentedTabs, TextField, StepList.
