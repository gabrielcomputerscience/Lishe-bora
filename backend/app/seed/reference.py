"""Programme reference data (real data supplied by the programme team, not demo data).

FOOD_CATEGORIES: the 16 food categories from the school survey (Food_Categories_foodcat.xlsx), each with its food items.
    Every food item becomes a commodity. `group` is the broader nutrition group the menu-diversity rules count
    (SystemSetting "nutrition.rules"); that mapping is a platform default for nutrition officers to confirm.
SAMPLED_SCHOOLS: the 32 sampled schools (Schools-Sampled.xlsx) in Makueni, Embu and Isiolo, with their sub-counties.
    The file has no official school codes, so the platform assigns codes in file order (MAKUENI-SCH001 ...). Replace them
    with NEMIS codes when available by editing them under Master data.
    Contact persons and phone numbers are personal data (Data Protection Act, 2019). They are not seeded; they are in
    docs/data/school_contacts_for_import.csv, to import as user accounts once the school heads have agreed."""

# (key, label as in the survey, nutrition group, [(commodity code, food item, unit)])
FOOD_CATEGORIES = [
    ("whole_grains", "Whole grains", "Cereal", [("SORGHUM", "Sorghum", "kg"), ("MILLET", "Millet", "kg"), ("RICE-BROWN", "Brown rice", "kg")]),
    ("refined_grains", "Refined grains", "Cereal", [("RICE-WHITE", "White rice", "kg"), ("MAIZE-FLOUR", "Maize flour", "kg"),
                                                    ("WHEAT-FLOUR", "Wheat flour", "kg")]),
    ("blended_grain_foods", "Blended grain-based foods", "Cereal", [("GITHERI", "Githeri", "kg"), ("PORRIDGE", "Porridge", "kg")]),
    ("legumes", "Legumes", "Legume", [("BEANS", "Beans", "kg"), ("COWPEAS", "Cowpeas", "kg"), ("PIGEON-PEAS", "Pigeon peas", "kg"),
                                      ("GREEN-GRAMS", "Green grams", "kg")]),
    ("green_leafy_vegetables", "Green leafy vegetables", "Vegetable", [("SUKUMA-WIKI", "Sukuma wiki", "kg"), ("AMARANTH", "Amaranth", "kg"),
                                                                       ("SPINACH", "Spinach", "kg")]),
    ("other_vegetables", "Other vegetables", "Vegetable", [("CABBAGE", "Cabbages", "kg"), ("CARROTS", "Carrots", "kg"),
                                                           ("TOMATOES", "Tomatoes", "kg"), ("ONIONS", "Onions", "kg")]),
    ("fruits", "Fruits", "Fruit", [("BANANAS", "Bananas", "kg"), ("ORANGES", "Oranges", "kg"), ("MANGOES", "Mangoes", "kg")]),
    ("roots_tubers", "Roots and tubers", "Roots & tubers", [("CASSAVA", "Cassava", "kg"), ("SWEET-POTATOES", "Sweet potatoes", "kg"),
                                                            ("YAMS", "Yams", "kg")]),
    ("eggs", "Eggs", "Animal-source", [("EGGS", "Eggs", "tray")]),
    ("milk_dairy", "Milk/Dairy products", "Animal-source", [("MILK", "Milk", "litre")]),
    ("meat", "Meat", "Animal-source", [("BEEF", "Beef", "kg"), ("GOAT-MEAT", "Goat", "kg"), ("POULTRY", "Poultry", "kg")]),
    ("fish", "Fish", "Animal-source", [("FISH", "Fish", "kg")]),
    ("processed_meats", "Processed meats", "Animal-source", [("SAUSAGES", "Sausages", "kg")]),
    ("cooking_oil", "Cooking oil", "Oil", [("COOKING-OIL", "Cooking oil", "litre")]),
    ("fats", "Fats", "Oil", [("MARGARINE", "Margarine", "kg"), ("BUTTER", "Butter", "kg")]),
    ("salt", "Salt", "", [("SALT", "Salt", "kg")]),
]
CATEGORY_LABELS = {k: label for k, label, _g, _i in FOOD_CATEGORIES}

