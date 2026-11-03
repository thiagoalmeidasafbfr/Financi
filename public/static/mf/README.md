Modern Finance is a calm, monochrome interface for money: black grounds, frosted glass, pill-shaped controls and large, confident figures. Hierarchy comes from lightness and weight, never from hue.

## Content fundamentals

- Speak plainly and briefly. Labels are one or two words: "Deposit", "Withdraw", "View All", "Account Balance".
- Headlines are short statements in title case ("Modern Tools for Modern Finance"); everything else is sentence case.
- Greet by first name with a two-tone line: "Hello!" in `ink-muted`, the name in `ink` at weight 700.
- Figures lead. Write currency with symbol, thousands separator and two decimals ("$32,846.59"); debits take a leading minus ("-$68.92"); periods are spelled out ("4.26% this month").
- Dates are relative when recent ("Today, 09:42"), short otherwise ("Sep 24, 10:36").
- No emoji, no exclamation marks beyond the greeting, no colour words for direction.

## Color

- Build every screen on `surface-000`. Step up one surface per layer: cards on `surface-100`, controls on `surface-200`, bubbles and the tab bar on `surface-300`, the selected chip on `surface-400`.
- Text is `ink` for primary content and amounts, `ink-muted` for dates, links and labels, `ink-subtle` only for cents and other tertiary figures on `surface-000` to `surface-200`.
- Glass (`glass` + `glass-edge` + `shadow-glass` + `blur-glass`) is for surfaces that float over imagery or gradient: the balance card, the greeting chip, the primary Get Started pill, the tab bar.
- `notify` is the only hue, and only as the unread dot on an icon button.
- Gains and losses are never green and red: carry direction with an arrow and words (TrendPill) or a minus sign.
- Charts use two values only: `chart-lit` for the focus period and `chart-dim` for context.
- Dark is the primary theme. Light is a derived theme for printed reports and daylight use; it keeps the same structure with surfaces inverted.

## Type

- `display` (Manrope 600) for the onboarding headline only, centred, first words in `ink-muted` and the closing words in `ink`.
- Everything else is Lato. Figures use `balance` (one per screen), `amount-lg` for section totals, `amount` inside cards, always with tabular numerals (`.mf-num`).
- `title` for section headers, `body-lg` for row titles and button labels, `body` for labels, `caption` for dates and links, `micro` for tab labels only.
- Both families load from Google Fonts (`components/bundle.css` imports them).

## Spacing, radius, depth

- Screen gutter `space-4`; card padding `space-4` (balance card `space-6`); rows `space-5` vertical; sections `space-8` apart.
- Controls are always pills or circles (`radius-pill`). Cards use `radius-md`; the balance card and sheets `radius-lg`.
- Depth is a top-edge highlight plus a soft dark drop (`shadow-glass`, `shadow-control`); no coloured glows, no hard borders except `line` hairlines between rows and `line-strong` around controls.
- Keyboard focus: a solid 2px `focus-ring` with a 2px offset, on every interactive element.

## Imagery

- Full-bleed, high-key studio photography in black and white tones on onboarding: a person in light clothing against a dark gradient, the product held toward the camera.
- Behind the home header, a blurred, desaturated photo fading into `surface-000` lets the glass card read.
- Never coloured illustrations or 3D icons.

## Iconography

- Single-ink icons, 20–22px, filled for objects (bell, wallet, bag, cup, briefcase, calendar) and stroked 1.8–2px for arrows and navigation.
- Icons sit inside round wells (`surface-200`, `line` edge) or round icon buttons.
- The preview icons are simple stand-ins drawn for this system; the original mockups' icon set was not provided. Replace them with your chosen icon library at the same sizes.

## Logo

- No logo was supplied. Set the name "Modern Finance" in Manrope 600 in `ink` until an official mark is added under `assets/Logos/`.

## Components

Styles live in `components/bundle.css` with the `mf-` prefix; there is no JavaScript bundle. Each component's guidelines are in its README: Button, IconButton, TrendPill, BalanceCard, SectionHeader, TransactionRow, TabBar, CategoryCard, SpendingBubble.
