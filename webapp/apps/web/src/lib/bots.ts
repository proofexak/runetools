/**
 * One colour per bot, fixed across every chart and filter: bots are ranked by name over
 * every bot ever logged (not the ones in view), so filtering never repaints a survivor.
 * Slots follow the validated categorical order (dataviz reference palette, checked
 * against this app's card surfaces in both modes); bots past the 8th share "Other".
 */
const LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
const DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const OTHER = { light: "#898781", dark: "#898781" };

export function botColors(allBots: string[], dark: boolean): Map<string, string> {
  const slots = dark ? DARK : LIGHT;
  const sorted = [...new Set(allBots)].sort();
  return new Map(sorted.map((b, i) => [b, slots[i] ?? OTHER.light]));
}
