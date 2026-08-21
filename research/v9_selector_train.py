from __future__ import annotations

import argparse
import base64
import itertools
import json
import math
import re
import statistics
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import GroupKFold
from sklearn.tree import DecisionTreeClassifier

CANDIDATES = ("unseen_current", "cok", "sota_claude")
GROUPS = ("public_v18_live", "mid_teacher_holdout")


@dataclass(frozen=True)
class Config:
    decision: int
    kind: str
    params: tuple[tuple[str, Any], ...]

    @property
    def kwargs(self) -> dict[str, Any]:
        return dict(self.params)

    @property
    def name(self) -> str:
        tail = ",".join(f"{k}={v}" for k, v in self.params)
        return f"d{self.decision}:{self.kind}({tail})"


def load_decision(report_dir: Path, decision: int) -> dict[str, Any]:
    reports = {}
    for candidate in CANDIDATES:
        path = report_dir / f"hybrid-d{decision}-{candidate}.json"
        reports[candidate] = json.loads(path.read_text(encoding="utf-8"))
    bundles: dict[tuple[str, int, int], dict[str, Any]] = {}
    for candidate, report in reports.items():
        for row in report["rows"]:
            key = (str(row["group"]), int(row["episode_id"]), int(row["candidate_seat"]))
            bundle = bundles.setdefault(key, {"features": row["features"], "rows": {}})
            if json.dumps(bundle["features"], sort_keys=True) != json.dumps(row["features"], sort_keys=True):
                raise RuntimeError(f"feature mismatch at {key}")
            bundle["rows"][candidate] = row
    missing = [key for key, b in bundles.items() if set(b["rows"]) != set(CANDIDATES)]
    if missing:
        raise RuntimeError(f"candidate rows missing: {missing[:3]}")
    keys = sorted(bundles)
    feature_names = sorted({name for b in bundles.values() for name in b["features"]})
    X = np.asarray([[float(bundles[k]["features"].get(f, 0.0) or 0.0) for f in feature_names] for k in keys], dtype=np.float64)
    margins = np.asarray([[float(bundles[k]["rows"][c]["margin"]) for c in CANDIDATES] for k in keys], dtype=np.float64)
    valid = np.asarray([[bool(bundles[k]["rows"][c]["valid"]) for c in CANDIDATES] for k in keys], dtype=bool)
    if not valid.all():
        raise RuntimeError("invalid hybrid rows in training set")
    return {
        "decision": decision,
        "keys": keys,
        "feature_names": feature_names,
        "X": X,
        "margins": margins,
        "groups": np.asarray([k[0] for k in keys], dtype=object),
        "episodes": np.asarray([k[1] for k in keys], dtype=np.int64),
        "seats": np.asarray([k[2] for k in keys], dtype=np.int64),
    }


def sample_weights(margins: np.ndarray) -> np.ndarray:
    ordered = np.sort(margins, axis=1)
    gap = ordered[:, -1] - ordered[:, -2]
    best = ordered[:, -1]
    second = ordered[:, -2]
    decisive = ((best > 0) & (second <= 0)).astype(np.float64)
    scale = np.median(np.abs(margins)) + 1.0
    return 1.0 + np.clip(gap / scale, 0.0, 10.0) + 3.0 * decisive


def make_estimator(config: Config):
    p = config.kwargs
    if config.kind == "dtc":
        return DecisionTreeClassifier(random_state=1729, class_weight="balanced", **p)
    if config.kind == "rfc":
        return RandomForestClassifier(n_estimators=160, random_state=1729, n_jobs=-1, class_weight="balanced_subsample", **p)
    if config.kind == "etc":
        return ExtraTreesClassifier(n_estimators=200, random_state=1729, n_jobs=-1, class_weight="balanced", **p)
    if config.kind == "rfr":
        return RandomForestRegressor(n_estimators=180, random_state=1729, n_jobs=-1, **p)
    if config.kind == "etr":
        return ExtraTreesRegressor(n_estimators=220, random_state=1729, n_jobs=-1, **p)
    raise ValueError(config.kind)


def fit_predict(config: Config, X_train: np.ndarray, M_train: np.ndarray, X_test: np.ndarray) -> np.ndarray:
    if config.kind == "constant":
        return np.full(len(X_test), int(config.kwargs["candidate"]), dtype=np.int64)
    estimator = make_estimator(config)
    if config.kind in ("dtc", "rfc", "etc"):
        y = np.argmax(M_train, axis=1)
        estimator.fit(X_train, y, sample_weight=sample_weights(M_train))
        return estimator.predict(X_test).astype(np.int64)
    estimator.fit(X_train, M_train)
    prediction = np.asarray(estimator.predict(X_test), dtype=np.float64)
    return np.argmax(prediction, axis=1).astype(np.int64)


