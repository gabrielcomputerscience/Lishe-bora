// Colours for the nutrition groups, from the AATF Brand Manual palette only (p.10).
export const GROUP_COLOUR: Record<string, string> = {
  "Cereal": "#AB822D", "Legume": "#507435", "Vegetable": "#75BA43", "Fruit": "#912E91", "Roots & tubers": "#AB822D",
  "Animal-source": "#912E91", "Oil": "#F9B916", "": "#6F7A66",
};
export const colourFor = (group: string) => GROUP_COLOUR[group] ?? GROUP_COLOUR[""];
