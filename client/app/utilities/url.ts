/** Map a message permalink (/arch/msg/<list>/<id>/) to its JSON API path. */
export function msgPermalinkToApi(url: string): string {
  return url.replace('/arch/msg/', '/arch/api/v1/msg/')
}