def folds_for(data: dict[str, Any]) -> list[dict[str, Any]]:
    groups = data["groups"]
    episodes = data["episodes"]
    folds = []
    a = np.flatnonzero(groups == GROUPS[0]); b = np.flatnonzero(groups == GROUPS[1])
    folds.append({"name": "public_to_mid", "train": a, "test": b, "domain": True})
    folds.append({"name": "mid_to_public", "train": b, "test": a, "domain": True})
    unique_episodes = np.unique(episodes)
    splitter = GroupKFold(n_splits=min(5, len(unique_episodes)))
    for i, (tr, te) in enumerate(splitter.split(data["X"], groups=episodes)):
        folds.append({"name": f"episode_cv_{i}", "train": tr, "test": te, "domain": False})
    for group in GROUPS:
        idx = np.flatnonzero(groups == group)
        ue = sorted(set(int(episodes[i]) for i in idx))
        cut = max(1, min(len(ue) - 1, round(0.70 * len(ue))))
        early, late = set(ue[:cut]), set(ue[cut:])
        tr = np.asarray([i for i in idx if int(episodes[i]) in early], dtype=np.int64)
        te = np.asarray([i for i in idx if int(episodes[i]) in late], dtype=np.int64)
        if len(tr) and len(te): folds.append({"name": f"{group}_early_to_late", "train": tr, "test": te, "domain": False})
        tr2, te2 = te, tr
        if len(tr2) and len(te2): folds.append({"name": f"{group}_late_to_early", "train": tr2, "test": te2, "domain": False})
    return folds


def evaluate_config(config: Config, data: dict[str, Any]) -> dict[str, Any]:
    X, M = data["X"], data["margins"]
    rows = []
    all_selected = []
    for fold in folds_for(data):
        pred = fit_predict(config, X[fold["train"]], M[fold["train"]], X[fold["test"]])
        realized = M[fold["test"], pred]
        row = {
            "name": fold["name"],
            "domain": bool(fold["domain"]),
            "n": int(len(realized)),
            "wins": int(np.sum(realized > 0)),
            "win_rate": float(np.mean(realized > 0)),
            "mean_margin": float(np.mean(realized)),
            "min_margin": float(np.min(realized)),
        }
        rows.append(row)
        all_selected.extend(realized.tolist())
    domain = [r for r in rows if r["domain"]]
    secondary = [r for r in rows if not r["domain"]]
    complexity = {"constant": 0, "dtc": 1, "rfc": 3, "etc": 3, "rfr": 4, "etr": 4}[config.kind]
    score = (
        min(r["win_rate"] for r in domain),
        sum(r["wins"] for r in domain) / max(1, sum(r["n"] for r in domain)),
        statistics.mean(r["win_rate"] for r in secondary),
        min(r["win_rate"] for r in secondary),
        float(np.mean(all_selected)),
        -complexity,
    )
    return {"config": config.name, "decision": config.decision, "kind": config.kind, "params": config.kwargs, "folds": rows, "score": list(score)}


def configs(decisions: list[int]) -> list[Config]:
    result = []
    for decision in decisions:
        for c in range(len(CANDIDATES)):
            result.append(Config(decision, "constant", (("candidate", c),)))
        for depth in (1, 2, 3, 4, 5):
            for leaf in (2, 4, 6, 10):
                result.append(Config(decision, "dtc", tuple(sorted({"max_depth": depth, "min_samples_leaf": leaf}.items()))))
        for kind in ("rfc", "etc"):
            for depth in (2, 3, 4, 5, None):
                for leaf in (2, 4, 7, 10):
                    for mf in ("sqrt", 0.5, 1.0):
                        result.append(Config(decision, kind, tuple(sorted({"max_depth": depth, "min_samples_leaf": leaf, "max_features": mf}.items()))))
        for kind in ("rfr", "etr"):
            for depth in (2, 3, 4, 5, None):
                for leaf in (2, 4, 7, 10):
                    for mf in ("sqrt", 0.5, 1.0):
                        result.append(Config(decision, kind, tuple(sorted({"max_depth": depth, "min_samples_leaf": leaf, "max_features": mf}.items()))))
    return result


