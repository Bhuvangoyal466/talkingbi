# TalkingBI — Frontend Project File & Directory Reference

> **Project:** `vite_react_shadcn_ts` — A Conversational Business Intelligence (BI) web application built with React, TypeScript, Vite, Tailwind CSS, and shadcn/ui components.

---

## Root Directory

| File / Dir | Description |
|---|---|
| `index.html` | HTML entry point. Mounts the React app into the `#root` div. |
| `package.json` | Project manifest. Defines scripts (`dev`, `build`, `lint`, `test`), dependencies (React 18, Recharts, Radix UI, TanStack Query, React Router, etc.), and devDependencies. |
| `bun.lockb` | Bun binary lockfile — locks exact dependency versions for reproducible installs. |
| `bun.lock` | Human-readable Bun lockfile (text format). |
| `package-lock.json` | npm lockfile for npm-based dependency resolution. |
| `vite.config.ts` | Vite bundler configuration. Sets dev server on port `8080`, configures `@vitejs/plugin-react-swc`, path alias `@` → `./src`, and integrates `lovable-tagger` in development mode. |
| `tailwind.config.ts` | Tailwind CSS configuration. Enables dark mode via `class`, sets content paths, extends theme with custom colors (CSS variables), font (`Inter`), border radius, and keyframe animations. |
| `postcss.config.js` | PostCSS configuration used by Tailwind CSS for CSS transformation. |
| `tsconfig.json` | Root TypeScript configuration. References `tsconfig.app.json` and `tsconfig.node.json`. |
| `tsconfig.app.json` | TypeScript config for the application source (`src/`). Sets up strict mode, JSX, and module resolution. |
| `tsconfig.node.json` | TypeScript config for Node.js context files (e.g., `vite.config.ts`). |
| `eslint.config.js` | ESLint flat config. Extends recommended JS/TS rules and adds `eslint-plugin-react-hooks` and `eslint-plugin-react-refresh` plugins for React-specific linting. |
| `components.json` | shadcn/ui configuration. Specifies style, Tailwind config path, CSS variable usage, base color (`slate`), and path aliases for components, hooks, lib, and ui directories. |
| `playwright.config.ts` | Playwright end-to-end test configuration. Uses `lovable-agent-playwright-config` factory for default settings. |
| `playwright-fixture.ts` | Playwright test fixture definitions for custom test helpers or shared page context. |
| `vitest.config.ts` | Vitest unit test configuration. Uses `jsdom` environment, global test APIs, setup file at `src/test/setup.ts`, and React SWC plugin. |
| `.gitignore` | Git ignore rules — excludes build outputs, `node_modules`, environment files, etc. |
| `README.md` | Project readme. Currently a placeholder from the Lovable scaffold (`TODO: Document your project here`). |

---

## `public/`

Static files served directly at the root URL — not processed by Vite.

| File | Description |
|---|---|
| `favicon.ico` | Browser tab icon for the application. |
| `placeholder.svg` | Generic SVG placeholder image, usable for missing images or loading states. |
| `robots.txt` | Search engine crawl instructions for the site. |

---

## `src/`

Main application source code.

| File | Description |
|---|---|
| `main.tsx` | Application bootstrap. Calls `createRoot` on `#root` and renders `<App />`. Imports global `index.css`. |
| `App.tsx` | Root React component. Sets up `QueryClientProvider` (TanStack Query), `TooltipProvider`, `Toaster`, `Sonner` toast provider, and React Router with two routes: `/` → `Index` and `*` → `NotFound`. |
| `index.css` | Global CSS. Defines Tailwind base/components/utilities layers plus CSS custom properties (design tokens) for colors, radius, sidebar dimensions, and chart palette in both light and dark themes. Also defines utility classes like `glass-card`, `glow-hover`, `pill-input`, and `animate-fade-in`. |
| `App.css` | Additional app-level CSS styles. |
| `vite-env.d.ts` | TypeScript declaration for Vite's `import.meta.env` types. |

---

## `src/pages/`

Page-level route components.

