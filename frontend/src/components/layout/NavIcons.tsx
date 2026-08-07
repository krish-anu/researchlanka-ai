/**
 * Nav glyphs as inline SVG.
 *
 * The Stitch screens call for Material Symbols, but that is a webfont fetched
 * from a third party on every page load. These are the same six concepts drawn
 * locally: no external request, no icon-font flash, and they inherit `stroke`
 * from the link so the active/inactive states need no per-icon styling.
 */

type IconProps = { className?: string };

function Frame({
  className = "",
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={`h-5 w-5 shrink-0 ${className}`}
    >
      {children}
    </svg>
  );
}

export function DashboardIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1" />
      <rect x="13.5" y="3" width="7.5" height="4.5" rx="1" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1" />
      <rect x="13.5" y="10.5" width="7.5" height="10.5" rx="1" />
    </Frame>
  );
}

export function PublicationsIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <path d="M5 3.5h9.5L19 8v12.5H5z" />
      <path d="M14.5 3.5V8H19" />
      <path d="M8 12.5h8M8 16h5.5" />
    </Frame>
  );
}

export function ResearchersIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
    </Frame>
  );
}

export function InstitutionsIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <path d="M3.5 9.5 12 4l8.5 5.5" />
      <path d="M6 10.5v7M10 10.5v7M14 10.5v7M18 10.5v7" />
      <path d="M3.5 20.5h17" />
    </Frame>
  );
}

export function TopicsIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <path d="M4 4h7l9 9-7 7-9-9z" />
      <circle cx="8" cy="8" r="1.4" />
    </Frame>
  );
}

export function DataQualityIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <ellipse cx="12" cy="6" rx="7" ry="2.75" />
      <path d="M5 6v11.5c0 1.5 3.1 2.75 7 2.75s7-1.25 7-2.75V6" />
      <path d="M5 11.75c0 1.5 3.1 2.75 7 2.75s7-1.25 7-2.75" />
    </Frame>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Frame>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Frame>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <Frame {...props}>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M15.5 15.5 21 21" />
    </Frame>
  );
}
