"""What a crop rotation needs to know about each crop: whether it is
perennial (orchards, vineyards, berries: they are not rotated), its botanical
family (two crops of one family in a row share pests and diseases) and its
role in a rotation (cereal, legume, break crop, cover crop).
Plain data, no network: crops of the catalogue (crops.json) by id; FAO
EcoCrop plants by their EcoCrop data sheet (life span / life form / family).
"""

# perennial crops of the catalogue: they stay for years, so no rotation
PERENNIAL = frozenset((
    "peach", "nectarine", "plum", "cherry", "apple", "pear", "apricot", "table_grape",
    "wine_grape", "blueberry", "raspberry", "strawberry", "avocado", "walnut", "almond",
    "hazelnut", "olive", "lemon", "orange", "mandarin", "kiwi", "alfalfa"))

# botanical family of the catalogue's annual crops
FAMILY = {
    "wheat": "Poaceae", "barley": "Poaceae", "oat": "Poaceae", "maize": "Poaceae",
    "rice": "Poaceae", "ryegrass": "Poaceae", "quinoa": "Amaranthaceae",
    "sugar_beet": "Amaranthaceae", "canola": "Brassicaceae", "lupin": "Fabaceae",
    "bean": "Fabaceae", "chickpea": "Fabaceae", "lentil": "Fabaceae", "pea": "Fabaceae",
    "alfalfa": "Fabaceae", "red_clover": "Fabaceae", "vetch": "Fabaceae",
    "potato": "Solanaceae", "tomato": "Solanaceae", "onion": "Amaryllidaceae",
    "garlic": "Amaryllidaceae", "lettuce": "Asteraceae", "sunflower": "Asteraceae",
    "pumpkin": "Cucurbitaceae", "hemp": "Cannabaceae",
}

# roles in a rotation
CEREAL = "cereal"
LEGUME = "legume"
BREAK = "break"
# what comes after each role in a rotation: a legume feeds the next cereal
# with nitrogen; a break crop cuts the cereals' pests and diseases
NEXT_ROLE = {CEREAL: LEGUME, LEGUME: CEREAL, BREAK: CEREAL, None: CEREAL}
# the role after the next one (third season)
THIRD_ROLE = {CEREAL: BREAK, LEGUME: BREAK, BREAK: LEGUME, None: LEGUME}

# cover crops sown between the rows of perennial crops: a legume (nitrogen)
# and a grass (soil structure, erosion)
COVER_LEGUMES = ("vetch", "red_clover")
COVER_GRASSES = ("oat", "barley", "ryegrass")


# (str crop_id, CropInfo info = None)
# True for crops that stay for years (orchards, vines, berries, alfalfa)
def is_perennial(crop_id, info=None):
    if crop_id in PERENNIAL:
        return True
    if crop_id in FAMILY or info is None:
        return False
    text = f"{info.life_span} {info.life_form}".lower()
    return "perennial" in text or "tree" in text or "shrub" in text


# (str crop_id, CropInfo info = None)
# the botanical family ("Fabaceae"), or "" when unknown
def family_of(crop_id, info=None):
    return FAMILY.get(crop_id) or (info.family if info is not None else "") or ""
