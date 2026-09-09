"""
Capa de datos del backend. SQLite por ahora (cero instalación, misma SQL
que Postgres para lo que usamos); al desplegar se migra a Postgres
cambiando solo este archivo.

Los tests usan ':memory:' para no tocar el archivo real.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Optional

from .matching import Diet, RecipeRecord

Db = sqlite3.Connection


@dataclass
class SeedIngredient:
    name: str  # canónico, en inglés (lo que entiende Spoonacular), singular
    synonyms: list[str]  # alemán + variantes en inglés


@dataclass
class SeedRecipe:
    title: str
    diet: Diet
    ingredients: list[tuple[str, Optional[str]]]  # (nombre, cantidad)
    instructions: str


# Solo inglés y alemán (decisión de producto: nada en español).
# Los plurales ingleses los resuelve el singularizador naive ("potatoes",
# "eggs"); los alemanes van explícitos porque no terminan en s/es.
SEED_INGREDIENTS: list[SeedIngredient] = [
    SeedIngredient("potato", ["kartoffel", "kartoffeln"]),
    SeedIngredient("egg", ["ei", "eier"]),
    SeedIngredient("onion", ["zwiebel", "zwiebeln"]),
    SeedIngredient("salt", ["salz"]),
    SeedIngredient("pepper", ["pfeffer"]),
    SeedIngredient("olive oil", ["oil", "öl", "olivenöl"]),
    SeedIngredient("ground beef", ["hackfleisch", "faschiertes"]),
    SeedIngredient("breadcrumbs", ["breadcrumb", "semmelbrösel", "paniermehl"]),
    SeedIngredient("lentils", ["lentil", "linse", "linsen"]),
    SeedIngredient("carrot", ["karotte", "karotten", "möhre", "möhren"]),
    SeedIngredient("tomato", ["tomate", "tomaten"]),
    SeedIngredient("pasta", ["noodles", "nudel", "nudeln", "spaghetti"]),
    SeedIngredient("basil", ["basilikum"]),
    SeedIngredient("cheese", ["käse"]),
    SeedIngredient("rice", ["reis"]),
    SeedIngredient("mushrooms", ["mushroom", "pilz", "pilze", "champignons"]),
    SeedIngredient("chickpeas", ["chickpea", "kichererbse", "kichererbsen"]),
    SeedIngredient("lemon", ["zitrone", "zitronen"]),
    SeedIngredient("garlic", ["knoblauch"]),
    SeedIngredient("bell pepper", ["paprika"]),
    SeedIngredient("chicken", ["hähnchen", "huhn", "hühnchen"]),
    SeedIngredient("milk", ["milch"]),
    SeedIngredient("flour", ["mehl"]),
    SeedIngredient("butter", []),
]

SEED_RECIPES: list[SeedRecipe] = [
    SeedRecipe(
        "Kartoffel-Tortilla",
        "vegetarian",
        [("potato", "1 kg"), ("egg", "6"), ("onion", "1"), ("salt", None), ("olive oil", None)],
        "Peel and thinly slice the potatoes and onion. Fry them gently in olive oil until soft (about 15 min). Beat the eggs with salt, mix in the potatoes and onion, then pour back into the pan and cook over low heat until set on the bottom. Flip and cook the other side until golden.",
    ),
    SeedRecipe(
        "Schnitzel mit Kartoffelpüree",
        "mit_meat",
        [
            ("ground beef", "500 g"),
            ("breadcrumbs", None),
            ("egg", "2"),
            ("potato", "1 kg"),
            ("salt", None),
            ("pepper", None),
        ],
        "Shape the ground beef into flat patties, season with salt and pepper. Dip each patty in beaten egg, then coat with breadcrumbs. Fry until golden on both sides. Meanwhile, boil the potatoes until tender and mash with a splash of the cooking water. Serve together.",
    ),
    SeedRecipe(
        "Lentil Stew",
        "vegan",
        [
            ("lentils", "400 g"),
            ("onion", "1"),
            ("carrot", "2"),
            ("tomato", "2"),
            ("garlic", None),
            ("salt", None),
        ],
        "Sauté the chopped onion, carrot and garlic until fragrant. Add the diced tomato and cook a few minutes more. Stir in the lentils and enough water to cover, season with salt, and simmer for 25-30 min until the lentils are tender.",
    ),
    SeedRecipe(
        "Pasta al Pesto",
        "vegetarian",
        [
            ("pasta", "500 g"),
            ("basil", None),
            ("cheese", None),
            ("garlic", None),
            ("olive oil", None),
            ("salt", None),
        ],
        "Cook the pasta in salted water until al dente. Blend basil, cheese, garlic and olive oil into a smooth pesto. Drain the pasta, reserving a splash of cooking water, and toss with the pesto (loosen with the reserved water if needed).",
    ),
    SeedRecipe(
        "Mushroom Risotto",
        "vegetarian",
        [
            ("rice", "300 g"),
            ("mushrooms", "250 g"),
            ("onion", None),
            ("cheese", None),
            ("butter", None),
            ("salt", None),
        ],
        "Sauté the sliced mushrooms and chopped onion in butter until soft. Add the rice and toast briefly, then add hot water a ladle at a time, stirring often, until the rice is creamy and cooked through (about 18-20 min). Finish with cheese and salt to taste.",
    ),
    SeedRecipe(
        "Hummus",
        "vegan",
        [
            ("chickpeas", "400 g"),
            ("lemon", "1"),
            ("garlic", None),
            ("olive oil", None),
            ("salt", None),
        ],
        "Blend the chickpeas, lemon juice, garlic, olive oil and salt until smooth, adding a little water if it's too thick. Taste and adjust the lemon and salt, then serve drizzled with extra olive oil.",
    ),
    SeedRecipe(
        "Roast Chicken with Potatoes",
        "mit_meat",
        [
            ("chicken", "1"),
            ("potato", "1 kg"),
            ("bell pepper", None),
            ("onion", None),
            ("olive oil", None),
            ("salt", None),
            ("pepper", None),
        ],
        "Toss the quartered potatoes, bell pepper and onion with olive oil, salt and pepper in a roasting tray. Season the chicken well and place on top. Roast at 200°C for about 1 hour, basting occasionally, until the chicken is cooked through and the vegetables are golden.",
    ),
    SeedRecipe(
        "Gemüse-Wok",
        "vegan",
        [
            ("carrot", None),
            ("bell pepper", None),
            ("onion", None),
            ("mushrooms", None),
            ("olive oil", None),
            ("salt", None),
        ],
        "Heat the olive oil in a wok or large pan until very hot. Stir-fry the sliced carrot first for a couple of minutes, then add onion, bell pepper and mushrooms. Keep tossing over high heat until crisp-tender, season with salt to taste.",
    ),
    SeedRecipe(
        "Pfannkuchen",
        "vegetarian",
        [("flour", "250 g"), ("milk", "500 ml"), ("egg", "2"), ("butter", None), ("salt", None)],
        "Whisk the flour, milk, eggs and a pinch of salt into a smooth, thin batter. Melt a little butter in a pan over medium heat, pour in a thin layer of batter and cook until golden on both sides. Repeat with the rest of the batter.",
    ),
    SeedRecipe(
        "Rice Salad",
        "vegan",
        [
            ("rice", "200 g"),
            ("tomato", None),
            ("bell pepper", None),
            ("onion", None),
            ("lemon", None),
            ("olive oil", None),
            ("salt", None),
        ],
        "Cook the rice and let it cool. Dice the tomato, bell pepper and onion and mix them into the rice. Dress with olive oil, a squeeze of lemon and salt, then toss well and chill before serving.",
    ),
]


def create_db(filename: str) -> Db:
    if filename != ":memory:":
        os.makedirs(os.path.dirname(filename), exist_ok=True)

    # check_same_thread=False: a diferencia de better-sqlite3 (Node,
    # single-threaded), el sqlite3 de la stdlib restringe por defecto una
    # conexión a su hilo de creación. FastAPI puede ejecutar rutas sync en un
    # threadpool distinto al que arma la app, así que lo desactivamos —
    # nuestro acceso es simple (lecturas + un seed inicial), sin escrituras
    # concurrentes que puedan corromper datos.
    db = sqlite3.connect(filename, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingredients (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS ingredient_synonyms (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
          alias TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS recipes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          diet TEXT NOT NULL CHECK (diet IN ('vegan', 'vegetarian', 'mit_meat')),
          instructions TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
          recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
          ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
          quantity TEXT,
          PRIMARY KEY (recipe_id, ingredient_id)
        );
        """
    )
    db.commit()

    _migrate_instructions_column(db)
    _seed_if_empty(db)
    return db


