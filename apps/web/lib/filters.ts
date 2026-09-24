type SearchableResource = { status?: string; [key: string]: unknown };

export function filterResources<T extends SearchableResource>(
  items: T[],
  query: string,
  status: string,
): T[] {
  const normalizedQuery = query.trim().toLocaleLowerCase("ro");
  return items.filter((item) => {
    if (status && item.status !== status) return false;
    if (!normalizedQuery) return true;
    return JSON.stringify(item).toLocaleLowerCase("ro").includes(normalizedQuery);
  });
}