| File | Description |
|---|---|
| `Index.tsx` | Main application page (route `/`). Manages `activeTab` state (`chat`, `charts`, `insights`). Renders `AppSidebar`, `TopNav`, and conditionally renders `ChatView`, `ChartsView`, or `InsightsView` based on the active tab. Handles quick-action tab switching from the sidebar. |
| `NotFound.tsx` | 404 page (catch-all route `*`). Logs the attempted path to the console and displays a centered "404 – Page not found" message with a link back to home. |

---

## `src/components/`

Shared application-level React components.

| File | Description |
|---|---|
| `AppSidebar.tsx` | Left sidebar component. Displays the **TalkingBI** brand, a data-upload button, a database path input with a "Connect DB" button, and a 2×2 grid of quick-action buttons (Auto Insights, Trend Chart, Data Summary, Clean Data). Accepts `onQuickAction` and `activeTab` props to communicate tab changes upward to `Index`. |
| `TopNav.tsx` | Top navigation bar. Renders three tab buttons — **Chat**, **Charts**, and **Insights** — each with a Lucide icon. Highlights the active tab with primary color styling. Accepts `activeTab` and `onTabChange` props. |
| `ChatView.tsx` | Chat interface component. Manages a message list with user and AI messages. Displays a scrollable message thread with avatar icons, handles user input via a text field and send button, and simulates AI responses after an 800 ms delay using a `generateResponse` helper. |
| `ChartsView.tsx` | Analytics dashboard component. Displays KPI cards (Total Users, New Installs, Active Now, Avg. Session) and four Recharts-powered charts: a **Line Chart** (install/remove over time), a **Pie Chart** (OS share: Android vs iOS), a **Horizontal Bar Chart** (page traffic by section), and combined **Pie Charts** (gender and age distribution). Uses static sample data. |
| `InsightsView.tsx` | Auto-insights panel. Renders a list of four AI-generated insight cards covering Revenue Trend, Churn Risk, Engagement, and Growth Opportunity — each with a Lucide icon color-coded by insight type (positive, warning, info). |
| `NavLink.tsx` | A compatibility wrapper around React Router's `NavLink` that accepts simple `className`, `activeClassName`, and `pendingClassName` string props (instead of the function-based `className` API), merging them via `cn()`. |

---

## `src/components/ui/`

Reusable, unstyled-first UI primitives generated by **shadcn/ui** on top of Radix UI. Each file exports one or more composable React components.