def _migrate_instructions_column(db: Db) -> None:
    """Migración idempotente para bases ya sembradas antes de agregar
    `instructions`: agrega la columna si falta y rellena por título."""
    columns = db.execute("PRAGMA table_info(recipes)").fetchall()
    if not any(c["name"] == "instructions" for c in columns):
        db.execute("ALTER TABLE recipes ADD COLUMN instructions TEXT NOT NULL DEFAULT ''")
        db.commit()

    for recipe in SEED_RECIPES:
        db.execute(
            "UPDATE recipes SET instructions = ? WHERE title = ? AND instructions = ''",
            (recipe.instructions, recipe.title),
        )
    db.commit()


def _seed_if_empty(db: Db) -> None:
    count = db.execute("SELECT COUNT(*) AS n FROM recipes").fetchone()["n"]
    if count > 0:
        return

    id_by_name: dict[str, int] = {}
    for ingredient in SEED_INGREDIENTS:
        cur = db.execute("INSERT INTO ingredients (name) VALUES (?)", (ingredient.name,))
        ingredient_id = cur.lastrowid
        id_by_name[ingredient.name] = ingredient_id
        for alias in ingredient.synonyms:
            db.execute(
                "INSERT INTO ingredient_synonyms (ingredient_id, alias) VALUES (?, ?)",
                (ingredient_id, alias.lower()),
            )

    for recipe in SEED_RECIPES:
        cur = db.execute(
            "INSERT INTO recipes (title, diet, instructions) VALUES (?, ?, ?)",
            (recipe.title, recipe.diet, recipe.instructions),
        )
        recipe_id = cur.lastrowid
        for name, quantity in recipe.ingredients:
            ingredient_id = id_by_name.get(name)
            if ingredient_id is None:
                raise ValueError(f'Seed inconsistente: falta el ingrediente "{name}"')
            db.execute(
                "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity) VALUES (?, ?, ?)",
                (recipe_id, ingredient_id, quantity),
            )

    db.commit()


