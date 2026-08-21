"""Kaggriculture heuristic ROI-based agent.

Strategy: score crops/animals by profit-per-tile-day (or profit-per-day for
animals) using live market prices, with a concentration penalty that spreads
planting across crops instead of dumping everything into a single one. Each
turn, tile jobs (water/feed/harvest/care/weed/fertilizer-collect) are
assigned to the nearest idle unit, tier by tier in priority order. Leftover
units fall back to planting, animal logistics (build/place), or shed
logistics (pickup/drop).

Game constants below are duplicated from the environment's own tables
(documented in README.md / AGENTS.md) since a submission only ships main.py.
"""

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
PREMIUM_PRODUCTS = {"STRAWBERRY", "MELON", "MILK", "WOOL"}  # sell in small batches to avoid crashing price
SEASON_DAYS = 30
ANIMAL_CAP = 6
FIB_COSTS = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]

DIRS = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def step_toward(pos, target):
    dx, dy = target[0] - pos[0], target[1] - pos[1]
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy) and dx != 0:
        return "EAST" if dx > 0 else "WEST"
    return "SOUTH" if dy > 0 else "NORTH"


def shed_access_tiles(board_size):
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def crop_plan_yield(crop):
    cd = CROPS[crop]
    if cd["ongoing"]:
        total_yield = cd["max_yield"]
        occ_days = cd["first_yield_day"] + (cd["max_yield"] - 1) * cd["interval"] + 1
    else:
        window_start = (cd["max_yield_day"] + 1) // 2
        days_in_window = cd["max_yield_day"] - window_start + 1
        total_yield = min(cd["max_yield"], 1 + days_in_window)
        occ_days = cd["max_yield_day"] + 1
    return total_yield, occ_days


def crop_score(crop, price, planted_count):
    total_yield, occ_days = crop_plan_yield(crop)
    profit = total_yield * price - CROPS[crop]["seed"]
    return (profit / max(1, occ_days)) / (1 + 0.2 * planted_count)


def animal_score(animal, product_price, wheat_price, placed_count, days_left):
    a = ANIMALS[animal]
    daily_profit = (product_price / a["interval"]) - wheat_price
    if daily_profit <= 0:
        return -1e9
    payback_days = a["cost"] / daily_profit
    if payback_days > days_left * 0.6:
        return -1e9
    return daily_profit / (1 + 0.3 * placed_count)


