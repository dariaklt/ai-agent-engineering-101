import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
MARKET = BASE / ".market"

inventory = json.loads(
    (MARKET / "inventory.json").read_text(encoding="utf-8")
)

catalog = json.loads(
    (MARKET / "catalog.json").read_text(encoding="utf-8")
)

current = Counter(
    u["sku"]
    for u in inventory.get("units", [])
    if u.get("grade") != "expired"
)

sales = Counter()
profits = defaultdict(int)

log_file = BASE / "logs" / "market-kit.log"

if log_file.exists():
    pattern = re.compile(
        r"\[seller\] \[strategy\] ACCEPT "
        r"sku=(\S+) price=(\d+) cost=(\d+) profit=(-?\d+)"
    )

    for line in log_file.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():
        match = pattern.search(line)

        if not match:
            continue

        sku = match.group(1)
        profit = int(match.group(4))

        if profit > 0:
            sales[sku] += 1
            profits[sku] += profit

MAX_TOTAL_UNITS = 24

total_stock = sum(current.values())
max_new_units = max(0, MAX_TOTAL_UNITS - total_stock)

if max_new_units <= 0:
    print(json.dumps({"buy": []}))
    raise SystemExit

top_skus = sorted(
    sales,
    key=lambda sku: (sales[sku], profits[sku]),
    reverse=True,
)[:4]

candidates = []

for sku in top_skus:
    sold_count = sales[sku]
    product = catalog.get(sku)

    if not product:
        continue

    kind = product.get("kind", "goods")

    # Food is riskier because it expires.
    # Goods can safely have a slightly larger stock.
    target_stock = 2 if kind == "food" else 3

    # Proven repeat sellers may get one extra unit.
    if sold_count >= 3:
        target_stock += 1

    target_stock = min(target_stock, 4)

    need = max(0, target_stock - current.get(sku, 0))

    if need <= 0:
        continue

    try:
        list_price = int(product.get("list_price", 0))
    except (TypeError, ValueError):
        continue

    if list_price <= 0:
        continue

    candidates.append({
        "sku": sku,
        "need": need,
        "sales": sold_count,
        "profit": profits[sku],
        "list_price": list_price,
    })


# Best proven sellers first.
candidates.sort(
    key=lambda x: (x["sales"], x["profit"]),
    reverse=True,
)

balance = int(inventory.get("balance", 0))

# Conservative restock:
# max 10% of cash and never more than ~300k estimated cost.
restock_budget = min(
    int(balance * 0.10),
    300_000,
)

buy = []
units_planned = 0

for item in candidates:
    if units_planned >= max_new_units or restock_budget <= 0:
        break

    # Grade A can cost up to ~75% of list,
    # so use that as a conservative estimate.
    estimated_cost = max(
        1,
        int(item["list_price"] * 0.75),
    )

    affordable = restock_budget // estimated_cost

    qty = min(
        item["need"],
        2,
        max_new_units - units_planned,
        affordable,
    )

    if qty <= 0:
        continue

    buy.append({
        "sku": item["sku"],
        "qty": int(qty),
    })

    units_planned += qty
    restock_budget -= qty * estimated_cost


print(json.dumps({"buy": buy}))