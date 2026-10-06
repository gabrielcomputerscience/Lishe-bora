// Font Awesome (free, solid) icons used on the public website. Bundled with the app: no external CDN, CSP-safe.
import {
  faAppleWhole, faBottleDroplet, faBowlFood, faBowlRice, faBreadSlice, faBullhorn, faCarrot, faCheese, faDrumstickBite, faEgg, faFish,
  faGlassWater, faHandHoldingHeart, faHotdog, faJar, faLandmark, faLeaf, faLocationDot, faLock, faMapLocationDot, faMobileScreen,
  faMoneyBillWave, faPeopleGroup, faPeopleRoof, faTruckFast, faChartLine, faUsers, faHandshake, faPepperHot, faQrcode, faScaleBalanced, faSchool, faSeedling, faWheatAwn, type IconDefinition,
} from "@fortawesome/free-solid-svg-icons";

export const FOOD_ICON: Record<string, IconDefinition> = {
  whole_grains: faWheatAwn, refined_grains: faBreadSlice, blended_grain_foods: faBowlRice, legumes: faSeedling,
  green_leafy_vegetables: faLeaf, other_vegetables: faPepperHot, fruits: faAppleWhole, roots_tubers: faCarrot, eggs: faEgg,
  milk_dairy: faGlassWater, meat: faDrumstickBite, fish: faFish, processed_meats: faHotdog, cooking_oil: faBottleDroplet,
  fats: faCheese, salt: faJar,
};
export const foodIcon = (key: string) => FOOD_ICON[key] ?? faBowlFood;
export const LIVE_ICON: Record<string, IconDefinition> = {
  schools: faSchool, counties: faMapLocationDot, suppliers: faPeopleGroup, foods: faBowlFood, opportunities: faBullhorn,
};
export { faHandHoldingHeart, faLandmark, faLocationDot, faLock, faMobileScreen, faMoneyBillWave, faQrcode, faScaleBalanced, faSchool, faWheatAwn };

/** Icon for a "Programme at a glance" figure, chosen from words in its label (the label is edited on the website). */
export function glanceIcon(label: string): IconDefinition {
  const l = label.toLowerCase();
  if (/school|learner|pupil|child/.test(l)) return faSchool;
  if (/women|youth|pwd|inclusi/.test(l)) return faHandHoldingHeart;
  if (/supplier|farmer|cooperative|producer/.test(l)) return faPeopleGroup;
  if (/local|sourced|food/.test(l)) return faSeedling;
  if (/deliver/.test(l)) return faTruckFast;
  if (/count/.test(l)) return faMapLocationDot;
  if (/paid|payment|kes|value/.test(l)) return faMoneyBillWave;
  return faChartLine;
}