| File | Description |
|---|---|
| `accordion.tsx` | Collapsible accordion sections (Radix `Accordion`). |
| `alert-dialog.tsx` | Modal confirmation dialogs with accessible focus management (Radix `AlertDialog`). |
| `alert.tsx` | Inline status alert banners with variant support (default, destructive). |
| `aspect-ratio.tsx` | Maintains a fixed aspect ratio for child content (Radix `AspectRatio`). |
| `avatar.tsx` | User avatar with image and text fallback (Radix `Avatar`). |
| `badge.tsx` | Small label badges with variant styles (default, secondary, destructive, outline). |
| `breadcrumb.tsx` | Breadcrumb navigation trail with separator and ellipsis support. |
| `button.tsx` | Button component with size and variant props (default, destructive, outline, ghost, link). Uses `class-variance-authority`. |
| `calendar.tsx` | Date-picker calendar UI built on `react-day-picker`. |
| `card.tsx` | Card container with `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, and `CardFooter` sub-components. |
| `carousel.tsx` | Touch/drag-friendly carousel built on `embla-carousel-react`. |
| `chart.tsx` | Chart wrapper utilities for Recharts — provides `ChartContainer`, `ChartTooltip`, `ChartLegend`, and CSS variable-based color configuration. |
| `checkbox.tsx` | Accessible checkbox input (Radix `Checkbox`). |
| `collapsible.tsx` | Simple show/hide collapsible section (Radix `Collapsible`). |
| `command.tsx` | Command palette / combobox search UI built on `cmdk`. |
| `context-menu.tsx` | Right-click context menu (Radix `ContextMenu`). |
| `dialog.tsx` | Modal dialog overlay with header, description, and footer slots (Radix `Dialog`). |
| `drawer.tsx` | Slide-in drawer panel (built on `vaul` via shadcn/ui). |
| `dropdown-menu.tsx` | Dropdown menu with items, submenus, checkboxes, and radio groups (Radix `DropdownMenu`). |
| `form.tsx` | Form field wrappers integrating `react-hook-form` with accessible label, description, and error message components. |
| `hover-card.tsx` | Popover shown on hover (Radix `HoverCard`). |
| `input-otp.tsx` | One-time-password input built on the `input-otp` library. |
| `input.tsx` | Styled HTML `<input>` element. |
| `label.tsx` | Accessible form label (Radix `Label`). |
| `menubar.tsx` | Horizontal application menu bar with dropdowns (Radix `Menubar`). |
| `navigation-menu.tsx` | Accessible top-level navigation menu with animated indicators (Radix `NavigationMenu`). |
| `pagination.tsx` | Page navigation controls with previous/next and numbered page buttons. |
| `popover.tsx` | Generic popover anchored to a trigger element (Radix `Popover`). |
| `progress.tsx` | Progress bar indicator (Radix `Progress`). |
| `radio-group.tsx` | Radio button group with accessible selection (Radix `RadioGroup`). |
| `resizable.tsx` | Drag-to-resize panel layouts built on `react-resizable-panels`. |
| `scroll-area.tsx` | Custom scrollbar-styled scroll container (Radix `ScrollArea`). |
| `select.tsx` | Styled native-like select dropdown (Radix `Select`). |
| `separator.tsx` | Horizontal or vertical visual divider (Radix `Separator`). |
| `sheet.tsx` | Side-panel sheet (slide-in overlay, variant of `Dialog`). |
| `sidebar.tsx` | Full-featured collapsible sidebar system with mobile support, cookie-persisted state, and keyboard shortcut toggle. Used by the shadcn/ui sidebar pattern. |
| `skeleton.tsx` | Animated loading skeleton placeholder. |
| `slider.tsx` | Range slider input (Radix `Slider`). |
| `sonner.tsx` | Toast notification system using the `sonner` library, themed to match the app. |
| `switch.tsx` | Toggle switch input (Radix `Switch`). |
| `table.tsx` | Styled HTML table with `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`, and `TableCaption` sub-components. |
| `tabs.tsx` | Tab group with panel switching (Radix `Tabs`). |
| `textarea.tsx` | Styled `<textarea>` element. |
| `toast.tsx` | Toast notification primitives (Radix `Toast`) — used by the custom `useToast` hook. |
| `toaster.tsx` | Renders active toasts from the `useToast` hook into the DOM. |
| `toggle.tsx` | Pressable toggle button (Radix `Toggle`). |
| `toggle-group.tsx` | Group of mutually exclusive or multi-select toggle buttons (Radix `ToggleGroup`). |
| `tooltip.tsx` | Tooltip shown on hover/focus (Radix `Tooltip`). |
| `use-toast.ts` | Toast state manager for the Radix-based toast system — manages a queue of toasts with add/update/dismiss actions. |

---

## `src/hooks/`

Custom React hooks.

| File | Description |
|---|---|
| `use-mobile.tsx` | `useIsMobile()` hook. Uses `window.matchMedia` to reactively return `true` when the viewport width is below 768 px (mobile breakpoint). |
| `use-toast.ts` | Re-export / alias of the toast hook from `src/components/ui/use-toast.ts`. Provides `useToast()` and `toast()` for triggering notifications from anywhere in the app. |

---

## `src/lib/`

Utility functions.

| File | Description |
|---|---|
| `utils.ts` | Exports the `cn()` helper — combines `clsx` (conditional class names) and `tailwind-merge` (deduplicates conflicting Tailwind classes) into a single utility function used throughout the component library. |

---

## `src/test/`

Test infrastructure files.

| File | Description |
|---|---|
| `setup.ts` | Vitest global setup. Imports `@testing-library/jest-dom` for extended matchers and mocks `window.matchMedia` (required for components that use media queries in a jsdom environment). |
| `example.test.ts` | Placeholder unit test. Contains a single passing assertion (`expect(true).toBe(true)`) to verify that the test runner is configured correctly. |
