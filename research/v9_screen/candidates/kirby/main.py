_price_history = {"WHEAT": []}


def agent(obs):
    # --- Observation Extraction ---
    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    money = farm["money"]

    # Seeds and shed contents are inside obs["private"]
    private_obs = obs.get("private", {})
    wheat_seeds = private_obs.get("seeds", {}).get("WHEAT", 0)
    shed_wheat = private_obs.get("shed", {}).get("WHEAT", 0)

    # --- Market Price Lookup & Tracking ---
    market_data = obs.get("market", {})
    wheat_market = market_data.get("WHEAT", {})
    
    # Safely retrieve seed buy price (or fallback value if key varies)
    wheat_price = wheat_market.get("buy_seed_price", 10)

    if "WHEAT" not in _price_history:
        _price_history["WHEAT"] = []

    _price_history["WHEAT"].append(wheat_price)
    avg_price = sum(_price_history["WHEAT"]) / len(_price_history["WHEAT"])

    # --- Market Logic (BUY + SELL) ---
    market_action = []

    # Buy seeds
    if wheat_seeds < 7 and money >= 10:
        market_action.append(["BUY_SEED", "WHEAT", 1])

    # Optimal dynamic selling
    if shed_wheat >= 10 and wheat_price >= avg_price:
        market_action.append(["SELL", "WHEAT", shed_wheat])

    # --- Farmer position ---
    fx, fy = farm["farmer"]
    tile = tiles[fy][fx]

    # --- Yield lookup for age comparison ---
    first_yield = {
        "WHEAT": 2,
        "CARROT": 2,
        "TOMATO": 8,
        "STRAWBERRY": 10,
        "MELON": 10,
    }

    # --- Harvesting logic ---
    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        crop = tile["crop"]
        crop_age = obs["day"] - tile["planted_day"]

        if tile["yield_units"] > 0 and crop_age >= first_yield.get(crop, 2):
            return {"farmer": ["HARVEST"], "hands": [], "market": market_action}

    # --- Weed removal logic ---
    if isinstance(tile, dict) and tile.get("kind") in (
        "WEED",
        "WEED_PATCH",
        "WEED_SEEDLING",
        "WEED_ROOT",
    ):
        return {"farmer": ["REMOVE_WEED"], "hands": [], "market": market_action}

    # --- Watering logic ---
    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        if not tile["watered_today"]:
            return {"farmer": ["WATER"], "hands": [], "market": market_action}

    # --- Planting logic ---
    if tile is None and wheat_seeds > 0:
        return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": market_action}

    # --- Movement setup ---
    height = len(tiles)
    width = len(tiles[0])

    moves = [
        ("NORTH", fx, fy - 1),
        ("SOUTH", fx, fy + 1),
        ("WEST", fx - 1, fy),
        ("EAST", fx + 1, fy),
    ]

    # --- Scan adjacent tiles for harvestable plants ---
    for op, nx, ny in moves:
        if 0 <= nx < width and 0 <= ny < height:
            neighbor = tiles[ny][nx]
            if isinstance(neighbor, dict) and neighbor.get("kind") == "PLANT":
                crop = neighbor["crop"]
                crop_age = obs["day"] - neighbor["planted_day"]

                if neighbor["yield_units"] > 0 and crop_age >= first_yield.get(crop, 2):
                    return {"farmer": [op], "hands": [], "market": market_action}

    # --- Scan adjacent tiles for empty land ---
    for op, nx, ny in moves:
        if 0 <= nx < width and 0 <= ny < height:
            target_tile = tiles[ny][nx]
            if target_tile is None:
                return {"farmer": [op], "hands": [], "market": market_action}

    # --- Scan adjacent tiles for weeds ---
    for op, nx, ny in moves:
        if 0 <= nx < width and 0 <= ny < height:
            neighbor = tiles[ny][nx]
            if isinstance(neighbor, dict) and neighbor.get("kind") in (
                "WEED",
                "WEED_PATCH",
                "WEED_SEEDLING",
                "WEED_ROOT",
            ):
                return {"farmer": [op], "hands": [], "market": market_action}

    # --- Default action ---
    return {"farmer": ["PASS"], "hands": [], "market": market_action}