def load_synonym_map(db: Db) -> dict[str, str]:
    """alias normalizado -> canónico (incluye cada canónico apuntando a sí mismo)."""
    result: dict[str, str] = {}
    for row in db.execute("SELECT name FROM ingredients").fetchall():
        result[row["name"]] = row["name"]

    for row in db.execute(
        "SELECT s.alias, i.name FROM ingredient_synonyms s JOIN ingredients i ON i.id = s.ingredient_id"
    ).fetchall():
        result[row["alias"]] = row["name"]
    return result


def load_recipes(db: Db) -> list[RecipeRecord]:
    rows = db.execute(
        """
        SELECT r.id, r.title, r.diet, i.name AS ingredient
        FROM recipes r
        JOIN recipe_ingredients ri ON ri.recipe_id = r.id
        JOIN ingredients i ON i.id = ri.ingredient_id
        ORDER BY r.id
        """
    ).fetchall()

    by_id: dict[int, RecipeRecord] = {}
    for row in rows:
        existing = by_id.get(row["id"])
        if existing:
            existing.ingredients.append(row["ingredient"])
        else:
            by_id[row["id"]] = RecipeRecord(
                id=row["id"],
                title=row["title"],
                diet=row["diet"],
                ingredients=[row["ingredient"]],
            )
    return list(by_id.values())


@dataclass
class RecipeDetail:
    id: int
    title: str
    diet: Diet
    instructions: str
    ingredients: list[dict]  # [{ "name": str, "quantity": str | None }]


def load_recipe(db: Db, id_: int) -> Optional[RecipeDetail]:
    recipe_row = db.execute(
        "SELECT id, title, diet, instructions FROM recipes WHERE id = ?", (id_,)
    ).fetchone()
    if recipe_row is None:
        return None

    ingredient_rows = db.execute(
        """
        SELECT i.name, ri.quantity
        FROM recipe_ingredients ri
        JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY i.name
        """,
        (id_,),
    ).fetchall()

    return RecipeDetail(
        id=recipe_row["id"],
        title=recipe_row["title"],
        diet=recipe_row["diet"],
        instructions=recipe_row["instructions"],
        ingredients=[{"name": r["name"], "quantity": r["quantity"]} for r in ingredient_rows],
    )
