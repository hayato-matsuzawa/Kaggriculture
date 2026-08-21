"""Lean, conservative Kaggriculture controller.

The farm backbone is an 8-cow/4-sheep high-throughput route.  The adaptive
layer is deliberately narrow: repair weed-blocked productive actions, move an
already-planned premium-product sale forward by exactly one turn when no town
demand occurs, repay that move on the original turn, and bank/liquidate only at
the very end.  Worker inventories are never treated as directly sellable.
"""
import base64
import copy
import json
import math
import zlib


# Lean 8-cow/4-sheep route selected after comparing the two stronger public
# candidates. The payload is data only; the adaptive wrapper below is ours.
_LEAN_ACTIONS = json.loads(zlib.decompress(base64.b64decode(
    (
    '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'
    )
)).decode("utf-8"))
_LEGACY_ACTIONS = _LEAN_ACTIONS
_REBALANCE_ACTIONS = _LEAN_ACTIONS
del _LEAN_ACTIONS
_PRICE_FLOOR = 1
_DEMAND_ALPHA = 0.25
_MARKET_PARAMS = {
    "WHEAT": (25, 10000, 400, "sqrt", 0.8, "log", 0.2),
    "CARROT": (35, 10000, 450, "log", 0.2, "sqrt", 0.7),
    "TOMATO": (60, 10000, 200, "linear", 0.4, "sqrt", 0.6),
    "STRAWBERRY": (120, 10000, 100, "sqrt", 0.7, "linear", 1.6),
    "MELON": (250, 10000, 300, "log", 0.2, "sq", 3.6),
    "EGG": (50, 10000, 332, "linear", 0.4, "log", 0.2),
    "MILK": (160, 10000, 122, "sqrt", 0.6, "linear", 1.6),
    "WOOL": (200, 10000, 105, "log", 0.2, "sq", 3.2),
    "FERTILIZER": (100, 10000, 200, "linear", 0.4, "linear", 0.4),
}
_SHOP_PRODUCTS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
_WEED_STATE = {0: {}, 1: {}}
_SALE_STATE = {0: {}, 1: {}}
_WEED_BLOCKED_OPS = {"BUILD_PASTURE", "BUILD_COOP", "PLANT", "PLACE"}
_PREMIUM_ITEMS = ("MELON", "MILK", "STRAWBERRY", "WOOL")
_TERMINAL_ROUTE_TURNS = 1
_TERMINAL_MIN_LOAD_VALUE = 300


def _get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(value, key, default)


def _regime(configuration):
    interval = int(_get(configuration, "townCenterSellInterval", 12) or 12)
    return "rebalance" if interval >= 24 else "legacy"


def _copy_action(action):
    action = copy.deepcopy(action or {})
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(order or ["PASS"]) for order in (action.get("hands") or [])],
        "market": [list(order) for order in (action.get("market") or [])],
    }


def _seat(obs):
    return 1 if int(_get(obs, "player", 0) or 0) == 1 else 0


def _farm(obs, seat):
    farms = list(_get(obs, "farms", []) or [])
    return farms[seat] if seat < len(farms) else {}


def _align_hands(action, obs):
    action = _copy_action(action)
    expected = len(_get(_farm(obs, _seat(obs)), "hands", []) or [])
    hands = list(action.get("hands") or [])
    if len(hands) < expected:
        hands.extend([["PASS"] for _ in range(expected - len(hands))])
    action["hands"] = [list(order or ["PASS"]) for order in hands[:expected]]
    return action


def _tile_at(farm, position):
    try:
        x, y = int(position[0]), int(position[1])
        return (_get(farm, "tiles", []) or [])[y][x]
    except (IndexError, TypeError, ValueError):
        return "LOCKED"