# Commodity codes used by earlier development builds. The seed deactivates them (never deletes: old records keep their links).
LEGACY_DEMO_COMMODITIES = ["MZE-G1", "RICE", "BEAN-RC", "GGRAM", "VEG-LEAFY", "VEG-CAB", "FRUIT-BAN", "OIL-VEG"]

COUNTIES = [("MAKUENI", "Makueni County"), ("EMBU", "Embu County"), ("ISIOLO", "Isiolo County")]

# (county code, sub-county, school code, school name) in the order of the source file
SAMPLED_SCHOOLS = [
    ("MAKUENI", "Kibwezi West", "MAKUENI-SCH001", "Kalulini"),
    ("MAKUENI", "Kibwezi West", "MAKUENI-SCH002", "Muatini"),
    ("MAKUENI", "Kibwezi West", "MAKUENI-SCH003", "Mukononi"),
    ("MAKUENI", "Kibwezi West", "MAKUENI-SCH004", "Yikivala"),
    ("MAKUENI", "Kibwezi West", "MAKUENI-SCH005", "Kibwezi Township"),
    ("MAKUENI", "Kambu", "MAKUENI-SCH006", "Kyambusia"),
    ("MAKUENI", "Kambu", "MAKUENI-SCH007", "Ngwata"),
    ("MAKUENI", "Kambu", "MAKUENI-SCH008", "Kivuthini"),
    ("MAKUENI", "Kambu", "MAKUENI-SCH009", "Usalama"),
    ("MAKUENI", "Kaiti", "MAKUENI-SCH010", "Kisyungi"),
    ("MAKUENI", "Kaiti", "MAKUENI-SCH011", "Ukia Primary"),
    ("MAKUENI", "Kaiti", "MAKUENI-SCH012", "Kauomi Primary"),
    ("MAKUENI", "Makueni", "MAKUENI-SCH013", "Nthangu Primary & Junior School"),
    ("MAKUENI", "Makueni", "MAKUENI-SCH014", "Nziu Mixed Day Primary"),
    ("MAKUENI", "Makueni", "MAKUENI-SCH015", "Kitichumu Primary School"),
    ("MAKUENI", "Makueni", "MAKUENI-SCH016", "Unoa Comprehensive School"),
    ("EMBU", "Mbeere South", "EMBU-SCH001", "Kabururi"),
    ("EMBU", "Mbeere South", "EMBU-SCH002", "Kaurari"),
    ("EMBU", "Mbeere South", "EMBU-SCH003", "Kamukunga"),
    ("EMBU", "Mbeere South", "EMBU-SCH004", "Gitungati"),
    ("EMBU", "Mbeere North", "EMBU-SCH005", "Murangu"),
    ("EMBU", "Mbeere North", "EMBU-SCH006", "Kiathambu"),
    ("EMBU", "Mbeere North", "EMBU-SCH007", "Karimari"),
    ("EMBU", "Mbeere North", "EMBU-SCH008", "Kathutheri"),
    ("ISIOLO", "Isiolo", "ISIOLO-SCH001", "Kawalash"),
    ("ISIOLO", "Isiolo", "ISIOLO-SCH002", "Lenguluma"),
    ("ISIOLO", "Isiolo", "ISIOLO-SCH003", "Ngaremara"),
    ("ISIOLO", "Isiolo", "ISIOLO-SCH004", "Akadeli"),
    ("ISIOLO", "Garbatulla", "ISIOLO-SCH005", "Daawa"),
    ("ISIOLO", "Garbatulla", "ISIOLO-SCH006", "Nagaa"),
    ("ISIOLO", "Garbatulla", "ISIOLO-SCH007", "Galmadidio"),
    ("ISIOLO", "Garbatulla", "ISIOLO-SCH008", "Yaqbarsadhi"),
]
