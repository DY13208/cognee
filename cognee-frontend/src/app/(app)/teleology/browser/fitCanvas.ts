/** Fit actual rendered cards, including user offsets, to the available canvas. */
export function fitCanvasBounds(cards: Array<{ x: number; y: number; width: number; height: number }>, canvas: { width: number; height: number }) {
  if (!cards.length) return null;
  const left = Math.min(...cards.map(card => card.x));
  const top = Math.min(...cards.map(card => card.y));
  const right = Math.max(...cards.map(card => card.x + card.width));
  const bottom = Math.max(...cards.map(card => card.y + card.height));
  const screenWidth = Math.max(1, canvas.width), screenHeight = Math.max(1, canvas.height);
  const padding = Math.min(40, screenWidth * .1, screenHeight * .1);
  const scale = Math.min((screenWidth - padding * 2) / Math.max(1, right - left), (screenHeight - padding * 2) / Math.max(1, bottom - top));
  const width = screenWidth / scale, height = screenHeight / scale;
  return { width, height, offsetX: (width - (right - left)) / 2 - left, offsetY: (height - (bottom - top)) / 2 - top };
}
