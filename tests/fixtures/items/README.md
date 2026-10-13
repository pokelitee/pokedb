# Item API fixtures

`tm01.json` and `potion.json` are complete responses captured from the corresponding `https://pokeapi.co/api/v2/item/<name>/` endpoints on October 13, 2026. They exercise the current `prices` contract without the removed `cost` field, including versioned prices and an item with no price records. Tests read these snapshots offline.