def agent(obs):
    player = obs["player"]
    farm = obs["farms"][player]
    private = obs["private"]
    market = obs["market"]
    day = obs["day"]
    hour = obs["hour"]
    tiles = farm["tiles"]
    board_size = len(tiles)
    prices = market["prices"]
    seeds = dict(private["seeds"])
    shed = private["shed"]
    days_left = max(1, SEASON_DAYS - day)
    shed_tiles = set(shed_access_tiles(board_size))

    units = [{"idx": 0, "pos": tuple(farm["farmer"])}]
    for hi, hp in enumerate(farm["hands"]):
        units.append({"idx": hi + 1, "pos": tuple(hp)})
    invs = private["inventories"]
    for u in units:
        u["inv"] = invs[u["idx"]] if u["idx"] < len(invs) else {}

    actions = {u["idx"]: None for u in units}

    water_jobs, feed_jobs, harvest_jobs = [], [], []
    care_jobs, weed_jobs, fert_collect_jobs = [], [], []
    planted_counts = {c: 0 for c in CROPS}
    placed_counts = {a: 0 for a in ANIMALS}
    empty_tiles = []
    empty_structures = {"COOP": [], "PASTURE": []}

    for y in range(board_size):
        for x in range(board_size):
            t = tiles[y][x]
            pos = (x, y)
            if t is None:
                empty_tiles.append(pos)
            elif t == "LOCKED":
                continue
            elif isinstance(t, dict):
                kind = t.get("kind")
                if kind == "PLANT":
                    planted_counts[t["crop"]] += 1
                    if not t["watered_today"]:
                        water_jobs.append(pos)
                    if t.get("yield_units", 0) > 0:
                        harvest_jobs.append(pos)
                elif kind == "WEED":
                    weed_jobs.append(pos)
                elif kind in ("COOP", "PASTURE"):
                    if "animal" in t:
                        placed_counts[t["animal"]] += 1
                        if not t["fed_today"]:
                            feed_jobs.append(pos)
                        elif not t["cared_today"]:
                            care_jobs.append(pos)
                        if t.get("yield_units", 0) > 0:
                            harvest_jobs.append(pos)
                        if t.get("fertilizer_available"):
                            fert_collect_jobs.append(pos)
                    else:
                        empty_structures[kind].append(pos)

    def assign_tier(jobs, make_action):
        pending = [u for u in units if actions[u["idx"]] is None]
        if not pending or not jobs:
            return
        pairs = sorted(
            ((manhattan(u["pos"], job), u, job) for u in pending for job in jobs),
            key=lambda p: p[0],
        )
        used_units, used_jobs = set(), set()
        for _, u, job in pairs:
            if u["idx"] in used_units or job in used_jobs:
                continue
            used_units.add(u["idx"])
            used_jobs.add(job)
            if u["pos"] == job:
                actions[u["idx"]] = make_action(u, job)
            else:
                actions[u["idx"]] = [step_toward(u["pos"], job)]

    assign_tier(water_jobs, lambda u, job: ["WATER"])
    assign_tier(feed_jobs, lambda u, job: ["FEED"])
    assign_tier(harvest_jobs, lambda u, job: ["HARVEST"])
    assign_tier(care_jobs, lambda u, job: ["CARE"])
    assign_tier(weed_jobs, lambda u, job: ["DIG"])
    assign_tier(fert_collect_jobs, lambda u, job: ["COLLECT_FERTILIZER"])

    # --- Planning for fallback (planting / animals / logistics) ---
    animal_candidates = sorted(
        ANIMALS,
        key=lambda a: -animal_score(a, prices[ANIMALS[a]["product"]], prices["WHEAT"], placed_counts[a], days_left),
    )
    best_animal = animal_candidates[0]
    best_animal_ok = (
        animal_score(best_animal, prices[ANIMALS[best_animal]["product"]], prices["WHEAT"], placed_counts[best_animal], days_left) > 0
    )
    want_more_animals = best_animal_ok and sum(placed_counts.values()) < ANIMAL_CAP and day <= 24
    needed_structure = ANIMALS[best_animal]["structure"] if want_more_animals else None
    structure_built_this_turn = False
    animal_placed_this_turn = False

    remaining_seeds = dict(seeds)
    local_planted_counts = dict(planted_counts)

    def best_crop_for_planting():
        scored = [(crop_score(c, prices[c], local_planted_counts[c]), c) for c in CROPS]
        scored.sort(reverse=True)
        return scored[0][1]

    for u in units:
        if actions[u["idx"]] is not None:
            continue
        pos = u["pos"]
        x, y = pos
        t = tiles[y][x]
        inv = u["inv"]

        # 1. Carrying an animal: go place it (build structure first if needed).
        carried_animal = next((a for a in ANIMALS if inv.get(a, 0) > 0), None)
        if carried_animal:
            struct = ANIMALS[carried_animal]["structure"]
            if isinstance(t, dict) and t.get("kind") == struct and "animal" not in t:
                actions[u["idx"]] = ["PLACE", carried_animal]
                animal_placed_this_turn = True
                continue
            targets = empty_structures.get(struct, [])
            if targets:
                nearest = min(targets, key=lambda p: manhattan(pos, p))
                actions[u["idx"]] = [step_toward(pos, nearest)]
                continue
            if t is None:
                actions[u["idx"]] = [f"BUILD_{struct}"]
                structure_built_this_turn = True
                continue
            if empty_tiles:
                nearest = min(empty_tiles, key=lambda p: manhattan(pos, p))
                actions[u["idx"]] = [step_toward(pos, nearest)]
                continue

        # 2. Need a structure for the animal expansion plan and don't have one queued.
        if (
            needed_structure
            and not structure_built_this_turn
            and not empty_structures.get(needed_structure)
            and shed.get(best_animal, 0) == 0
        ):
            if t is None:
                actions[u["idx"]] = [f"BUILD_{needed_structure}"]
                structure_built_this_turn = True
                continue
            if empty_tiles:
                nearest = min(empty_tiles, key=lambda p: manhattan(pos, p))
                actions[u["idx"]] = [step_toward(pos, nearest)]
                continue

        # 3. Standing on empty tile: plant best-ROI crop if we have seed.
        if t is None:
            crop = best_crop_for_planting()
            if remaining_seeds.get(crop, 0) > 0:
                actions[u["idx"]] = ["PLANT", crop]
                remaining_seeds[crop] -= 1
                local_planted_counts[crop] += 1
                continue

        # 4. Shed-adjacent logistics: drop harvest, pick up wheat/fertilizer/animal.
        if pos in shed_tiles:
            if inv:
                actions[u["idx"]] = ["DROP"]
                continue
            if (
                needed_structure
                and not animal_placed_this_turn
                and shed.get(best_animal, 0) > 0
            ):
                actions[u["idx"]] = ["PICKUP", best_animal, 1]
                continue
            if shed.get("WHEAT", 0) > 0 and sum(placed_counts.values()) > 0:
                actions[u["idx"]] = ["PICKUP", "WHEAT", min(5, shed["WHEAT"])]
                continue
            if shed.get("FERTILIZER", 0) > 0:
                actions[u["idx"]] = ["PICKUP", "FERTILIZER", min(5, shed["FERTILIZER"])]
                continue

        # 5. Otherwise navigate somewhere useful.
        if t is None:
            actions[u["idx"]] = ["PASS"]
            continue
        if empty_tiles:
            nearest = min(empty_tiles, key=lambda p: manhattan(pos, p))
            actions[u["idx"]] = [step_toward(pos, nearest)]
            continue
        nearest_shed = min(shed_tiles, key=lambda p: manhattan(pos, p))
        actions[u["idx"]] = [step_toward(pos, nearest_shed)] if pos != nearest_shed else ["PASS"]

    # --- Market orders ---
    orders = []

    for product, stock in shed.items():
        if product not in prices or stock <= 0:
            continue
        if product == "WHEAT":
            keep = 3 * max(1, sum(placed_counts.values()))
            qty = max(0, stock - keep)
        else:
            cap = 4 if product in PREMIUM_PRODUCTS else stock
            qty = min(stock, cap)
        if qty > 0:
            orders.append(["SELL", product, qty])

    money = farm["money"]
    top_crops = sorted(CROPS, key=lambda c: -crop_score(c, prices[c], local_planted_counts[c]))[:2]
    for crop in top_crops:
        desired = min(3, len(empty_tiles) + 1)
        shortfall = desired - remaining_seeds.get(crop, 0)
        cost = CROPS[crop]["seed"]
        buy_n = 0
        while shortfall > buy_n and money - cost > 300:
            money -= cost
            buy_n += 1
        if buy_n > 0:
            orders.append(["BUY_SEED", crop, buy_n])

    if sum(placed_counts.values()) > 0:
        feed_buffer = 3 * sum(placed_counts.values())
        have = shed.get("WHEAT", 0)
        if have < feed_buffer and money - prices["WHEAT"] > 300:
            buy_n = min(10, feed_buffer - have)
            orders.append(["BUY_PRODUCT", "WHEAT", buy_n])
            money -= buy_n * prices["WHEAT"]

    if money > 800 and shed.get("FERTILIZER", 0) < 3:
        orders.append(["BUY_PRODUCT", "FERTILIZER", 1])
        money -= prices["FERTILIZER"]

    if want_more_animals and shed.get(best_animal, 0) == 0 and money - ANIMALS[best_animal]["cost"] > 300:
        orders.append(["BUY_ANIMAL", best_animal, 1])
        money -= ANIMALS[best_animal]["cost"]

    if hour == 0 and day <= 26:
        desired_hands = min(3, 1 + len(farm["unlocked_quadrants"]))
        n_hired = farm["hires_today"]
        while n_hired < desired_hands:
            cost = FIB_COSTS[min(n_hired, len(FIB_COSTS) - 1)]
            if money - cost < 300:
                break
            orders.append(["HIRE"])
            money -= cost
            n_hired += 1

    n_unlocked_extra = len(farm["unlocked_quadrants"]) - 1
    land_prices = [1000, 2000, 4000]
    if n_unlocked_extra < 3:
        next_cost = land_prices[n_unlocked_extra]
        total_unlocked_tiles = board_size * board_size * len(farm["unlocked_quadrants"]) // 4
        free_ratio = len(empty_tiles) / max(1, total_unlocked_tiles)
        if free_ratio < 0.15 and money - next_cost * 1.5 > 0 and day <= 24:
            orders.append(["BUY_LAND"])
            money -= next_cost

    orders = orders[:10]

    farmer_action = actions[0] or ["PASS"]
    hand_actions = [actions.get(i + 1) or ["PASS"] for i in range(len(farm["hands"]))]

    return {"farmer": farmer_action, "hands": hand_actions, "market": orders}
