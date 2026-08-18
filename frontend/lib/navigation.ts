export function safeReturnPath(value: string | string[] | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//") || candidate.includes("\\")) {
    return "/";
  }
  return candidate;
}

export function authPath(path: "/login" | "/register", next: string): string {
  return next === "/" ? path : `${path}?next=${encodeURIComponent(next)}`;
}
