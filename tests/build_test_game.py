"""Build the Gun Range test world (.zork file) for engine testing.

This script creates a complete, hand-crafted test game based on the design
document at docs/game-design/test-world.md.  Every ID, name, description,
and field value is taken directly from that document.

Run standalone:
    python tests/build_test_game.py
"""

from pathlib import Path
import json

from anyzork.db.schema import GameDB


def build_test_game() -> Path:
    """Build and return path to the test game .zork file."""
    path = Path(__file__).parent / "test_game.zork"
    # Delete if exists
    path.unlink(missing_ok=True)

    db = GameDB(path)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    db.initialize(
        game_name="The Gun Range",
        author="test",
        prompt="A military gun range qualification course that tests nested container weapon assembly.",
        seed="gun-range-test-v2",
        intro_text=(
            "PROVING GROUNDS -- WEAPONS QUALIFICATION COURSE\n\n"
            "Your objective: assemble and qualify with both assigned weapon systems. "
            "P226 pistol and AR-15 rifle. Load your magazines, load your weapons, "
            "and put rounds on target.\n\n"
            "Report to the armory to begin."
        ),
        win_text=(
            "QUALIFICATION COMPLETE\n\n"
            "Both weapon systems qualified. You are cleared to proceed.\n\n"
            "Final score: {score} / {max_score}"
        ),
        lose_text=None,
        win_conditions=json.dumps(["p226_qualified", "ar15_qualified"]),
        lose_conditions=None,
        max_score=45,
        region_count=1,
        room_count=5,
    )
    db.set_meta("realism", "medium")

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------
    db.insert_room(
        id="armory",
        name="Armory",
        description=(
            "A windowless concrete room lined with steel weapon racks and metal "
            "shelving. The air smells of gun oil and solvent. Fluorescent tubes "
            "buzz overhead, casting flat white light across every surface. A "
            "reinforced door leads east toward the range."
        ),
        short_description=(
            "The concrete armory. Steel racks and shelving line the walls. "
            "The range is east."
        ),
        first_visit_text=(
            "You step through the blast door and it seals behind you with a "
            "hydraulic hiss. The proving grounds qualification course begins "
            "here. Arm up, qualify, get out."
        ),
        region="gun_range",
        is_dark=0,
        is_start=1,
    )

    db.insert_room(
        id="firing_range",
        name="Firing Range",
        description=(
            "A long, narrow range with shooting lanes separated by thick concrete "
            "dividers. Halogen floods illuminate paper targets hanging at the far "
            "end. Spent brass casings litter the floor. The air is heavy with the "
            "smell of burnt powder. The armory is back to the west, and a door to "
            "the north is marked RANGE OFFICE."
        ),
        short_description=(
            "The firing range. Shooting lanes stretch out ahead. West to the "
            "armory, north to the range office. A door to the south is marked EXIT."
        ),
        first_visit_text=None,
        region="gun_range",
        is_dark=0,
        is_start=0,
    )

    db.insert_room(
        id="range_office",
        name="Range Office",
        description=(
            "A small office behind reinforced glass. A metal desk is buried under "
            "paperwork, and a corkboard on the wall is pinned with range schedules "
            "and safety violations. A coffee mug sits on the desk, still warm."
        ),
        short_description=(
            "The range office. Paperwork covers every surface. South returns to "
            "the range."
        ),
        first_visit_text=None,
        region="gun_range",
        is_dark=0,
        is_start=0,
    )

    db.insert_room(
        id="exit_corridor",
        name="Exit Corridor",
        description=(
            "A short corridor of bare concrete. Daylight leaks under the heavy "
            "steel door at the far end. A sign above it reads: QUALIFICATION "
            "COMPLETE -- PROCEED TO DEBRIEFING."
        ),
        short_description="The exit corridor. Daylight ahead.",
        first_visit_text=(
            "You push through the door and daylight floods in. The qualification "
            "course is behind you. Well done, recruit."
        ),
        region="gun_range",
        is_dark=0,
        is_start=0,
    )

    db.insert_room(
        id="storage_bunker",
        name="Storage Bunker",
        description=(
            "A low-ceilinged concrete bunker lined with metal shelving. Crates "
            "of surplus equipment are stacked against the walls. The air is stale "
            "and cold. A single bare bulb socket hangs from the ceiling, but the "
            "bulb is burnt out. The armory is back to the south."
        ),
        short_description=(
            "The dark storage bunker. Shelves and crates everywhere. South to the armory."
        ),
        first_visit_text=(
            "You push open the heavy door and step into blackness. The overhead "
            "light is dead. You'll need your own light source to see anything."
        ),
        region="gun_range",
        is_dark=1,
        is_start=0,
    )

    # ------------------------------------------------------------------
    # Exits
    # ------------------------------------------------------------------
    db.insert_exit(
        id="armory_to_range",
        from_room_id="armory",
        to_room_id="firing_range",
        direction="east",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="range_to_armory",
        from_room_id="firing_range",
        to_room_id="armory",
        direction="west",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="range_to_office",
        from_room_id="firing_range",
        to_room_id="range_office",
        direction="north",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="office_to_range",
        from_room_id="range_office",
        to_room_id="firing_range",
        direction="south",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="range_to_exit",
        from_room_id="firing_range",
        to_room_id="exit_corridor",
        direction="south",
        is_locked=1,
        is_hidden=0,
    )
    db.insert_exit(
        id="exit_to_range",
        from_room_id="exit_corridor",
        to_room_id="firing_range",
        direction="north",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="armory_to_bunker",
        from_room_id="armory",
        to_room_id="storage_bunker",
        direction="north",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="bunker_to_armory",
        from_room_id="storage_bunker",
        to_room_id="armory",
        direction="south",
        is_locked=0,
        is_hidden=0,
    )

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    # Insertion order respects FK constraints:
    #   locker_key before weapons_locker (key_item_id)
    #   weapons_locker before ar15 (container_id)
    #   crate_key before supply_crate (key_item_id)
    #   supply_crate before ear_protection (container_id)

    # --- P226 Weapon System ---

    db.insert_item(
        id="p226",
        name="P226 pistol",
        description="A SIG Sauer P226 service pistol. Matte black finish, polymer grip.",
        examine_description=(
            "A full-size SIG Sauer P226 in 9mm. The slide is clean, the bore is "
            "bright, and the grip panels show light wear from holster draw. The "
            "magazine well is empty -- it needs a P226 magazine to function."
        ),
        room_description="A P226 pistol sits on one of the weapon racks.",
        drop_description="A P226 pistol lies on the ground.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=1,
        accepts_items=json.dumps(["p226_magazine"]),
        reject_message="That magazine doesn't fit the P226.",
        has_lid=0,
        is_open=1,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="weapon",
        item_tags=json.dumps(["weapon", "firearm"]),
        take_message="You pick up the P226. It has good weight.",
        drop_message="You set the P226 down.",
    )

    db.insert_item(
        id="p226_magazine",
        name="P226 magazine",
        description="A 15-round detachable magazine for the P226.",
        examine_description=(
            "A steel-body 15-round magazine for the SIG P226. Double-stack design. "
            "The feed lips are clean and the spring has good tension. It's empty "
            "-- you'd need 9mm ammo to load it."
        ),
        room_description="A P226 magazine rests on a metal shelf.",
        drop_description="A P226 magazine lies on the ground.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=1,
        accepts_items=json.dumps(["9mm_ammo"]),
        reject_message="That ammo doesn't fit this magazine.",
        has_lid=0,
        is_open=1,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="weapon",
        take_message="You pick up the P226 magazine.",
        drop_message="You set the P226 magazine down.",
    )

    db.insert_item(
        id="9mm_ammo",
        name="9mm ammo",
        description="A box of 9mm full metal jacket rounds.",
        examine_description=(
            "Standard 9x19mm Parabellum, full metal jacket. Brass casings, copper "
            "jackets. The box is full. These fit the P226 magazine."
        ),
        room_description="A box of 9mm ammo sits on the shelf beside the magazine.",
        drop_description="A box of 9mm ammo sits on the ground.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="ammo",
        take_message="You pick up the box of 9mm ammo.",
        drop_message="You set the 9mm ammo down.",
    )

    # --- Keys (must precede containers that reference them) ---

    db.insert_item(
        id="locker_key",
        name="locker key",
        description="A small steel key on a ring.",
        examine_description=(
            'A standard padlock key. The tag reads "WPN LOCKER -- ARM-01." '
            "It fits the weapons locker in the armory."
        ),
        room_description="A small key hangs from a hook on the wall.",
        drop_description="A small key sits on the ground.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="key",
        take_message="You take the locker key.",
        drop_message="You set the key down.",
    )

    db.insert_item(
        id="crate_key",
        name="crate key",
        description='A small key with a tag that reads "SUPPLY."',
        examine_description=(
            'A small brass key. The tag reads "SUPPLY -- ARM OFFICE." It looks '
            "like it fits the supply crate in the range office."
        ),
        room_description=None,
        drop_description="A small key sits on the ground.",
        home_room_id=None,
        room_id=None,
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=1,
        is_visible=0,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="key",
        take_message="You take the crate key.",
        drop_message="You set the crate key down.",
    )

    # --- Containers (must precede items stored inside them) ---

    db.insert_item(
        id="weapons_locker",
        name="weapons locker",
        description="A tall steel weapons locker, the kind you see in every military armory.",
        examine_description=(
            "A full-height steel weapons locker with a reinforced door and a heavy "
            "padlock. Standard military issue. It can hold just about anything. The "
            "padlock looks like it needs a key."
        ),
        room_description="A tall steel weapons locker stands in the corner.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=1,
        accepts_items=None,
        reject_message=None,
        has_lid=1,
        is_open=0,
        is_locked=1,
        is_takeable=0,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id="locker_key",
        consume_key=0,
        unlock_message="You turn the key in the padlock. It clicks open and you swing the locker door wide.",
        lock_message="The weapons locker is padlocked shut. You need a key.",
        open_message="You open the weapons locker.",
        search_message=None,
        weight=None,
        category="furniture",
    )

    db.insert_item(
        id="supply_crate",
        name="supply crate",
        description="A heavy-duty plastic supply crate with a combination lock.",
        examine_description=(
            "A Pelican-style hard case with reinforced latches and a small "
            "combination lock. A label on the side reads: SUPPLY -- SGT. CHEN. "
            "You would need the crate key from Sergeant Chen to open this."
        ),
        room_description="A locked supply crate sits under the desk.",
        home_room_id="range_office",
        room_id="range_office",
        container_id=None,
        is_container=1,
        accepts_items=None,
        reject_message=None,
        has_lid=1,
        is_open=0,
        is_locked=1,
        is_takeable=0,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id="crate_key",
        consume_key=0,
        unlock_message="The key turns and the latches pop open.",
        lock_message="The supply crate is locked. You need the key from Sergeant Chen.",
        open_message="You open the supply crate.",
        search_message=None,
        weight=None,
        category="furniture",
    )

    # --- AR-15 Weapon System (ar15 inside weapons_locker) ---

    db.insert_item(
        id="ar15",
        name="AR-15 rifle",
        description="An AR-15 semi-automatic rifle with a black polymer stock.",
        examine_description=(
            "A standard AR-15 platform in 5.56 NATO. Flat-top upper receiver, M4 "
            "profile barrel, six-position collapsible stock. The bolt carrier group "
            "is clean and lubricated. The magazine well is empty -- it needs an "
            "AR-15 magazine."
        ),
        room_description="An AR-15 rifle is propped against the weapon rack.",
        drop_description="An AR-15 rifle lies on the ground.",
        home_room_id="armory",
        room_id=None,
        container_id="weapons_locker",
        is_container=1,
        accepts_items=json.dumps(["ar15_magazine"]),
        reject_message="That magazine doesn't fit the AR-15.",
        has_lid=0,
        is_open=1,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="weapon",
        item_tags=json.dumps(["weapon", "firearm"]),
        take_message="You pick up the AR-15. It's heavier than the pistol.",
        drop_message="You set the AR-15 down.",
    )

    db.insert_item(
        id="ar15_magazine",
        name="AR-15 magazine",
        description="A 30-round STANAG magazine for the AR-15.",
        examine_description=(
            "A 30-round aluminum STANAG magazine. Curved body, anti-tilt follower. "
            "Standard NATO spec. It's empty -- you'd need 5.56mm ammo to load it."
        ),
        room_description="An AR-15 magazine lies on a workbench.",
        drop_description="An AR-15 magazine lies on the ground.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=1,
        accepts_items=json.dumps(["556_ammo"]),
        reject_message="That ammo doesn't fit this magazine.",
        has_lid=0,
        is_open=1,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="weapon",
        take_message="You pick up the AR-15 magazine.",
        drop_message="You set the AR-15 magazine down.",
    )

    db.insert_item(
        id="556_ammo",
        name="5.56mm ammo",
        description="A box of 5.56x45mm NATO rounds.",
        examine_description=(
            "Standard 5.56x45mm NATO, 55-grain full metal jacket. Green-tip "
            "penetrator. The box is full. These fit the AR-15 magazine."
        ),
        room_description="A box of 5.56mm ammo is stacked on a lower shelf.",
        drop_description="A box of 5.56mm ammo sits on the ground.",
        home_room_id="armory",
        room_id="armory",
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="ammo",
        take_message="You pick up the box of 5.56mm ammo.",
        drop_message="You set the 5.56mm ammo down.",
    )

    # --- Items inside supply_crate ---

    db.insert_item(
        id="ear_protection",
        name="ear protection",
        description="A pair of over-ear hearing protectors.",
        examine_description=(
            "Standard-issue Peltor over-ear hearing protectors, olive drab. "
            "Required on the firing range. These have seen some use but the "
            "foam seals are still good."
        ),
        room_description="A pair of ear protection hangs from a peg inside the crate.",
        drop_description="A pair of ear protection sits on the ground.",
        home_room_id="range_office",
        room_id=None,
        container_id="supply_crate",
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=1,
        category="equipment",
        take_message="You take the ear protection. Safety first.",
        drop_message="You set the ear protection down.",
    )

    # ------------------------------------------------------------------
    # Items -- Range Scenery (Non-Takeable)
    # ------------------------------------------------------------------
    db.insert_item(
        id="pistol_target",
        name="pistol target",
        description="A paper silhouette target hanging from a motorized track.",
        examine_description=(
            "A standard B-27 paper silhouette target, human-shaped, hanging at "
            "25 yards. The scoring zones are clearly marked. It's unmarked -- no "
            "one has qualified yet today."
        ),
        room_description="A paper silhouette target hangs in the left lane.",
        home_room_id="firing_range",
        room_id="firing_range",
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=0,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=None,
        category="scenery",
    )

    db.insert_item(
        id="rifle_target",
        name="rifle target",
        description="A steel plate target mounted on a spring stand.",
        examine_description=(
            "An AR500 steel plate, 12 inches in diameter, mounted on a heavy "
            "spring stand at 100 yards. A clean hit would make it ring and swing. "
            "It's untouched."
        ),
        room_description="A steel plate target stands at the far end of the right lane.",
        home_room_id="firing_range",
        room_id="firing_range",
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=0,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=None,
        category="scenery",
    )

    db.insert_item(
        id="range_safety_poster",
        name="safety poster",
        description="A faded safety poster on the wall.",
        examine_description=(
            "The poster lists the four rules of firearm safety in large block "
            "letters: 1. Treat every weapon as if it is loaded. 2. Never point at "
            "anything you do not intend to destroy. 3. Keep your finger off the "
            "trigger until ready to fire. 4. Know your target and what is beyond "
            'it. Someone has written "ALSO: WEAR YOUR EARS" in marker at the bottom.'
        ),
        read_description=(
            "FOUR RULES OF FIREARM SAFETY. 1. Treat every weapon as if it is "
            "loaded. 2. Never point at anything you do not intend to destroy. "
            "3. Keep your finger off the trigger until ready to fire. 4. Know "
            "your target and what is beyond it."
        ),
        room_description="A faded safety poster is tacked to the concrete divider.",
        home_room_id="firing_range",
        room_id="firing_range",
        container_id=None,
        is_container=0,
        accepts_items=None,
        reject_message=None,
        has_lid=0,
        is_open=0,
        is_locked=0,
        is_takeable=0,
        is_visible=1,
        is_consumed_on_use=0,
        key_item_id=None,
        weight=None,
        category="scenery",
    )

    # ------------------------------------------------------------------
    # Items -- Toggleable / Light Source / Consumable
    # ------------------------------------------------------------------
    db.insert_item(
        id="batteries",
        name="batteries",
        description="A pack of AA batteries.",
        examine_description=(
            "A 4-pack of Duracell AA batteries. Standard fare."
        ),
        room_description="A pack of batteries sits on a shelf.",
        drop_description="A pack of batteries lies on the ground.",
        home_room_id="armory",
        room_id="armory",
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        quantity=20,
        max_quantity=20,
        quantity_unit="charges",
        category="consumable",
    )

    db.insert_item(
        id="flashlight",
        name="tactical flashlight",
        description="A heavy-duty tactical flashlight.",
        examine_description=(
            "A SureFire tactical flashlight. Aluminum body, LED bulb. The "
            "battery indicator shows a charge."
        ),
        room_description="A tactical flashlight sits on the shelf.",
        drop_description="A flashlight lies on the ground.",
        home_room_id="armory",
        room_id="armory",
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        is_toggleable=1,
        toggle_state="off",
        toggle_on_message="The flashlight clicks on, casting a bright white beam.",
        toggle_off_message="The flashlight clicks off. Darkness returns.",
        item_tags=json.dumps(["light_source", "tool"]),
        requires_item_id="batteries",
        requires_message="The flashlight won't turn on -- the batteries are dead.",
        quantity=10,
        max_quantity=10,
        quantity_unit="charges",
        depleted_message="The flashlight flickers and dies. Batteries depleted.",
        category="tool",
    )

    # ------------------------------------------------------------------
    # NPCs
    # ------------------------------------------------------------------
    db.insert_npc(
        id="sgt_chen",
        name="Sergeant Chen",
        description=(
            "A compact woman in fatigues leans against the desk, arms crossed. "
            "Her nametape reads CHEN."
        ),
        examine_description=(
            "Sergeant Chen is mid-thirties, wiry, with close-cropped hair and the "
            "kind of economy of movement that comes from years of training. Her "
            "sleeves are rolled to the elbow and there's a pen behind her ear. "
            "Qualification records are spread across the desk in front of her. "
            "She looks like she has been waiting for you."
        ),
        room_id="range_office",
        is_alive=1,
        is_blocking=0,
        blocked_exit_id=None,
        unblock_flag=None,
        default_dialogue='Chen glances up. "You need something, recruit? Talk to me."',
        hp=None,
        damage=None,
        category="character",
    )

    # ------------------------------------------------------------------
    # Dialogue Nodes
    # ------------------------------------------------------------------
    db.insert_dialogue_node(
        id="chen_root",
        npc_id="sgt_chen",
        content=(
            'Chen looks you over. "You\'re the new recruit for qualification. '
            "Here's how it works: assemble your weapons in the armory, bring them "
            "out to the range, and put rounds on target. Pistol and rifle. Both "
            'must qualify. Questions?"'
        ),
        set_flags=json.dumps(["talked_to_chen"]),
        is_root=1,
    )

    db.insert_dialogue_node(
        id="chen_weapons",
        npc_id="sgt_chen",
        content=(
            '"Everything you need is in the armory, west of the range. Pistol and '
            "mags are on the racks and shelves. The rifle is in the weapons locker "
            "-- key should be hanging on the wall. Ammo is on the shelves too. "
            "Assemble each weapon: load the ammo into the magazine, then load the "
            'magazine into the gun. Do not mix calibers."'
        ),
        set_flags=None,
        is_root=0,
    )

    db.insert_dialogue_node(
        id="chen_supply",
        npc_id="sgt_chen",
        content=(
            "Chen pulls a small key from her pocket and tosses it to you. "
            '"Here. There\'s ear protection in the crate. Not required, but '
            'your hearing will thank you."'
        ),
        set_flags=json.dumps(["has_crate_key"]),
        is_root=0,
    )

    db.insert_dialogue_node(
        id="chen_p226_done",
        npc_id="sgt_chen",
        content=(
            'Chen checks a box on her clipboard. "P226 qual, confirmed. '
            'Good shooting. Now do the rifle."'
        ),
        set_flags=None,
        is_root=0,
    )

    db.insert_dialogue_node(
        id="chen_ar15_done",
        npc_id="sgt_chen",
        content=(
            'Chen checks another box. "AR-15 qual, confirmed. Nice work, recruit. '
            "If both quals are done, the exit should be unlocked. Head south from "
            'the range."'
        ),
        set_flags=None,
        is_root=0,
    )

    # ------------------------------------------------------------------
    # Dialogue Options
    # ------------------------------------------------------------------

    # Options for chen_root
    db.insert_dialogue_option(
        id="chen_opt_weapons",
        node_id="chen_root",
        text='"Where are the weapons?"',
        next_node_id="chen_weapons",
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )

    db.insert_dialogue_option(
        id="chen_opt_supply",
        node_id="chen_root",
        text='"I need the supply crate key."',
        next_node_id="chen_supply",
        required_flags=None,
        excluded_flags=json.dumps(["has_crate_key"]),
        required_items=None,
        set_flags=None,
        sort_order=2,
    )

    db.insert_dialogue_option(
        id="chen_opt_qualified_p226",
        node_id="chen_root",
        text='"I\'ve qualified with the P226."',
        next_node_id="chen_p226_done",
        required_flags=json.dumps(["p226_qualified"]),
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=3,
    )

    db.insert_dialogue_option(
        id="chen_opt_qualified_ar15",
        node_id="chen_root",
        text='"I\'ve qualified with the AR-15."',
        next_node_id="chen_ar15_done",
        required_flags=json.dumps(["ar15_qualified"]),
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=4,
    )

    db.insert_dialogue_option(
        id="chen_opt_done",
        node_id="chen_root",
        text='"Nothing. I\'m good."',
        next_node_id=None,
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=5,
    )

    # Options for chen_weapons
    db.insert_dialogue_option(
        id="chen_weapons_back",
        node_id="chen_weapons",
        text='"Got it. What else?"',
        next_node_id="chen_root",
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )

    # Options for chen_supply
    db.insert_dialogue_option(
        id="chen_supply_back",
        node_id="chen_supply",
        text='"Thanks. Anything else?"',
        next_node_id="chen_root",
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )

    # Options for chen_p226_done
    db.insert_dialogue_option(
        id="chen_p226_back",
        node_id="chen_p226_done",
        text='"Will do."',
        next_node_id=None,
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )

    # Options for chen_ar15_done
    db.insert_dialogue_option(
        id="chen_ar15_back",
        node_id="chen_ar15_done",
        text='"On my way."',
        next_node_id=None,
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )

    # ------------------------------------------------------------------
    # Locks
    # ------------------------------------------------------------------
    db.insert_lock(
        id="range_exit_lock",
        lock_type="state",
        target_exit_id="range_to_exit",
        key_item_id=None,
        puzzle_id=None,
        combination=None,
        required_flags=json.dumps(["p226_qualified", "ar15_qualified"]),
        locked_message=(
            "The exit door is sealed. A panel beside it reads: QUALIFICATION "
            "INCOMPLETE. Both pistol and rifle quals are required."
        ),
        unlock_message=(
            "The panel beside the exit door flashes green: QUALIFICATION COMPLETE. "
            "The lock disengages with a heavy clunk."
        ),
        is_locked=1,
        consume_key=0,
    )

    # ------------------------------------------------------------------
    # Puzzles
    # ------------------------------------------------------------------
    db.insert_puzzle(
        id="p226_qualification",
        name="P226 Pistol Qualification",
        description=(
            "Assemble the P226 pistol (load ammo into magazine, load magazine "
            "into gun) and fire at the pistol target in the firing range."
        ),
        room_id="firing_range",
        is_solved=0,
        solution_steps=json.dumps([
            "Take 9mm ammo, P226 magazine, and P226 pistol from the armory",
            "Load the 9mm ammo into the P226 magazine",
            "Load the P226 magazine into the P226 pistol",
            "Go to the firing range",
            "Shoot the pistol target",
        ]),
        hint_text=json.dumps([
            "You need to assemble a pistol. Check the armory for parts.",
            "Load the ammo into the magazine first, then the magazine into the gun.",
            "Take the loaded P226 to the firing range and shoot the target.",
        ]),
        difficulty=2,
        score_value=15,
        is_optional=0,
    )

    db.insert_puzzle(
        id="ar15_qualification",
        name="AR-15 Rifle Qualification",
        description=(
            "Assemble the AR-15 rifle (load ammo into magazine, load magazine "
            "into gun) and fire at the rifle target in the firing range."
        ),
        room_id="firing_range",
        is_solved=0,
        solution_steps=json.dumps([
            "Find the AR-15 in the weapons locker (unlock with locker key)",
            "Take 5.56mm ammo and AR-15 magazine from the armory",
            "Load the 5.56mm ammo into the AR-15 magazine",
            "Load the AR-15 magazine into the AR-15 rifle",
            "Go to the firing range",
            "Shoot the rifle target",
        ]),
        hint_text=json.dumps([
            "You need to assemble a rifle. The AR-15 is in the locked weapons locker in the armory.",
            "Find the locker key hanging on the wall in the armory. The ammo and magazine are on the shelves and workbench.",
            "Load ammo into mag, mag into gun. Take the loaded AR-15 to the range and shoot the steel target.",
        ]),
        difficulty=2,
        score_value=15,
        is_optional=0,
    )

    # ------------------------------------------------------------------
    # DSL Commands
    # ------------------------------------------------------------------

    # 6.1 Load P226 Magazine (ammo into magazine)
    db.insert_command(
        id="load_p226_magazine",
        verb="load",
        pattern="load {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "p226_magazine"},
            {"type": "has_item", "item": "9mm_ammo"},
            {"type": "not_item_in_container", "item": "9mm_ammo", "container": "p226_magazine"},
        ]),
        effects=json.dumps([
            {"type": "move_item_to_container", "item": "9mm_ammo", "container": "p226_magazine"},
            {"type": "print", "message": "You press the 9mm rounds into the P226 magazine one by one. The spring tension builds with each round until the magazine is full."},
        ]),
        success_message="",
        failure_message="You need the P226 magazine and 9mm ammo to load it.",
        context_room_ids=None,
        priority=10,
        one_shot=0,
        done_message="",
    )

    # 6.2 Load AR-15 Magazine (ammo into magazine)
    db.insert_command(
        id="load_ar15_magazine",
        verb="load",
        pattern="load {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "ar15_magazine"},
            {"type": "has_item", "item": "556_ammo"},
            {"type": "not_item_in_container", "item": "556_ammo", "container": "ar15_magazine"},
        ]),
        effects=json.dumps([
            {"type": "move_item_to_container", "item": "556_ammo", "container": "ar15_magazine"},
            {"type": "print", "message": "You push the 5.56mm rounds into the AR-15 magazine. The follower clicks down with each round. Full."},
        ]),
        success_message="",
        failure_message="You need the AR-15 magazine and 5.56mm ammo to load it.",
        context_room_ids=None,
        priority=10,
        one_shot=0,
        done_message="",
    )

    # 6.3 Load P226 (magazine into gun)
    db.insert_command(
        id="load_p226",
        verb="load",
        pattern="load {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "p226"},
            {"type": "has_item", "item": "p226_magazine"},
            {"type": "item_in_container", "item": "9mm_ammo", "container": "p226_magazine"},
            {"type": "not_item_in_container", "item": "p226_magazine", "container": "p226"},
        ]),
        effects=json.dumps([
            {"type": "move_item_to_container", "item": "p226_magazine", "container": "p226"},
            {"type": "set_flag", "flag": "p226_assembled"},
            {"type": "print", "message": "You slam the loaded magazine into the P226's grip. It seats with a satisfying click. The P226 is ready to fire."},
        ]),
        success_message="",
        failure_message="You need the P226 and a loaded P226 magazine to do that.",
        context_room_ids=None,
        priority=5,
        one_shot=0,
        done_message="",
    )

    # 6.4 Load AR-15 (magazine into gun)
    db.insert_command(
        id="load_ar15",
        verb="load",
        pattern="load {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "ar15"},
            {"type": "has_item", "item": "ar15_magazine"},
            {"type": "item_in_container", "item": "556_ammo", "container": "ar15_magazine"},
            {"type": "not_item_in_container", "item": "ar15_magazine", "container": "ar15"},
        ]),
        effects=json.dumps([
            {"type": "move_item_to_container", "item": "ar15_magazine", "container": "ar15"},
            {"type": "set_flag", "flag": "ar15_assembled"},
            {"type": "print", "message": "You rock the loaded magazine into the AR-15's mag well and slap it home. The rifle is ready to fire."},
        ]),
        success_message="",
        failure_message="You need the AR-15 and a loaded AR-15 magazine to do that.",
        context_room_ids=None,
        priority=5,
        one_shot=0,
        done_message="",
    )

    # 6.5 Shoot Pistol Target
    db.insert_command(
        id="shoot_pistol_target",
        verb="shoot",
        pattern="shoot {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "p226"},
            {"type": "item_in_container", "item": "p226_magazine", "container": "p226"},
            {"type": "item_in_container", "item": "9mm_ammo", "container": "p226_magazine"},
            {"type": "in_room", "room": "firing_range"},
            {"type": "not_flag", "flag": "p226_qualified"},
        ]),
        effects=json.dumps([
            {"type": "set_flag", "flag": "p226_qualified"},
            {"type": "add_score", "points": 15},
            {"type": "solve_puzzle", "puzzle": "p226_qualification"},
            {"type": "print", "message": "You raise the P226, align the sights, and squeeze. The pistol barks and bucks in your hand. Downrange, the paper target jerks -- a clean hole punched dead center mass. Pistol qualification: PASS."},
        ]),
        success_message="",
        failure_message="You need a loaded P226 pistol and you need to be at the firing range.",
        context_room_ids=json.dumps(["firing_range"]),
        priority=0,
        one_shot=1,
        done_message="You've already qualified with the P226.",
    )

    # 6.6 Shoot Rifle Target
    db.insert_command(
        id="shoot_rifle_target",
        verb="shoot",
        pattern="shoot {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "ar15"},
            {"type": "item_in_container", "item": "ar15_magazine", "container": "ar15"},
            {"type": "item_in_container", "item": "556_ammo", "container": "ar15_magazine"},
            {"type": "in_room", "room": "firing_range"},
            {"type": "not_flag", "flag": "ar15_qualified"},
        ]),
        effects=json.dumps([
            {"type": "set_flag", "flag": "ar15_qualified"},
            {"type": "add_score", "points": 15},
            {"type": "solve_puzzle", "puzzle": "ar15_qualification"},
            {"type": "print", "message": "You shoulder the AR-15, press your cheek to the stock, and fire. The rifle cracks sharply. A hundred yards out, the steel plate rings like a bell and swings on its stand. Rifle qualification: PASS."},
        ]),
        success_message="",
        failure_message="You need a loaded AR-15 rifle and you need to be at the firing range.",
        context_room_ids=json.dumps(["firing_range"]),
        priority=0,
        one_shot=1,
        done_message="You've already qualified with the AR-15.",
    )

    # 6.7 Unload P226 (magazine from gun)
    db.insert_command(
        id="unload_p226",
        verb="unload",
        pattern="unload {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "p226"},
            {"type": "item_in_container", "item": "p226_magazine", "container": "p226"},
        ]),
        effects=json.dumps([
            {"type": "take_item_from_container", "item": "p226_magazine"},
            {"type": "set_flag", "flag": "p226_assembled", "value": False},
            {"type": "print", "message": "You press the magazine release and the P226 magazine drops into your hand."},
        ]),
        success_message="",
        failure_message="The P226 doesn't have a magazine in it.",
        context_room_ids=None,
        priority=5,
        one_shot=0,
        done_message="",
    )

    # 6.8 Unload AR-15 (magazine from gun)
    db.insert_command(
        id="unload_ar15",
        verb="unload",
        pattern="unload {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "ar15"},
            {"type": "item_in_container", "item": "ar15_magazine", "container": "ar15"},
        ]),
        effects=json.dumps([
            {"type": "take_item_from_container", "item": "ar15_magazine"},
            {"type": "set_flag", "flag": "ar15_assembled", "value": False},
            {"type": "print", "message": "You press the mag release and strip the AR-15 magazine free."},
        ]),
        success_message="",
        failure_message="The AR-15 doesn't have a magazine in it.",
        context_room_ids=None,
        priority=5,
        one_shot=0,
        done_message="",
    )

    # 6.9 Unload P226 Magazine (ammo from magazine)
    db.insert_command(
        id="unload_p226_magazine",
        verb="unload",
        pattern="unload {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "p226_magazine"},
            {"type": "item_in_container", "item": "9mm_ammo", "container": "p226_magazine"},
        ]),
        effects=json.dumps([
            {"type": "take_item_from_container", "item": "9mm_ammo"},
            {"type": "print", "message": "You strip the 9mm rounds from the P226 magazine. The spring pushes each one up as you pull them free."},
        ]),
        success_message="",
        failure_message="The P226 magazine is empty.",
        context_room_ids=None,
        priority=10,
        one_shot=0,
        done_message="",
    )

    # 6.10 Unload AR-15 Magazine (ammo from magazine)
    db.insert_command(
        id="unload_ar15_magazine",
        verb="unload",
        pattern="unload {target}",
        preconditions=json.dumps([
            {"type": "has_item", "item": "ar15_magazine"},
            {"type": "item_in_container", "item": "556_ammo", "container": "ar15_magazine"},
        ]),
        effects=json.dumps([
            {"type": "take_item_from_container", "item": "556_ammo"},
            {"type": "print", "message": "You strip the 5.56mm rounds from the AR-15 magazine."},
        ]),
        success_message="",
        failure_message="The AR-15 magazine is empty.",
        context_room_ids=None,
        priority=10,
        one_shot=0,
        done_message="",
    )

    # 6.11 Spawn Crate Key (triggered by dialogue flag)
    db.insert_command(
        id="spawn_crate_key",
        verb="talk",
        pattern="talk to {npc}",
        preconditions=json.dumps([
            {"type": "npc_in_room", "npc": "sgt_chen", "room": "_current"},
            {"type": "has_flag", "flag": "has_crate_key"},
            {"type": "not_flag", "flag": "crate_key_given"},
        ]),
        effects=json.dumps([
            {"type": "spawn_item", "item": "crate_key", "location": "_inventory"},
            {"type": "set_flag", "flag": "crate_key_given"},
            {"type": "print", "message": ""},
        ]),
        success_message="",
        failure_message="",
        context_room_ids=json.dumps(["range_office"]),
        priority=100,
        one_shot=1,
        done_message="",
    )

    # 6.12 Take Ear Protection (quest tracking)
    db.insert_command(
        id="take_ear_protection",
        verb="take",
        pattern="take ear protection",
        preconditions=json.dumps([
            {"type": "not_flag", "flag": "has_ear_protection"},
        ]),
        effects=json.dumps([
            {"type": "set_flag", "flag": "has_ear_protection"},
        ]),
        success_message="You grab the ear protection. Safety first.",
        failure_message="",
        context_room_ids=json.dumps(["range_office"]),
        priority=10,
        one_shot=1,
        done_message="",
    )

    # ------------------------------------------------------------------
    # Quests
    # ------------------------------------------------------------------
    db.insert_quest(
        id="weapons_qualification",
        name="Weapons Qualification",
        description=(
            "Assemble both weapon systems, qualify at the firing range with each, "
            "and exit the proving grounds."
        ),
        quest_type="main",
        status="active",
        discovery_flag=None,
        completion_flag="qualification_complete",
        score_value=10,
        sort_order=1,
    )

    # Quest Objectives
    db.insert_quest_objective(
        id="obj_assemble_p226",
        quest_id="weapons_qualification",
        description="Assemble the P226 pistol (load magazine, load gun).",
        completion_flag="p226_assembled",
        order_index=1,
        is_optional=0,
        bonus_score=0,
    )

    db.insert_quest_objective(
        id="obj_qualify_p226",
        quest_id="weapons_qualification",
        description="Qualify with the P226 at the firing range.",
        completion_flag="p226_qualified",
        order_index=2,
        is_optional=0,
        bonus_score=0,
    )

    db.insert_quest_objective(
        id="obj_assemble_ar15",
        quest_id="weapons_qualification",
        description="Assemble the AR-15 rifle (load magazine, load gun).",
        completion_flag="ar15_assembled",
        order_index=3,
        is_optional=0,
        bonus_score=0,
    )

    db.insert_quest_objective(
        id="obj_qualify_ar15",
        quest_id="weapons_qualification",
        description="Qualify with the AR-15 at the firing range.",
        completion_flag="ar15_qualified",
        order_index=4,
        is_optional=0,
        bonus_score=0,
    )

    db.insert_quest_objective(
        id="obj_ear_protection",
        quest_id="weapons_qualification",
        description="Obtain ear protection from Sergeant Chen's supply crate.",
        completion_flag="has_ear_protection",
        order_index=5,
        is_optional=1,
        bonus_score=5,
    )

    # ------------------------------------------------------------------
    # Flags (initial state -- all false)
    # ------------------------------------------------------------------
    db.insert_flag(id="talked_to_chen", value="false", description="Player has talked to Sergeant Chen.")
    db.insert_flag(id="has_crate_key", value="false", description="Chen has offered the crate key.")
    db.insert_flag(id="crate_key_given", value="false", description="Crate key has been spawned to inventory.")
    db.insert_flag(id="p226_assembled", value="false", description="P226 magazine is loaded into P226.")
    db.insert_flag(id="ar15_assembled", value="false", description="AR-15 magazine is loaded into AR-15.")
    db.insert_flag(id="p226_qualified", value="false", description="Player passed P226 qualification.")
    db.insert_flag(id="ar15_qualified", value="false", description="Player passed AR-15 qualification.")
    db.insert_flag(id="has_ear_protection", value="false", description="Player obtained ear protection (optional).")
    db.insert_flag(id="qualification_complete", value="false", description="Both qualifications complete.")

    # ------------------------------------------------------------------
    # Interaction Responses
    # ------------------------------------------------------------------
    db.insert_interaction_response(
        id="firearm_character",
        item_tag="firearm",
        target_category="character",
        response="{target} flinches as you level the {item}.",
        consumes=1,
    )
    db.insert_interaction_response(
        id="firearm_furniture",
        item_tag="firearm",
        target_category="furniture",
        response="The {item} barks. A bullet hole appears in the {target}.",
        consumes=1,
    )
    db.insert_interaction_response(
        id="firearm_default",
        item_tag="firearm",
        target_category="*",
        response="You fire the {item} at the {target}. The shot echoes off the walls.",
        consumes=1,
    )
    db.insert_interaction_response(
        id="light_source_default",
        item_tag="light_source",
        target_category="*",
        response="You shine the {item} toward the {target}. Nothing unusual.",
    )
    db.insert_interaction_response(
        id="global_default",
        item_tag="*",
        target_category="*",
        response="Nothing interesting happens.",
    )

    # ------------------------------------------------------------------
    # Player state (start in armory)
    # ------------------------------------------------------------------
    db.init_player(start_room_id="armory", hp=100, max_hp=100)

    db.close()
    return path


if __name__ == "__main__":
    p = build_test_game()
    print(f"Test game built: {p}")