def export_tree(tree: Any, classifier: bool) -> dict[str, Any]:
    value = tree.value
    leaves = {}
    for node in range(tree.node_count):
        if tree.children_left[node] == tree.children_right[node]:
            if classifier:
                leaves[str(node)] = [float(x) for x in value[node][0]]
            else:
                leaves[str(node)] = [float(x[0]) for x in value[node]]
    return {
        "left": [int(x) for x in tree.children_left],
        "right": [int(x) for x in tree.children_right],
        "feature": [int(x) for x in tree.feature],
        "threshold": [float(x) for x in tree.threshold],
        "leaves": leaves,
    }


def fit_and_export(config: Config, data: dict[str, Any]) -> dict[str, Any]:
    X, M = data["X"], data["margins"]
    if config.kind == "constant":
        return {"kind": "constant", "candidate": int(config.kwargs["candidate"])}
    estimator = make_estimator(config)
    if config.kind in ("dtc", "rfc", "etc"):
        y = np.argmax(M, axis=1)
        estimator.fit(X, y, sample_weight=sample_weights(M))
        estimators = [estimator] if config.kind == "dtc" else list(estimator.estimators_)
        return {"kind": "forest_classifier", "classes": [int(x) for x in estimator.classes_], "trees": [export_tree(e.tree_, True) for e in estimators]}
    estimator.fit(X, M)
    return {"kind": "forest_regressor", "trees": [export_tree(e.tree_, False) for e in estimator.estimators_]}


def compressed_literal(text: str) -> str:
    return base64.b85encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")


