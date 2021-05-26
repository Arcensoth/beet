from beet import Context, Function, Language


def add_greeting_translations(ctx: Context):
    ctx.assets["minecraft:en_us"] = Language({"greeting.hello": "hello"})
    ctx.assets["minecraft:fr_fr"] = Language({"greeting.hello": "bonjour"})


def add_greeting(ctx: Context):
    ctx.data["greeting:hello"] = Function(
        ['tellraw @a {"translate": "greeting.hello"}'] * 5,
        tags=["minecraft:load"],
    )