def _weed_repair_action(obs, action, actions, step):
    action = _align_hands(action, obs)
    seat = _seat(obs)
    game = _WEED_STATE[seat]
    day = _positive_count(_get(obs, "day", step // 24))
    previous_day = game.get("day") if game else None
    if (
        not game
        or step == 0
        or step <= game.get("last_step", -1)
    ):
        game = {"last_step": step, "day": day, "pending": {}}
        _WEED_STATE[seat] = game
    elif day != previous_day:
        # Hired hands disappear at day end, so their actor indices cannot keep
        # delayed actions.  The permanent farmer (index 0) persists and keeps
        # its queue across the boundary.
        farmer_queue = game.get("pending", {}).get(0)
        game["pending"] = {0: farmer_queue} if farmer_queue else {}
    game["last_step"] = step
    game["day"] = day

    # Preserve the last two turns for endgame banking and liquidation.
    if step >= len(actions) - 2:
        return action

    farm = _farm(obs, seat)
    positions = [_get(farm, "farmer"), *list(_get(farm, "hands", []) or [])]
    unit_actions = [action.get("farmer", ["PASS"]), *list(action.get("hands") or [])]
    pending = game["pending"]

    for index, (position, intended) in enumerate(zip(positions, unit_actions)):
        intended = list(intended) if isinstance(intended, list) and intended else ["PASS"]
        queue = pending.get(index)
        if queue:
            unit_actions[index] = list(queue.pop(0))
            if intended[0] != "PASS":
                queue.append(intended)
            if queue:
                pending[index] = queue
            else:
                pending.pop(index, None)
            continue
        if intended[0] not in _WEED_BLOCKED_OPS:
            continue
        tile = _tile_at(farm, position)
        if not isinstance(tile, dict) or tile.get("kind") != "WEED":
            continue
        pending[index] = [intended]
        unit_actions[index] = ["DIG"]

    action["farmer"] = unit_actions[0] if unit_actions else ["PASS"]
    action["hands"] = unit_actions[1:]
    return _align_hands(action, obs)


def _shape(name, value):
    value = max(0.0, float(value))
    if name == "linear":
        return value
    if name == "sq":
        return value * value
    if name == "sqrt":
        return math.sqrt(value)
    if name == "log":
        return math.log1p(value)
    if name == "log10":
        return math.log10(1.0 + value)
    raise ValueError(name)


def _market_parameters(item, configuration=None):
    names = (
        "base", "I0", "T", "below_func", "below_target",
        "above_func", "above_target",
    )
    values = list(_MARKET_PARAMS[item])
    configured = _get(configuration, "marketParams", {}) or {}
    override = _get(configured, item, {}) or {}
    for index, name in enumerate(names):
        value = _get(override, name, None)
        if value is not None:
            values[index] = value
    return values


def _market_price(item, inventory, configuration=None):
    base, equilibrium, scale, below_func, below_target, above_func, above_target = (
        _market_parameters(item, configuration)
    )
    base = float(base)
    equilibrium = int(equilibrium)
    scale = max(1.0, float(scale))
    below_target = float(below_target)
    above_target = float(above_target)
    if inventory < equilibrium:
        amplitude = below_target * base / _shape(below_func, scale)
        price = base + amplitude * _shape(below_func, equilibrium - inventory)
    else:
        amplitude = above_target * base / _shape(above_func, scale)
        price = base - amplitude * _shape(above_func, inventory - equilibrium)
    return max(_PRICE_FLOOR, int(round(price)))


def _is_sell(order):
    return (
        isinstance(order, (list, tuple))
        and len(order) >= 3
        and order[0] == "SELL"
        and order[1] in _MARKET_PARAMS
    )


def _impact_score(obs, order, configuration=None):
    if not _is_sell(order):
        return float("-inf")
    item = str(order[1])
    try:
        quantity = max(0, int(order[2]))
    except (TypeError, ValueError):
        return 0.0
    market = _get(obs, "market", {}) or {}
    inventory = _get(market, "inventory", {}) or {}
    prices = _get(market, "prices", {}) or {}
    current_inventory = int(_get(inventory, item, 10000) or 0)
    current_quote = float(
        _get(
            prices,
            item,
            _market_price(item, current_inventory, configuration),
        ) or 0
    )
    later_quote = float(
        _market_price(item, current_inventory + quantity, configuration)
    )
    return float(quantity) * max(0.0, current_quote - later_quote)


def _demand_per_day(obs, configuration, item):
    town = _get(obs, "town", {}) or {}
    shops = list(_get(town, "unlocked_shops", []) or [])
    turns_per_day = int(_get(configuration, "turnsPerDay", 24) or 24)
    shop_interval = max(
        1, int(_get(configuration, "townShopSellInterval", 4) or 4)
    )
    demand = 0.0
    for shop in shops:
        products = _SHOP_PRODUCTS.get(shop, ())
        if item in products:
            demand += (turns_per_day / shop_interval) * (
                2 if len(products) == 1 else 1
            )
    regime = _regime(configuration)
    if item != "FERTILIZER":
        center_default = 24 if regime == "rebalance" else 12
        center_interval = max(
            1,
            int(
                _get(configuration, "townCenterSellInterval", center_default)
                or center_default
            ),
        )
        day = int(_get(obs, "day", int(_get(obs, "step", 0) or 0) // 24) or 0)
        multiplier = (
            1
            if regime == "rebalance"
            else (4 if day >= 20 else 2 if day >= 10 else 1)
        )
        demand += (turns_per_day / center_interval) * multiplier
    return demand


def _order_score(obs, configuration, order):
    score = _impact_score(obs, order, configuration)
    if _regime(configuration) != "rebalance" or score <= 0 or not _is_sell(order):
        return score
    item = str(order[1])
    quantity = max(0, int(order[2]))
    market = _get(obs, "market", {}) or {}
    inventory = _get(market, "inventory", {}) or {}
    current_inventory = int(_get(inventory, item, 10000) or 0)
    demand = max(0.25, _demand_per_day(obs, configuration, item))
    excess = max(0.0, current_inventory + quantity - 10000)
    urgency = min(1.0, (excess / demand) / 10.0)
    return score * (1.0 + _DEMAND_ALPHA * urgency)


def _rank_sell_slots(obs, action, configuration):
    action = _copy_action(action)
    market = list(action.get("market") or [])
    rows = [
        (_order_score(obs, configuration, order), -index, list(order))
        for index, order in enumerate(market)
        if _is_sell(order)
    ]
    if len(rows) < 2:
        return action
    rows.sort(reverse=True)
    ranked = iter(row[2] for row in rows)
    action["market"] = [next(ranked) if _is_sell(order) else order for order in market]
    return action


def _positive_count(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _isolated_sale_revenue(obs, configuration, order):
    """Exact own-order revenue if no concurrent opponent order hits this item."""
    if not _is_sell(order):
        return 0
    item = str(order[1])
    quantity = _positive_count(order[2])
    market = _get(obs, "market", {}) or {}
    inventories = _get(market, "inventory", {}) or {}
    quotes = _get(market, "prices", {}) or {}
    inventory = _positive_count(_get(inventories, item, 10000))
    revenue = 0
    for unit in range(quantity):
        if unit == 0:
            price = _positive_count(
                _get(
                    quotes,
                    item,
                    _market_price(item, inventory, configuration),
                )
            )
        else:
            price = _market_price(item, inventory, configuration)
        price = max(_PRICE_FLOOR, int(price))
        revenue += price
        # At the price floor, the engine buys the unit without increasing the
        # market inventory.  Future units therefore remain responsive to buys.
        if price > _PRICE_FLOOR:
            inventory += 1
    return revenue


def _shed_products(obs):
    """Return product counts that SELL can actually access this turn."""
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    return {
        item: _positive_count(_get(shed, item, 0))
        for item in _MARKET_PARAMS
        if _positive_count(_get(shed, item, 0)) > 0
    }


def _episode_steps(configuration):
    return max(1, _positive_count(_get(configuration, "episodeSteps", 720)) or 720)


def _is_final_action(obs, configuration):
    # Kaggle's episodeSteps includes the initial state, hence the last action is
    # normally numbered episodeSteps - 2 (718 for the standard 720-step game).
    step = _positive_count(_get(obs, "step", 0))
    return step >= max(0, _episode_steps(configuration) - 2)


def _shed_access(farm):
    size = len(_get(farm, "tiles", []) or []) or 10
    half = size // 2
    return {
        (half - 1, half - 1), (half, half - 1),
        (half - 1, half), (half, half),
    }


def _position(value):
    try:
        return int(value[0]), int(value[1])
    except (IndexError, TypeError, ValueError):
        return None


def _inventory_value(obs, inventory):
    prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
    return sum(
        _positive_count(count) * _positive_count(_get(prices, item, 1))
        for item, count in (inventory or {}).items()
        if item in _MARKET_PARAMS
    )


def _route_to_shed(position, sheds, farm):
    """Return one legal Manhattan step toward a shed-access tile."""
    if position is None or not sheds:
        return ["PASS"]
    x, y = position
    target = min(
        sheds,
        key=lambda q: (abs(q[0] - x) + abs(q[1] - y), q[1], q[0]),
    )
    tx, ty = target
    candidates = []
    if tx < x:
        candidates.append(("WEST", (x - 1, y)))
    if tx > x:
        candidates.append(("EAST", (x + 1, y)))
    if ty < y:
        candidates.append(("NORTH", (x, y - 1)))
    if ty > y:
        candidates.append(("SOUTH", (x, y + 1)))
    tiles = _get(farm, "tiles", []) or []
    size = len(tiles)
    for operation, (nx, ny) in candidates:
        if 0 <= nx < size and 0 <= ny < size:
            return [operation]
    return ["PASS"]


def _terminal_bank(obs, action, configuration):
    """Route valuable reachable loads to the shed during the final window."""
    step = _positive_count(_get(obs, "step", 0))
    final_step = max(0, _episode_steps(configuration) - 2)
    first_route_step = max(0, final_step - _TERMINAL_ROUTE_TURNS)
    if step < first_route_step or step >= final_step:
        return action
    action = _align_hands(action, obs)
    farm = _farm(obs, _seat(obs))
    positions = [_get(farm, "farmer"), *list(_get(farm, "hands", []) or [])]
    inventories = list(
        _get(_get(obs, "private", {}) or {}, "inventories", []) or []
    )
    unit_actions = [action["farmer"], *action["hands"]]
    sheds = _shed_access(farm)
    turns_remaining = final_step - step
    for index, position in enumerate(positions):
        inventory = inventories[index] if index < len(inventories) else {}
        load = sum(_positive_count(value) for value in (inventory or {}).values())
        pos = _position(position)
        if load <= 0 or pos is None or index >= len(unit_actions):
            continue
        if pos in sheds:
            unit_actions[index] = ["DROP"]
            continue
        distance = min(
            abs(pos[0] - target[0]) + abs(pos[1] - target[1])
            for target in sheds
        )
        value = _inventory_value(obs, inventory)
        scheduled = unit_actions[index] if unit_actions[index] else ["PASS"]
        safe_override = scheduled[0] == "PASS"
        if distance + 1 <= turns_remaining and (
            value >= _TERMINAL_MIN_LOAD_VALUE or safe_override
        ):
            unit_actions[index] = _route_to_shed(pos, sheds, farm)
    action["farmer"] = unit_actions[0]
    action["hands"] = unit_actions[1:]
    return action


def _terminal_liquidation(obs, action, configuration):
    step = _positive_count(_get(obs, "step", 0))
    final_step = max(0, _episode_steps(configuration) - 2)
    if step < max(0, final_step - _TERMINAL_ROUTE_TURNS):
        return action
    action = _copy_action(action)
    orders = [
        ["SELL", item, quantity]
        for item, quantity in _shed_products(obs).items()
    ]
    orders.sort(
        key=lambda order: (
            _isolated_sale_revenue(obs, configuration, order),
            _order_score(obs, configuration, order),
            order[1],
        ),
        reverse=True,
    )
    limit = _positive_count(
        _get(configuration, "maxMarketOrdersPerTurn", 10)
    ) or 10
    action["market"] = orders[:limit]
    return action


def _opening_feed_first(action, step):
    """Put the opening feed purchase before animals and hires."""
    if step != 0:
        return action
    action = _copy_action(action)
    market = action["market"]
    for index, order in enumerate(market):
        if len(order) >= 3 and order[:2] == ["BUY_PRODUCT", "WHEAT"]:
            action["market"] = [market[index], *market[:index], *market[index + 1:]]
            break
    return action


def _reduce_sale(action, item, quantity):
    """Repay a previous pull-forward without making any count negative."""
    remaining = _positive_count(quantity)
    market = []
    for raw in action.get("market", []) or []:
        order = list(raw)
        if remaining and _is_sell(order) and order[1] == item:
            sold = _positive_count(order[2])
            reduction = min(sold, remaining)
            sold -= reduction
            remaining -= reduction
            if sold == 0:
                continue
            order[2] = sold
        market.append(order)
    action["market"] = market
    return remaining


def _town_demand_now(obs, item, step, configuration):
    """Whether town demand will replenish this item after market actions."""
    turns_per_day = _positive_count(_get(configuration, "turnsPerDay", 24)) or 24
    center_interval = _positive_count(
        _get(configuration, "townCenterSellInterval", turns_per_day)
    ) or turns_per_day
    if item != "FERTILIZER" and step % center_interval == 0:
        return True
    shop_interval = _positive_count(
        _get(configuration, "townShopSellInterval", 4)
    ) or 4
    if step % shop_interval:
        return False
    town = _get(obs, "town", {}) or {}
    for shop in list(_get(town, "unlocked_shops", []) or []):
        if item in _SHOP_PRODUCTS.get(str(shop), ()):
            return True
    return False


def _pickup_reserve(action, item):
    """Stock needed by same-turn worker pickups before farm actions execute."""
    reserve = 0
    orders = [action.get("farmer", ["PASS"]), *list(action.get("hands") or [])]
    for order in orders:
        if (
            isinstance(order, (list, tuple))
            and len(order) >= 2
            and order[0] == "PICKUP"
            and order[1] == item
        ):
            reserve += _positive_count(order[2]) if len(order) >= 3 else 1
    return reserve


def _existing_sell(action, item):
    return sum(
        _positive_count(order[2])
        for order in (action.get("market", []) or [])
        if _is_sell(order) and order[1] == item
    )


def _premium_front_run(obs, action, actions, step, configuration):
    """Move only tomorrow's premium sales to today, then conserve quantity."""
    seat = _seat(obs)
    state = _SALE_STATE[seat]
    if not state or step == 0 or step <= state.get("last_step", -1):
        state = {"last_step": step, "debt": {}}
        _SALE_STATE[seat] = state
    state["last_step"] = step
    debt = state["debt"]
    action = _copy_action(action)

    due = dict(debt.pop(step, {}))
    for item, quantity in due.items():
        unpaid = _reduce_sale(action, item, quantity)
        if unpaid:
            following = debt.setdefault(step + 1, {})
            following[item] = following.get(item, 0) + unpaid

    final_step = max(0, _episode_steps(configuration) - 2)
    future_step = step + 1
    if (
        step >= final_step - 1
        or future_step >= len(actions)
    ):
        return action
    limit = _positive_count(
        _get(configuration, "maxMarketOrdersPerTurn", 10)
    ) or 10
    shed = _shed_products(obs)
    moved = {}
    for item in _PREMIUM_ITEMS:
        if _town_demand_now(obs, item, step, configuration):
            continue
        planned = sum(
            _positive_count(order[2])
            for order in (actions[future_step].get("market", []) or [])
            if _is_sell(order) and order[1] == item
        )
        if planned <= 0:
            continue
        committed = _existing_sell(action, item)
        available = max(
            0,
            shed.get(item, 0) - committed - _pickup_reserve(action, item),
        )
        quantity = min(planned, available)
        if quantity <= 0:
            continue
        existing = next(
            (
                order for order in action["market"]
                if _is_sell(order) and order[1] == item
            ),
            None,
        )
        if existing is not None:
            existing[2] = _positive_count(existing[2]) + quantity
        elif len(action["market"]) < limit:
            action["market"].append(["SELL", item, quantity])
        else:
            continue
        moved[item] = moved.get(item, 0) + quantity
    if moved:
        tomorrow = debt.setdefault(future_step, {})
        for item, quantity in moved.items():
            tomorrow[item] = tomorrow.get(item, 0) + quantity
    return action


def agent(obs, configuration=None):
    try:
        actions = (
            _REBALANCE_ACTIONS
            if _regime(configuration) == "rebalance"
            else _LEGACY_ACTIONS
        )
        step = min(max(0, int(_get(obs, "step", 0) or 0)), len(actions) - 1)
        action = _weed_repair_action(
            obs, _copy_action(actions[step]), actions, step
        )
        action = _opening_feed_first(action, step)
        action = _premium_front_run(
            obs, action, actions, step, configuration
        )
        action = _rank_sell_slots(obs, action, configuration)
        action = _terminal_bank(obs, action, configuration)
        action = _terminal_liquidation(obs, action, configuration)
        return _align_hands(action, obs)
    except Exception:
        farm = _farm(obs, _seat(obs))
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in (_get(farm, "hands", []) or [])],
            "market": [],
        }


def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
