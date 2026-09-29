// Cut-out photos of the survey foods (public/foods), keyed by commodity code. Used by the homepage food showcase.
const f = (n: string) => `/foods/${n}.webp`;
export const FOOD_IMAGE: Record<string, string> = {
  "RICE-BROWN": f("brown-rice"), MILLET: f("millet"), SORGHUM: f("sorghum"),
  "MAIZE-FLOUR": f("maize-flour"), "WHEAT-FLOUR": f("wheat-flour"), "RICE-WHITE": f("white-rice"),
  GITHERI: f("githeri"), PORRIDGE: f("porridge"),
  BEANS: f("beans"), COWPEAS: f("cowpeas"), "GREEN-GRAMS": f("green-grams"), "PIGEON-PEAS": f("pigeon-peas"),
  AMARANTH: f("amaranth"), SPINACH: f("spinach"), "SUKUMA-WIKI": f("sukuma-wiki"),
  CABBAGE: f("cabbage"), CARROTS: f("carrots"), ONIONS: f("onions"), TOMATOES: f("tomatoes"),
  BANANAS: f("bananas"), MANGOES: f("mangoes"), ORANGES: f("oranges"),
  CASSAVA: f("cassava"), "SWEET-POTATOES": f("sweet-potatoes"), YAMS: f("yams"),
  EGGS: f("eggs"), MILK: f("milk"), BEEF: f("beef"), "GOAT-MEAT": f("goat"), POULTRY: f("poultry"), FISH: f("fish"),
};