def build_main(candidate_dir: Path, feature_names: list[str], decision: int, model: dict[str, Any]) -> str:
    sources = {name: compressed_literal((candidate_dir / name / "main.py").read_text(encoding="utf-8")) for name in CANDIDATES}
    payload = compressed_literal(json.dumps({"features": feature_names, "decision": decision, "model": model}, separators=(",", ":")))
    source_json = json.dumps(sources, separators=(",", ":"))
    return f'''# Kaggriculture V9 meta-selector\n# Common opening and selector trained only on pre-newest disjoint replay periods.\nimport base64\nimport copy\nimport json\nimport zlib\n\n_CANDIDATES={CANDIDATES!r}\n_SOURCES={source_json}\n_MODEL_B85={payload!r}\n_STATE={{0:{{"selected":None}},1:{{"selected":None}}}}\n_AGENTS={{}}\n\ndef _get(o,k,d=None):\n    try:return o.get(k,d)\n    except Exception:\n        try:return getattr(o,k)\n        except Exception:return d\n\ndef _load():\n    global _AGENTS,_SPEC\n    if _AGENTS:return\n    _SPEC=json.loads(zlib.decompress(base64.b85decode(_MODEL_B85)).decode())\n    for seat in (0,1):\n        _AGENTS[seat]={{}}\n        for name,blob in _SOURCES.items():\n            ns={{}};src=zlib.decompress(base64.b85decode(blob)).decode()\n            exec(compile(src,"<embedded-"+name+"-"+str(seat)+">","exec"),ns)\n            fn=ns.get("agent")\n            if not callable(fn):raise RuntimeError("missing agent "+name)\n            _AGENTS[seat][name]=fn\n\ndef _call(fn,obs,configuration):\n    try:\n        try:r=fn(obs,configuration)\n        except TypeError:r=fn(obs)\n        return copy.deepcopy(r) if isinstance(r,dict) else {{"farmer":["PASS"],"hands":[],"market":[]}}\n    except Exception:\n        return {{"farmer":["PASS"],"hands":[],"market":[]}}\n\ndef _num_map(x):\n    if not isinstance(x,dict):return {{}}\n    out={{}}\n    for k,v in x.items():\n        try:out[str(k)]=float(v or 0)\n        except Exception:out[str(k)]=0.0\n    return out\n\ndef _farm(prefix,farm,out):\n    farm=farm if isinstance(farm,dict) else {{}}\n    out[prefix+".money"]=float(farm.get("money",0) or 0);hands=farm.get("hands",[]) or []\n    out[prefix+".hands"]=float(len(hands));out[prefix+".hires_today"]=float(farm.get("hires_today",0) or 0);out[prefix+".lands"]=float(len(farm.get("unlocked_quadrants",[]) or []))\n    ps=[farm.get("farmer")]+list(hands);xs=[];ys=[]\n    for p in ps:\n        if isinstance(p,(list,tuple)) and len(p)>=2:xs.append(float(p[0]));ys.append(float(p[1]))\n    out[prefix+".pos_x_mean"]=sum(xs)/max(1,len(xs));out[prefix+".pos_y_mean"]=sum(ys)/max(1,len(ys));out[prefix+".pos_x_span"]=(max(xs)-min(xs)) if xs else 0.0;out[prefix+".pos_y_span"]=(max(ys)-min(ys)) if ys else 0.0\n    counts={{}};ysum=watered=unwatered=fed=unfed=cared=uncared=fert=0.0\n    for row in farm.get("tiles",[]) or []:\n        for tile in row or []:\n            if tile is None:key="EMPTY"\n            elif tile=="LOCKED":key="LOCKED"\n            elif isinstance(tile,dict):\n                key=str(tile.get("kind") or "DICT");crop=tile.get("crop");animal=tile.get("animal")\n                if crop:counts["CROP:"+str(crop)]=counts.get("CROP:"+str(crop),0)+1\n                if animal:counts["ANIMAL:"+str(animal)]=counts.get("ANIMAL:"+str(animal),0)+1\n                try:ysum+=float(tile.get("yield_units",0) or 0)\n                except Exception:pass\n                if key=="PLANT":\n                    if tile.get("watered_today"):watered+=1\n                    else:unwatered+=1\n                if animal:\n                    if tile.get("fed_today"):fed+=1\n                    else:unfed+=1\n                    if tile.get("cared_today"):cared+=1\n                    else:uncared+=1\n                    fert+=float(bool(tile.get("fertilizer_available")))\n            else:key="OTHER"\n            counts[key]=counts.get(key,0)+1\n    for key in ("EMPTY","LOCKED","WEED","PLANT","COOP","PASTURE"):out[prefix+".tile."+key]=float(counts.get(key,0))\n    for crop in ("WHEAT","CARROT","TOMATO","STRAWBERRY","MELON"):out[prefix+".crop."+crop]=float(counts.get("CROP:"+crop,0))\n    for animal in ("GOOSE","COW","SHEEP"):out[prefix+".animal."+animal]=float(counts.get("ANIMAL:"+animal,0))\n    out[prefix+".yield_sum"]=ysum;out[prefix+".watered"]=watered;out[prefix+".unwatered"]=unwatered;out[prefix+".fed"]=fed;out[prefix+".unfed"]=unfed;out[prefix+".cared"]=cared;out[prefix+".uncared"]=uncared;out[prefix+".fertilizer_available"]=fert\n\ndef _features(obs):\n    pid=int(_get(obs,"player",0) or 0);farms=list(_get(obs,"farms",[]) or []);me=farms[pid] if pid<len(farms) else {{}};opp=farms[1-pid] if len(farms)>=2 else {{}}\n    out={{"seat":float(pid),"step":float(_get(obs,"step",0) or 0),"day":float(_get(obs,"day",0) or 0),"hour":float(_get(obs,"hour",0) or 0)}};_farm("self",me,out);_farm("opp",opp,out)\n    out["diff.money"]=out["self.money"]-out["opp.money"];out["diff.hands"]=out["self.hands"]-out["opp.hands"];out["diff.lands"]=out["self.lands"]-out["opp.lands"]\n    market=_get(obs,"market",{{}}) or {{}};prices=_num_map(market.get("prices",{{}}) if isinstance(market,dict) else {{}});inventory=_num_map(market.get("inventory",{{}}) if isinstance(market,dict) else {{}})\n    for item in ("WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"):out["price."+item]=prices.get(item,0.0);out["market_inventory."+item]=inventory.get(item,0.0)\n    town=_get(obs,"town",{{}}) or {{}};shops=list(town.get("unlocked_shops",[]) or []) if isinstance(town,dict) else [];out["shop_count"]=float(len(shops))\n    for shop in ("BAKERY","PIZZA_SHOP","BRUNCH_SPOT","YARN_STORE","ICE_CREAM_SHOP","PET_CAFE","SMOOTHIE_SHOP","FARMERS_MARKET"):out["shop."+shop]=float(shops.count(shop))\n    private=_get(obs,"private",{{}}) or {{}};shed=_num_map(private.get("shed",{{}}) if isinstance(private,dict) else {{}});seeds=_num_map(private.get("seeds",{{}}) if isinstance(private,dict) else {{}});carried={{}}\n    for inv in (private.get("inventories",[]) if isinstance(private,dict) else []) or []:\n        for item,v in _num_map(inv).items():carried[item]=carried.get(item,0.0)+v\n    for item in ("WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER","GOOSE","COW","SHEEP"):out["shed."+item]=shed.get(item,0.0);out["carried."+item]=carried.get(item,0.0)\n    for crop in ("WHEAT","CARROT","TOMATO","STRAWBERRY","MELON"):out["seed."+crop]=seeds.get(crop,0.0)\n    return out\n\ndef _leaf(tree,x):\n    node=0;left=tree["left"];right=tree["right"];feature=tree["feature"];threshold=tree["threshold"];leaves=tree["leaves"]\n    while str(node) not in leaves:\n        node=left[node] if x[feature[node]]<=threshold[node] else right[node]\n    return leaves[str(node)]\n\ndef _predict(x):\n    m=_SPEC["model"];kind=m["kind"]\n    if kind=="constant":return int(m["candidate"])\n    if kind=="forest_classifier":\n        scores=[0.0]*len(_CANDIDATES);classes=m["classes"]\n        for tree in m["trees"]:\n            v=_leaf(tree,x);total=sum(v) or 1.0\n            for i,c in enumerate(classes):scores[c]+=v[i]/total\n        return max(range(len(scores)),key=lambda i:scores[i])\n    scores=[0.0]*len(_CANDIDATES)\n    for tree in m["trees"]:\n        v=_leaf(tree,x)\n        for i in range(len(scores)):scores[i]+=v[i]\n    return max(range(len(scores)),key=lambda i:scores[i])\n\ndef agent(obs,configuration=None):\n    _load();pid=int(_get(obs,"player",0) or 0);step=int(_get(obs,"step",0) or 0)\n    if step==0:_STATE[pid]={{"selected":None}}\n    actions={{name:_call(_AGENTS[pid][name],obs,configuration) for name in _CANDIDATES if _STATE[pid]["selected"] is None}}\n    if _STATE[pid]["selected"] is not None:return _call(_AGENTS[pid][_STATE[pid]["selected"]],obs,configuration)\n    decision=int(_SPEC["decision"])\n    if step<decision:return actions["unseen_current"]\n    f=_features(obs);x=[float(f.get(n,0.0)) for n in _SPEC["features"]];choice=_predict(x);name=_CANDIDATES[choice];_STATE[pid]["selected"]=name\n    return actions[name]\n'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hybrid-reports", type=Path, required=True)
    ap.add_argument("--candidate-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    decisions = sorted({int(m.group(1)) for p in args.hybrid_reports.glob("hybrid-d*-*.json") if (m := re.match(r"hybrid-d(\d+)-", p.name))})
    datasets = {d: load_decision(args.hybrid_reports, d) for d in decisions}
    results = []
    for i, config in enumerate(configs(decisions), 1):
        result = evaluate_config(config, datasets[config.decision]); results.append(result)
        if i % 100 == 0: print(f"evaluated {i}/{len(configs(decisions))}", flush=True)
    results.sort(key=lambda r: tuple(r["score"]), reverse=True)
    winner_row = results[0]
    winner = next(c for c in configs(decisions) if c.name == winner_row["config"])
    data = datasets[winner.decision]
    model = fit_and_export(winner, data)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "main.py").write_text(build_main(args.candidate_dir, data["feature_names"], winner.decision, model), encoding="utf-8")
    report = {
        "selection_protocol": "No newest-holdout row was loaded. Hyperparameters selected by bidirectional era transfer, grouped episode CV, and temporal block CV.",
        "candidate_names": list(CANDIDATES),
        "decisions_considered": decisions,
        "winner": winner_row,
        "top_configs": results[:50],
        "model": model,
        "feature_names": data["feature_names"],
        "training_samples": len(data["keys"]),
        "training_episodes": len(set(int(x) for x in data["episodes"])),
    }
    (args.output_dir / "selector-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Kaggriculture V9 selector training", "", report["selection_protocol"], "", f"- Winner: `{winner.name}`", f"- Decision step: {winner.decision}", f"- Training samples: {report['training_samples']}", f"- Training episodes: {report['training_episodes']}", "", "## Cross-validation folds", "", "| Fold | Wins | N | Win rate | Mean margin | Min margin |", "|---|---:|---:|---:|---:|---:|"]
    for row in winner_row["folds"]:
        lines.append(f"| {row['name']} | {row['wins']} | {row['n']} | {100*row['win_rate']:.2f}% | {row['mean_margin']:.1f} | {row['min_margin']:.1f} |")
    (args.output_dir / "selector-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((args.output_dir / "selector-report.md").read_text(), flush=True)


if __name__ == "__main__":
    main()
