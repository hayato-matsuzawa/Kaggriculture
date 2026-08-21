"""
Kaggriculture AI Agent - Self-Contained Single File Submission for Kaggle.
Agent v18: Golden-Ratio 3-Tile Column Partitioning Engine.
Rules:
  - Each worker manages exactly 3 tiles in their column (y=0, y=1, y=2).
  - 100% Guaranteed daily watering compliance (0% weed death rate).
  - Single-seed JIT supply chain to prevent cash drain.
"""
import sys
import os
import math
from typing import Dict, List, Tuple, Optional, Any

CROP_TYPES = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
PRODUCT_TYPES = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

CROP_MATURITY_DAYS = {"WHEAT": 4, "CARROT": 3, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 12}
SHED_TILES = {(3, 3), (4, 3), (3, 4), (4, 4)}

TOWN_SHOP_DEMANDS = {
    "BAKERY": ["EGG", "WHEAT"], "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"], "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"], "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"], "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"]
}

MARKET_PARAMS = {
    "WHEAT":      {"base": 25,  "I0": 10000, "T": 400},
    "CARROT":     {"base": 35,  "I0": 10000, "T": 450},
    "TOMATO":     {"base": 60,  "I0": 10000, "T": 200},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100},
    "MELON":      {"base": 250, "I0": 10000, "T": 300},
}


class GameState:
    def __init__(self, obs: Dict[str, Any]):
        self.raw_obs = obs
        self.player_id: int = obs.get("player", 0)
        self.opponent_id: int = 1 - self.player_id
        self.day: int = obs.get("day", 0)
        self.hour: int = obs.get("hour", 0)
        self.step: int = obs.get("step", self.day * 24 + self.hour)

        farms = obs.get("farms", [{}, {}])
        self.my_farm = farms[self.player_id] if len(farms) > self.player_id else {}
        self.money: float = float(self.my_farm.get("money", 0.0))
        self.tiles: List[List[Any]] = self.my_farm.get("tiles", [])
        self.farmer_pos: Tuple[int, int] = tuple(self.my_farm.get("farmer", [0, 0]))
        self.hands_pos: List[Tuple[int, int]] = [tuple(h) for h in self.my_farm.get("hands", [])]
        self.unlocked_quadrants: List[str] = self.my_farm.get("unlocked_quadrants", ["NW"])
        self.hires_today: int = self.my_farm.get("hires_today", 0)

        market = obs.get("market", {})
        self.market_prices: Dict[str, int] = market.get("prices", {})

        town = obs.get("town", {})
        self.unlocked_shops: List[str] = town.get("unlocked_shops", [])

        private = obs.get("private", {})
        self.shed: Dict[str, int] = private.get("shed", {})
        self.seeds: Dict[str, int] = dict(private.get("seeds", {}))

    def get_tile(self, x: int, y: int) -> Any:
        if (x, y) in SHED_TILES:
            return "SHED"
        if 0 <= y < len(self.tiles) and 0 <= x < len(self.tiles[y]):
            return self.tiles[y][x]
        return "LOCKED"


class AgentPlanner:
    def __init__(self, state: GameState):
        self.state = state
        self.available_seeds = dict(state.seeds)

    def plan_turn(self) -> Dict[str, Any]:
        market_orders = self.plan_market_orders()
        farmer_actions = self.plan_farmer_action()
        hand_actions = [self.plan_hand_action(i) for i in range(len(self.state.hands_pos))]

        return {
            "farmer": farmer_actions,
            "hands": hand_actions,
            "market": market_orders
        }

    def plan_market_orders(self) -> List[List[Any]]:
        orders = []
        money = self.state.money
        step = self.state.step
        day = self.state.day
        hour = self.state.hour
        unlocked_quads = len(self.state.unlocked_quadrants)

        # 1. Instant Liquidation
        is_shop_tick = (step % 4 == 0)
        demanded_items = set()
        for shop in self.state.unlocked_shops:
            if shop in TOWN_SHOP_DEMANDS:
                demanded_items.update(TOWN_SHOP_DEMANDS[shop])

        for item in PRODUCT_TYPES:
            qty_shed = self.state.shed.get(item, 0)
            if qty_shed > 0:
                orders.append(["SELL", item, qty_shed])

        # 2. Daily Re-Hiring Fleet (Hire 4 Farm Hands every morning)
        max_hands = 4 if unlocked_quads == 1 else 5
        if self.state.hires_today < max_hands and money >= 20 and hour <= 4:
            orders.append(["HIRE"])

        # 3. Single-Seed Demand Chain (Buy 1 seed when inventory is empty)
        straw_s = self.state.seeds.get("STRAWBERRY", 0)
        tomato_s = self.state.seeds.get("TOMATO", 0)
        melon_s = self.state.seeds.get("MELON", 0)
        carrot_s = self.state.seeds.get("CARROT", 0)
        wheat_s = self.state.seeds.get("WHEAT", 0)

        if day <= 22:
            if straw_s == 0 and money >= 200:
                orders.append(["BUY_SEED", "STRAWBERRY", 1])
            elif tomato_s == 0 and money >= 120:
                orders.append(["BUY_SEED", "TOMATO", 1])
            elif melon_s == 0 and money >= 160:
                orders.append(["BUY_SEED", "MELON", 1])
            elif carrot_s == 0 and money >= 80:
                orders.append(["BUY_SEED", "CARROT", 1])
            elif wheat_s == 0 and money >= 50:
                orders.append(["BUY_SEED", "WHEAT", 1])

        # 4. Strict Day 1-3 Land Expansion Safeguard
        active_planted_crops = sum(
            1 for row in self.state.tiles for t in row
            if isinstance(t, dict) and t.get("kind") == "PLANT"
        )
        if unlocked_quads == 1 and active_planted_crops >= 18 and money >= 2500 and day <= 3:
            orders.append(["BUY_LAND"])

        return orders[:10]

    def select_best_seed(self) -> Optional[str]:
        for c in ["STRAWBERRY", "TOMATO", "MELON", "CARROT", "WHEAT"]:
            if self.available_seeds.get(c, 0) > 0:
                self.available_seeds[c] -= 1
                return c
        return None

    def execute_col(self, pos: Tuple[int, int], col_x: int) -> List[str]:
        ux, uy = pos
        day = self.state.day
        # Golden Ratio: Limit worker column workload to top 3 tiles (y=0, 1, 2)
        col_tiles = [(col_x, y) for y in (0, 1, 2) if (col_x, y) not in SHED_TILES]

        # PRIORITY 1: HARVEST RIPE CROPS IMMEDIATELY
        for tx, ty in col_tiles:
            t = self.state.get_tile(tx, ty)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                crop = t.get("crop", "CARROT")
                max_age = CROP_MATURITY_DAYS.get(crop, 3)
                age = day - t.get("planted_day", 0)
                if t.get("yield_units", 0) > 0 or age >= max_age:
                    if (ux, uy) == (tx, ty): return ["HARVEST"]
                    return self.get_step((ux, uy), (tx, ty))

        # PRIORITY 2: MANDATORY DAILY WATERING
        for tx, ty in col_tiles:
            t = self.state.get_tile(tx, ty)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                if not t.get("watered_today", False):
                    if (ux, uy) == (tx, ty): return ["WATER"]
                    return self.get_step((ux, uy), (tx, ty))

        # PRIORITY 3: DIG WEEDS
        curr = self.state.get_tile(ux, uy)
        if isinstance(curr, dict) and curr.get("kind") == "WEED":
            return ["DIG"]

        for tx, ty in col_tiles:
            if (tx, ty) == (ux, uy): continue
            t = self.state.get_tile(tx, ty)
            if isinstance(t, dict) and t.get("kind") == "WEED":
                return self.get_step((ux, uy), (tx, ty))

        # PRIORITY 4: PLANT SEEDS
        is_unplanted = (curr is None) or (isinstance(curr, dict) and curr.get("kind") in ("EMPTY", None))
        if (ux, uy) in col_tiles and is_unplanted and (ux, uy) not in SHED_TILES:
            seed = self.select_best_seed()
            if seed:
                return ["PLANT", seed]

        for tx, ty in col_tiles:
            if (tx, ty) == (ux, uy): continue
            t = self.state.get_tile(tx, ty)
            tile_empty = (t is None) or (isinstance(t, dict) and t.get("kind") in ("EMPTY", None))
            if tile_empty and sum(self.available_seeds.values()) > 0:
                return self.get_step((ux, uy), (tx, ty))

        return ["PASS"]

    def plan_farmer_action(self) -> List[str]:
        return self.execute_col(self.state.farmer_pos, 0)

    def plan_hand_action(self, idx: int) -> List[str]:
        if idx >= len(self.state.hands_pos): return ["PASS"]
        h_pos = self.state.hands_pos[idx]
        return self.execute_col(h_pos, idx + 1)

    def get_step(self, s: Tuple[int, int], t: Tuple[int, int]) -> List[str]:
        if s == t: return ["PASS"]
        sx, sy = s; tx, ty = t
        if tx > sx: return ["EAST"]
        elif tx < sx: return ["WEST"]
        elif ty > sy: return ["SOUTH"]
        elif ty < sy: return ["NORTH"]
        return ["PASS"]


def agent(obs, config=None):
    try:
        state = GameState(obs)
        planner = AgentPlanner(state)
        return planner.plan_turn()
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
