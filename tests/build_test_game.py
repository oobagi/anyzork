"""Build a compact Gun Range test world to validate the AnyZork engine.

Game: "The Gun Range"

A private shooting range facility that exercises every AnyZork engine
capability in a tight, 4-room layout. Load firearms, shoot targets,
find supplies, and earn your range qualification.

Layout (1 region, 4 rooms):

    [Armory] --(east/west)--> [Firing Range] --(east/west)--> [Storage Room]
                                    |
                              (down, LOCKED -- state lock)
                                    |
                                [Bunker]

Win condition: Shoot both targets (P226 and AR-15) to unlock the bunker,
then use the qualification card inside the bunker.

Run this script to create tests/test_game.zork.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the package is importable when running the script directly.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from anyzork.db.schema import GameDB  # noqa: E402


def build_game() -> Path:
    """Build the test game and return the path to the .zork file."""
    output = Path(__file__).resolve().parent / "test_game.zork"

    # Remove stale file if it exists.
    if output.exists():
        output.unlink()

    with GameDB(output) as db:
        # ==============================================================
        # 1. Initialize database & metadata
        # ==============================================================
        db.initialize(
            game_name="The Gun Range",
            author="Level Designer Agent (test harness)",
            prompt=(
                "A private shooting range facility. Load firearms, shoot "
                "targets, and earn your range qualification."
            ),
            seed="gun-range-01",
            intro_text=(
                "You push through the heavy door into the range facility. "
                "The smell of gun oil and spent brass hits you immediately. "
                "Fluorescent tubes hum overhead, casting flat white light "
                "across concrete walls.\n\n"
                "THE GUN RANGE\n"
                "CIVILIAN QUALIFICATION FACILITY\n\n"
                "A sign by the entrance reads:\n"
                "'Qualify with both firearms to access the bunker below.'"
            ),
            win_text=(
                "The bunker hatch swings open and daylight floods in from "
                "above. You climb the ladder into fresh air. A brass plaque "
                "on the wall reads: QUALIFIED. You earned it."
            ),
            lose_text=(
                "Your vision blurs. The fluorescent lights swim overhead "
                "as you hit the concrete floor. The last thing you hear is "
                "a distant alarm. Qualification: FAILED."
            ),
            win_conditions=json.dumps(["range_qualification_complete"]),
            lose_conditions=json.dumps(["player_dead"]),
            max_score=100,
            region_count=1,
            room_count=4,
        )

        # ==============================================================
        # 2. Rooms (4 rooms, 1 region)
        # ==============================================================

        db.insert_room(
            id="armory",
            name="Armory",
            description=(
                "A concrete room with pegboard walls and metal shelving. "
                "Fluorescent tubes buzz overhead. The air is thick with "
                "the smell of Hoppe's No. 9 and CLP. A doorway leads "
                "east to the firing range."
            ),
            short_description="The Armory. East to the firing range.",
            first_visit_text=(
                "You step into the armory. The pegboard is mostly bare -- "
                "hooks where dozens of weapons once hung. A few remain."
            ),
            region="Range Facility",
            is_dark=0,
            is_start=1,
            visited=0,
        )

        db.insert_room(
            id="firing_range",
            name="Firing Range",
            description=(
                "A long, narrow range with concrete lane dividers and "
                "acoustic baffles on the ceiling. Shell casings crunch "
                "underfoot. Halogen floods illuminate the target line "
                "at the far end. The armory is west, storage is east, "
                "and a heavy hatch leads down."
            ),
            short_description=(
                "The Firing Range. West to the armory, east to storage, "
                "down to the bunker."
            ),
            first_visit_text=(
                "The crack of phantom gunfire echoes in your memory as "
                "you step onto the range. Thousands of rounds have been "
                "fired here."
            ),
            region="Range Facility",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="storage_room",
            name="Storage Room",
            description=(
                "A cool, dry room with reinforced shelving along every "
                "wall. The ventilation fans hum steadily. The firing "
                "range is back to the west."
            ),
            short_description="Storage Room. West to the firing range.",
            first_visit_text=(
                "Cold air hits you as the door swings open. Everything "
                "in here is organized with military precision."
            ),
            region="Range Facility",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="bunker",
            name="Bunker",
            description=(
                "A reinforced underground room with thick concrete walls "
                "and a low ceiling. Cable conduits snake overhead between "
                "recessed strip lights. A steel ladder leads back up to "
                "the range."
            ),
            short_description="The Bunker. Up to the firing range.",
            first_visit_text=(
                "You descend the ladder into a cool, humming space. "
                "This is it -- the qualification checkpoint."
            ),
            region="Range Facility",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        # ==============================================================
        # 3. Exits (6 exits -- 3 bidirectional pairs)
        # ==============================================================

        # Armory <-> Firing Range (east/west)
        db.insert_exit(
            id="armory_to_range",
            from_room_id="armory",
            to_room_id="firing_range",
            direction="east",
            description="The firing range is through the doorway to the east.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="range_to_armory",
            from_room_id="firing_range",
            to_room_id="armory",
            direction="west",
            description="The armory is back to the west.",
            is_locked=0,
            is_hidden=0,
        )

        # Firing Range <-> Storage Room (east/west)
        db.insert_exit(
            id="range_to_storage",
            from_room_id="firing_range",
            to_room_id="storage_room",
            direction="east",
            description="A door leads east to the storage room.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="storage_to_range",
            from_room_id="storage_room",
            to_room_id="firing_range",
            direction="west",
            description="The firing range is back to the west.",
            is_locked=0,
            is_hidden=0,
        )

        # Firing Range <-> Bunker (down/up, LOCKED -- state lock)
        db.insert_exit(
            id="range_to_bunker",
            from_room_id="firing_range",
            to_room_id="bunker",
            direction="down",
            description="A heavy hatch leads down to the bunker.",
            is_locked=1,
            is_hidden=0,
        )
        db.insert_exit(
            id="bunker_to_range",
            from_room_id="bunker",
            to_room_id="firing_range",
            direction="up",
            description="A steel ladder leads back up to the firing range.",
            is_locked=0,
            is_hidden=0,
        )

        # ==============================================================
        # 4. Items -- containers first, then contained, then loose
        # ==============================================================

        # ---- CONTAINERS ----

        # Armory: Weapon Locker (closed, LOCKED -- needs locker_key)
        db.insert_item(
            id="weapon_locker",
            name="weapon locker",
            description="A tall steel weapon locker with a padlock.",
            examine_description=(
                "A standard armory locker, tall and narrow. The padlock "
                "on the front needs a specific key. Through the ventilation "
                "slits you can see the outlines of firearms inside."
            ),
            room_id="armory",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=1,
            lock_message="The weapon locker is padlocked shut. You need a key.",
            open_message="The padlock clicks open and you swing the locker door wide.",
            search_message="You look inside the weapon locker...",
            category="scenery",
            room_description=(
                "A tall steel weapon locker stands against the wall, padlocked shut."
            ),
        )

        # Armory: Ammo Shelf (always-open, no lid)
        db.insert_item(
            id="ammo_shelf",
            name="ammo shelf",
            description="A metal shelf stocked with ammunition boxes.",
            examine_description=(
                "A sturdy metal shelf bolted to the wall. Several boxes "
                "of ammunition are arranged by caliber."
            ),
            room_id="armory",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=1,
            has_lid=0,
            is_locked=0,
            search_message="You check the ammo shelf...",
            category="scenery",
            room_description=(
                "A metal shelf holds boxes of ammunition, organized by caliber."
            ),
        )

        # Storage Room: Supply Crate (closed, unlocked)
        db.insert_item(
            id="supply_crate",
            name="supply crate",
            description="A wooden supply crate with rope handles.",
            examine_description=(
                "A heavy wooden crate with stenciled markings. The lid "
                "is not locked, just latched."
            ),
            room_id="storage_room",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=0,
            open_message="You flip the latch and lift the crate lid.",
            search_message="You look inside the supply crate...",
            category="scenery",
            room_description=(
                "A wooden supply crate sits on the floor, its lid latched."
            ),
        )

        # Storage Room: Med Kit container (closed, unlocked)
        db.insert_item(
            id="med_kit_container",
            name="med kit",
            description="A white plastic medical kit with a red cross.",
            examine_description=(
                "A standard first aid kit. The red cross on the lid is "
                "faded but visible. The clasp is not locked."
            ),
            room_id="storage_room",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=0,
            open_message="You pop the clasp and open the med kit.",
            search_message="You look inside the med kit...",
            category="scenery",
            room_description=(
                "A white med kit with a red cross hangs on the wall."
            ),
        )

        # ---- ITEMS INSIDE CONTAINERS ----

        # In weapon locker (locked): P226 and AR-15
        db.insert_item(
            id="p226",
            name="P226 pistol",
            description="A SIG Sauer P226 semi-automatic pistol.",
            examine_description=(
                "A well-maintained SIG Sauer P226 in 9mm. The slide is "
                "locked back -- no magazine inserted. A solid, reliable "
                "sidearm."
            ),
            room_id=None,
            container_id="weapon_locker",
            is_takeable=1,
            is_visible=1,
            take_message="You take the P226. It feels solid in your hand.",
            weight=2,
            category="weapon",
        )

        db.insert_item(
            id="ar15",
            name="AR-15 rifle",
            description="An AR-15 semi-automatic rifle.",
            examine_description=(
                "A standard AR-15 chambered in 5.56 NATO. The bolt is "
                "locked open -- no magazine inserted. Clean and well-oiled."
            ),
            room_id=None,
            container_id="weapon_locker",
            is_takeable=1,
            is_visible=1,
            take_message="You take the AR-15. It's lighter than you expected.",
            weight=3,
            category="weapon",
        )

        # In ammo shelf (always-open): magazines and ammo
        db.insert_item(
            id="p226_magazine",
            name="P226 magazine",
            description="A 15-round detachable magazine for the P226.",
            examine_description=(
                "A standard SIG P226 magazine. Currently empty -- needs "
                "to be loaded with 9mm ammunition."
            ),
            room_id=None,
            container_id="ammo_shelf",
            is_takeable=1,
            is_visible=1,
            take_message="You take the P226 magazine from the shelf.",
            weight=1,
            category="weapon",
        )

        db.insert_item(
            id="ar15_magazine",
            name="AR-15 magazine",
            description="A 30-round STANAG magazine for the AR-15.",
            examine_description=(
                "A standard STANAG magazine. Currently empty -- needs "
                "to be loaded with 5.56mm ammunition."
            ),
            room_id=None,
            container_id="ammo_shelf",
            is_takeable=1,
            is_visible=1,
            take_message="You take the AR-15 magazine from the shelf.",
            weight=1,
            category="weapon",
        )

        db.insert_item(
            id="9mm_ammo",
            name="9mm ammo",
            description="A box of 9mm pistol ammunition.",
            examine_description=(
                "A sealed box of fifty 9mm FMJ rounds. Standard for "
                "the P226 pistol."
            ),
            room_id=None,
            container_id="ammo_shelf",
            is_takeable=1,
            is_visible=1,
            take_message="You grab the box of 9mm ammo.",
            weight=2,
            category="ammo",
        )

        db.insert_item(
            id="556_ammo",
            name="5.56mm ammo",
            description="A box of 5.56mm NATO rifle ammunition.",
            examine_description=(
                "A sealed box of sixty 5.56mm NATO rounds. Standard for "
                "the AR-15 rifle."
            ),
            room_id=None,
            container_id="ammo_shelf",
            is_takeable=1,
            is_visible=1,
            take_message="You grab the box of 5.56mm ammo.",
            weight=2,
            category="ammo",
        )

        # In supply crate (closed, unlocked): bunker key and documents
        db.insert_item(
            id="bunker_key",
            name="bunker key",
            description="A heavy brass key with a tag reading 'BUNKER'.",
            examine_description=(
                "A heavy brass key. The tag attached reads: BUNKER -- "
                "RANGE LEVEL. Not for the main hatch though -- that "
                "opens electronically."
            ),
            room_id=None,
            container_id="supply_crate",
            is_takeable=1,
            is_visible=1,
            take_message="You take the bunker key.",
            weight=1,
            category="key",
        )

        db.insert_item(
            id="field_manual",
            name="field manual",
            description="A small firearms training manual.",
            examine_description=(
                "A pocket-sized manual with a worn cover. The title "
                "reads: RANGE QUALIFICATION PROCEDURES."
            ),
            read_description=(
                "RANGE QUALIFICATION PROCEDURES\n\n"
                "Chapter 1: Safety\n"
                "Always treat every weapon as if it is loaded.\n\n"
                "Chapter 2: Loading\n"
                "1. Insert ammunition into the magazine.\n"
                "2. Insert the loaded magazine into the weapon.\n\n"
                "Chapter 3: Qualification\n"
                "Fire at each target from a standing position. "
                "Qualify with both the P226 and the AR-15 to "
                "unlock the bunker hatch."
            ),
            room_id=None,
            container_id="supply_crate",
            is_takeable=1,
            is_visible=1,
            take_message="You take the field manual.",
            weight=1,
            category="document",
        )

        # In med kit container (closed, unlocked): bandages and painkillers
        db.insert_item(
            id="bandages",
            name="bandages",
            description="A roll of sterile gauze bandages.",
            examine_description=(
                "A tightly wound roll of sterile gauze. Good for patching "
                "up minor injuries. Should restore about 20 HP."
            ),
            room_id=None,
            container_id="med_kit_container",
            is_takeable=1,
            is_visible=1,
            is_consumed_on_use=1,
            take_message="You take the bandages from the med kit.",
            weight=1,
            category="consumable",
        )

        db.insert_item(
            id="painkillers",
            name="painkillers",
            description="A blister pack of ibuprofen tablets.",
            examine_description=(
                "Standard over-the-counter painkillers. Should take the "
                "edge off. Restores about 15 HP."
            ),
            room_id=None,
            container_id="med_kit_container",
            is_takeable=1,
            is_visible=1,
            is_consumed_on_use=1,
            take_message="You take the painkillers from the med kit.",
            weight=1,
            category="consumable",
        )

        # ---- LOOSE ITEMS (in rooms) ----

        # Armory: Locker Key (for weapon locker)
        db.insert_item(
            id="locker_key",
            name="locker key",
            description="A small brass key with a tag reading 'WPN LOCKER'.",
            examine_description=(
                "A small brass padlock key. The tag reads: WPN LOCKER -- "
                "ARMORY. This opens the weapon locker."
            ),
            room_id="armory",
            is_takeable=1,
            is_visible=1,
            weight=1,
            category="key",
            room_description=(
                "A small brass key lies on the counter near the door."
            ),
        )

        # Armory: Range Rules (document with read_description)
        db.insert_item(
            id="range_rules",
            name="range rules",
            description="A laminated card listing the range safety rules.",
            examine_description=(
                "A laminated card mounted on the wall. The text is printed "
                "in bold red and black."
            ),
            read_description=(
                "RANGE SAFETY RULES\n\n"
                "1. All firearms must be unloaded until on the firing line.\n"
                "2. Keep your finger off the trigger until ready to fire.\n"
                "3. Never point a firearm at anything you don't intend to "
                "shoot.\n"
                "4. Qualify with BOTH firearms to unlock the bunker hatch.\n"
                "5. Report all injuries to the quartermaster immediately."
            ),
            room_id="armory",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A laminated range rules card is mounted on the wall."
            ),
        )

        # Firing Range: Pistol Target (scenery)
        db.insert_item(
            id="pistol_target",
            name="pistol target",
            description="A paper silhouette target at the near lane.",
            examine_description=(
                "A standard qualification target -- human silhouette on "
                "heavy paper. The center ring is marked. It hangs about "
                "15 meters downrange in the pistol lane."
            ),
            room_id="firing_range",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A paper silhouette target hangs at the near lane."
            ),
        )

        # Firing Range: Rifle Target (scenery)
        db.insert_item(
            id="rifle_target",
            name="rifle target",
            description="A steel plate target at the far lane.",
            examine_description=(
                "A heavy steel plate target painted white, mounted on a "
                "stand at 50 meters downrange in the rifle lane. A hit "
                "will ring it like a bell."
            ),
            room_id="firing_range",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A steel plate target stands at the far lane."
            ),
        )

        # Firing Range: Scoreboard (scenery)
        db.insert_item(
            id="scoreboard",
            name="scoreboard",
            description="A digital scoreboard mounted above the lanes.",
            examine_description=(
                "A digital display showing qualification scores. Your "
                "name is listed but the score columns are blank. Time "
                "to fill them in."
            ),
            room_id="firing_range",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A digital scoreboard is mounted above the lanes."
            ),
        )

        # Firing Range: Firing Lane (scenery)
        db.insert_item(
            id="firing_lane",
            name="firing lane",
            description="A concrete shooting lane with a waist-high divider.",
            examine_description=(
                "A standard shooting lane with a concrete divider and a "
                "shelf for resting your weapon. Spent brass litters the "
                "floor. A red line marks the firing position."
            ),
            room_id="firing_range",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "Concrete shooting lanes stretch toward the target line."
            ),
        )

        # Bunker: Qualification Scanner (scenery)
        db.insert_item(
            id="qualification_scanner",
            name="qualification scanner",
            description="An electronic scanner next to a heavy hatch.",
            examine_description=(
                "A wall-mounted card reader with a green LED. A slot "
                "accepts qualification cards. The display reads: "
                "AWAITING QUALIFICATION CARD."
            ),
            room_id="bunker",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A qualification scanner is mounted next to a heavy hatch."
            ),
        )

        # ---- INVISIBLE ITEMS (spawned by DSL commands) ----

        # Qualification Card: spawned after both targets are hit
        db.insert_item(
            id="qualification_card",
            name="qualification card",
            description="A scored qualification card with two punched marks.",
            examine_description=(
                "A stiff card punched with two marks -- one for pistol, "
                "one for rifle. The header reads: RANGE QUALIFICATION -- "
                "COMPLETE. Feed it into the bunker scanner."
            ),
            room_id=None,
            container_id=None,
            is_takeable=1,
            is_visible=0,
            weight=1,
            category="key",
        )

        # ---- BACKFILL: Set key_item_id on locked containers ----
        db._mutate(
            "UPDATE items SET key_item_id = ? WHERE id = ?",
            ("locker_key", "weapon_locker"),
        )

        # ==============================================================
        # 5. NPCs
        # ==============================================================

        # Quartermaster (Friendly, Dialogue Tree)
        db.insert_npc(
            id="quartermaster",
            name="Quartermaster",
            description=(
                "A broad-shouldered man in a faded olive uniform, leaning "
                "against the counter with his arms crossed."
            ),
            examine_description=(
                "The Quartermaster. Salt-and-pepper crew cut, hands like "
                "catchers' mitts, and a nameplate that reads HAYES. He "
                "knows where everything is."
            ),
            room_id="armory",
            is_alive=1,
            is_blocking=0,
            blocked_exit_id=None,
            unblock_flag=None,
            default_dialogue=(
                "Hayes glances at you. 'Qualification day? Everything you "
                "need is right here. Guns in the locker, ammo on the shelf. "
                "Talk to me if you need pointers.'"
            ),
            hp=None,
            damage=None,
        )

        # Training Dummy in firing range (has HP for future combat testing)
        db.insert_npc(
            id="training_dummy",
            name="Training Dummy",
            description=(
                "A sand-filled dummy in a human silhouette, hanging from "
                "a steel frame at the edge of the range."
            ),
            examine_description=(
                "A battered training dummy. Duct tape holds its seams "
                "together. Someone drew a smiley face on it in marker."
            ),
            room_id="firing_range",
            is_alive=1,
            is_blocking=0,
            blocked_exit_id=None,
            unblock_flag=None,
            default_dialogue="It's a training dummy. It doesn't talk.",
            hp=30,
            damage=5,
        )

        # ==============================================================
        # 6. Dialogue Trees
        # ==============================================================

        # ---- Quartermaster dialogue tree ----

        # Root node
        db.insert_dialogue_node(
            id="qm_root",
            npc_id="quartermaster",
            content=(
                "Hayes straightens up. 'What can I help you with, "
                "shooter?'"
            ),
            set_flags=None,
            is_root=1,
        )

        # Node: How to qualify
        db.insert_dialogue_node(
            id="qm_how_to_qualify",
            npc_id="quartermaster",
            content=(
                "'Simple. Load a magazine with ammo, load the magazine "
                "into the gun, then fire at the target on the range. "
                "You gotta qualify with both the P226 and the AR-15. "
                "Once both targets are down, the bunker hatch unlocks.'"
            ),
            set_flags=json.dumps(["asked_qualification"]),
            is_root=0,
        )

        # Node: Where are the guns
        db.insert_dialogue_node(
            id="qm_where_guns",
            npc_id="quartermaster",
            content=(
                "'Guns are in the weapon locker right there.' He points. "
                "'Locked up tight. The key should be on the counter where "
                "I left it. Ammo and magazines are on the shelf -- help "
                "yourself.'"
            ),
            set_flags=json.dumps(["asked_gun_location"]),
            is_root=0,
        )

        # Node: Inventory-reactive -- have a gun
        db.insert_dialogue_node(
            id="qm_have_gun",
            npc_id="quartermaster",
            content=(
                "Hayes eyes the weapon in your hands. 'Good, you're "
                "armed. Now load it up and get on the range. Remember: "
                "ammo into magazine, magazine into gun. Don't overthink "
                "it.'"
            ),
            set_flags=json.dumps(["got_gun_advice"]),
            is_root=0,
        )

        # Options from root node

        # Option 1: How to qualify (disappears after asking)
        db.insert_dialogue_option(
            id="qm_root_opt_1",
            node_id="qm_root",
            text='"How do I qualify?"',
            next_node_id="qm_how_to_qualify",
            required_flags=None,
            excluded_flags=json.dumps(["asked_qualification"]),
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        # Option 2: Where are the guns (disappears after asking)
        db.insert_dialogue_option(
            id="qm_root_opt_2",
            node_id="qm_root",
            text='"Where are the guns?"',
            next_node_id="qm_where_guns",
            required_flags=None,
            excluded_flags=json.dumps(["asked_gun_location"]),
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        # Option 3: Inventory-reactive (requires P226 in inventory)
        db.insert_dialogue_option(
            id="qm_root_opt_3",
            node_id="qm_root",
            text='"I got the P226. Any tips?"',
            next_node_id="qm_have_gun",
            required_flags=None,
            excluded_flags=json.dumps(["got_gun_advice"]),
            required_items=json.dumps(["p226"]),
            set_flags=None,
            sort_order=2,
        )

        # Option 4: Leave (always visible, terminal)
        db.insert_dialogue_option(
            id="qm_root_opt_4",
            node_id="qm_root",
            text='"[Leave]"',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=3,
        )

        # Sub-node options: loop back to root or leave

        # How to qualify -> back or leave
        db.insert_dialogue_option(
            id="qm_qualify_back",
            node_id="qm_how_to_qualify",
            text='"I have more questions."',
            next_node_id="qm_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )
        db.insert_dialogue_option(
            id="qm_qualify_leave",
            node_id="qm_how_to_qualify",
            text='"Got it, thanks."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        # Where guns -> back or leave
        db.insert_dialogue_option(
            id="qm_guns_back",
            node_id="qm_where_guns",
            text='"I have more questions."',
            next_node_id="qm_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )
        db.insert_dialogue_option(
            id="qm_guns_leave",
            node_id="qm_where_guns",
            text='"Thanks."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        # Have gun -> back or leave
        db.insert_dialogue_option(
            id="qm_have_gun_back",
            node_id="qm_have_gun",
            text='"Anything else I should know?"',
            next_node_id="qm_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )
        db.insert_dialogue_option(
            id="qm_have_gun_leave",
            node_id="qm_have_gun",
            text='"Roger that."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        # ==============================================================
        # 7. Locks
        # ==============================================================

        # State Lock: Firing Range -> Bunker (requires both targets shot)
        db.insert_lock(
            id="bunker_hatch_lock",
            lock_type="state",
            target_exit_id="range_to_bunker",
            key_item_id=None,
            puzzle_id=None,
            combination=None,
            required_flags=json.dumps([
                "p226_target_hit",
                "ar15_target_hit",
            ]),
            locked_message=(
                "The bunker hatch display reads: QUALIFICATION INCOMPLETE. "
                "Requirements: P226 Qualification [  ], AR-15 Qualification "
                "[  ]. Shoot both targets to gain access."
            ),
            unlock_message=(
                "The bunker hatch display turns green: QUALIFICATION "
                "COMPLETE. The electronic bolts retract and the hatch "
                "swings open."
            ),
            is_locked=1,
            consume_key=0,
        )

        # ==============================================================
        # 8. Puzzles
        # ==============================================================

        # P226 Qualification
        db.insert_puzzle(
            id="p226_qualification",
            name="P226 Qualification",
            description="Load and fire the P226 pistol at the pistol target.",
            room_id="firing_range",
            is_solved=0,
            solution_steps=json.dumps([
                "Find the P226 magazine and 9mm ammo on the ammo shelf",
                "Load the P226 magazine with 9mm ammo",
                "Find the P226 pistol in the weapon locker",
                "Load the P226 with the loaded magazine",
                "Shoot the pistol target at the firing range",
            ]),
            hint_text=json.dumps([
                "The P226 magazine and 9mm ammo are on the ammo shelf.",
                "Load ammo into the magazine first, then magazine into gun.",
                "The P226 is in the weapon locker -- you need the locker key.",
            ]),
            difficulty=1,
            score_value=15,
            is_optional=0,
        )

        # AR-15 Qualification
        db.insert_puzzle(
            id="ar15_qualification",
            name="AR-15 Qualification",
            description="Load and fire the AR-15 rifle at the rifle target.",
            room_id="firing_range",
            is_solved=0,
            solution_steps=json.dumps([
                "Find the AR-15 magazine and 5.56mm ammo on the ammo shelf",
                "Load the AR-15 magazine with 5.56mm ammo",
                "Find the AR-15 in the weapon locker",
                "Load the AR-15 with the loaded magazine",
                "Shoot the rifle target at the firing range",
            ]),
            hint_text=json.dumps([
                "The AR-15 magazine and 5.56mm ammo are on the ammo shelf.",
                "Load ammo into the magazine first, then magazine into gun.",
                "The AR-15 is in the weapon locker with the P226.",
            ]),
            difficulty=1,
            score_value=15,
            is_optional=0,
        )

        # ==============================================================
        # 9. Quests and Quest Objectives
        # ==============================================================

        # --- Main Quest: Range Qualification ---
        db.insert_quest(
            id="range_qualification",
            name="Range Qualification",
            description=(
                "Load and fire both the P226 and AR-15 at their targets, "
                "then enter the bunker to complete qualification."
            ),
            quest_type="main",
            status="undiscovered",
            discovery_flag=None,
            completion_flag="range_qualification_complete",
            score_value=25,
            sort_order=0,
        )

        db.insert_quest_objective(
            id="obj_p226_qualify",
            quest_id="range_qualification",
            description="Qualify with the P226 pistol",
            completion_flag="p226_target_hit",
            order_index=1,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="obj_ar15_qualify",
            quest_id="range_qualification",
            description="Qualify with the AR-15 rifle",
            completion_flag="ar15_target_hit",
            order_index=2,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="obj_enter_bunker",
            quest_id="range_qualification",
            description="Enter the bunker and use the qualification card",
            completion_flag="range_qualification_complete",
            order_index=3,
            is_optional=0,
            bonus_score=0,
        )

        # --- Side Quest: Field Medic ---
        db.insert_quest(
            id="field_medic",
            name="Field Medic",
            description=(
                "Find and use the medical supplies in the storage room."
            ),
            quest_type="side",
            status="undiscovered",
            discovery_flag="found_medical_supplies",
            completion_flag="field_medic_complete",
            score_value=10,
            sort_order=1,
        )

        db.insert_quest_objective(
            id="obj_find_bandages",
            quest_id="field_medic",
            description="Find the bandages",
            completion_flag="found_bandages",
            order_index=1,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="obj_use_bandages",
            quest_id="field_medic",
            description="Use the bandages",
            completion_flag="used_bandages",
            order_index=2,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="obj_use_painkillers",
            quest_id="field_medic",
            description="Use the painkillers",
            completion_flag="used_painkillers",
            order_index=3,
            is_optional=1,
            bonus_score=5,
        )

        # ==============================================================
        # 10. Commands (DSL)
        # ==============================================================

        # ---- P226 GUN SYSTEM ----

        # Load P226 magazine with 9mm ammo (load {target})
        db.insert_command(
            id="load_p226_magazine",
            verb="load",
            pattern="load {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "p226_magazine"},
                {"type": "has_item", "item": "9mm_ammo"},
                {"type": "not_flag", "flag": "p226_mag_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "9mm_ammo"},
                {"type": "set_flag", "flag": "p226_mag_loaded"},
                {"type": "print", "message": "You slide 9mm rounds into the P226 magazine one by one until it clicks full. The magazine is loaded."},
            ]),
            success_message="",
            failure_message="You need the P226 magazine and 9mm ammo to do that.",
            context_room_ids=None,
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The P226 magazine is already loaded.",
        )

        # Put 9mm in P226 magazine (put {item} in {target})
        db.insert_command(
            id="put_9mm_in_p226_mag",
            verb="put",
            pattern="put {item} in {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "p226_magazine"},
                {"type": "has_item", "item": "9mm_ammo"},
                {"type": "not_flag", "flag": "p226_mag_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "9mm_ammo"},
                {"type": "set_flag", "flag": "p226_mag_loaded"},
                {"type": "print", "message": "You slide 9mm rounds into the P226 magazine one by one until it clicks full. The magazine is loaded."},
            ]),
            success_message="",
            failure_message="You need the P226 magazine and 9mm ammo to do that.",
            context_room_ids=None,
            puzzle_id=None,
            priority=20,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The P226 magazine is already loaded.",
        )

        # Load P226 with loaded magazine (load {target})
        db.insert_command(
            id="load_p226_gun",
            verb="load",
            pattern="load {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "p226"},
                {"type": "has_item", "item": "p226_magazine"},
                {"type": "has_flag", "flag": "p226_mag_loaded"},
                {"type": "not_flag", "flag": "p226_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "p226_magazine"},
                {"type": "set_flag", "flag": "p226_loaded"},
                {"type": "print", "message": "You slam the loaded magazine into the P226 grip. It seats with a satisfying click. You rack the slide -- a round chambers. The P226 is ready to fire."},
            ]),
            success_message="",
            failure_message="You need the P226 and a loaded P226 magazine.",
            context_room_ids=None,
            puzzle_id=None,
            priority=5,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The P226 is already loaded.",
        )

        # Put P226 magazine in P226 (put {item} in {target})
        db.insert_command(
            id="put_p226_mag_in_p226",
            verb="put",
            pattern="put {item} in {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "p226"},
                {"type": "has_item", "item": "p226_magazine"},
                {"type": "has_flag", "flag": "p226_mag_loaded"},
                {"type": "not_flag", "flag": "p226_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "p226_magazine"},
                {"type": "set_flag", "flag": "p226_loaded"},
                {"type": "print", "message": "You slam the loaded magazine into the P226 grip. It seats with a satisfying click. You rack the slide -- a round chambers. The P226 is ready to fire."},
            ]),
            success_message="",
            failure_message="You need the P226 and a loaded P226 magazine.",
            context_room_ids=None,
            puzzle_id=None,
            priority=20,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The P226 is already loaded.",
        )

        # Shoot pistol target with P226
        db.insert_command(
            id="shoot_p226_target",
            verb="shoot",
            pattern="shoot {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "p226"},
                {"type": "has_flag", "flag": "p226_loaded"},
                {"type": "in_room", "room": "firing_range"},
                {"type": "not_flag", "flag": "p226_target_hit"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "p226_target_hit"},
                {"type": "add_score", "points": 15},
                {"type": "solve_puzzle", "puzzle": "p226_qualification"},
                {"type": "print", "message": "You raise the P226, align the sights, and squeeze the trigger. The report cracks off the concrete walls. Downrange, the silhouette target jerks -- a hole dead center. P226 qualified."},
            ]),
            success_message="",
            failure_message="You need a loaded P226 and you need to be at the firing range.",
            context_room_ids=json.dumps(["firing_range"]),
            puzzle_id="p226_qualification",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The pistol target already has a hole in it. You've qualified with the P226.",
        )

        # ---- AR-15 GUN SYSTEM ----

        # Load AR-15 magazine with 5.56mm ammo (load {target})
        db.insert_command(
            id="load_ar15_magazine",
            verb="load",
            pattern="load {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "ar15_magazine"},
                {"type": "has_item", "item": "556_ammo"},
                {"type": "not_flag", "flag": "ar15_mag_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "556_ammo"},
                {"type": "set_flag", "flag": "ar15_mag_loaded"},
                {"type": "print", "message": "You press 5.56mm rounds into the STANAG magazine one by one. It takes thirty. The AR-15 magazine is loaded."},
            ]),
            success_message="",
            failure_message="You need the AR-15 magazine and 5.56mm ammo to do that.",
            context_room_ids=None,
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The AR-15 magazine is already loaded.",
        )

        # Put 5.56 in AR-15 magazine (put {item} in {target})
        db.insert_command(
            id="put_556_in_ar15_mag",
            verb="put",
            pattern="put {item} in {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "ar15_magazine"},
                {"type": "has_item", "item": "556_ammo"},
                {"type": "not_flag", "flag": "ar15_mag_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "556_ammo"},
                {"type": "set_flag", "flag": "ar15_mag_loaded"},
                {"type": "print", "message": "You press 5.56mm rounds into the STANAG magazine one by one. It takes thirty. The AR-15 magazine is loaded."},
            ]),
            success_message="",
            failure_message="You need the AR-15 magazine and 5.56mm ammo to do that.",
            context_room_ids=None,
            puzzle_id=None,
            priority=20,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The AR-15 magazine is already loaded.",
        )

        # Load AR-15 with loaded magazine (load {target})
        db.insert_command(
            id="load_ar15_gun",
            verb="load",
            pattern="load {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "ar15"},
                {"type": "has_item", "item": "ar15_magazine"},
                {"type": "has_flag", "flag": "ar15_mag_loaded"},
                {"type": "not_flag", "flag": "ar15_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "ar15_magazine"},
                {"type": "set_flag", "flag": "ar15_loaded"},
                {"type": "print", "message": "You rock the loaded magazine into the AR-15 magwell until it clicks. You slap the bolt release -- a round chambers with a metallic snap. The AR-15 is ready to fire."},
            ]),
            success_message="",
            failure_message="You need the AR-15 and a loaded AR-15 magazine.",
            context_room_ids=None,
            puzzle_id=None,
            priority=5,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The AR-15 is already loaded.",
        )

        # Put AR-15 magazine in AR-15 (put {item} in {target})
        db.insert_command(
            id="put_ar15_mag_in_ar15",
            verb="put",
            pattern="put {item} in {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "ar15"},
                {"type": "has_item", "item": "ar15_magazine"},
                {"type": "has_flag", "flag": "ar15_mag_loaded"},
                {"type": "not_flag", "flag": "ar15_loaded"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "ar15_magazine"},
                {"type": "set_flag", "flag": "ar15_loaded"},
                {"type": "print", "message": "You rock the loaded magazine into the AR-15 magwell until it clicks. You slap the bolt release -- a round chambers with a metallic snap. The AR-15 is ready to fire."},
            ]),
            success_message="",
            failure_message="You need the AR-15 and a loaded AR-15 magazine.",
            context_room_ids=None,
            puzzle_id=None,
            priority=20,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The AR-15 is already loaded.",
        )

        # Shoot rifle target with AR-15
        db.insert_command(
            id="shoot_ar15_target",
            verb="shoot",
            pattern="shoot {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "ar15"},
                {"type": "has_flag", "flag": "ar15_loaded"},
                {"type": "in_room", "room": "firing_range"},
                {"type": "not_flag", "flag": "ar15_target_hit"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "ar15_target_hit"},
                {"type": "add_score", "points": 15},
                {"type": "solve_puzzle", "puzzle": "ar15_qualification"},
                {"type": "print", "message": "You shoulder the AR-15, settle the red dot on the steel plate, and squeeze. The rifle bucks and the report slams your ears. Fifty meters out, the steel plate rings like a church bell. AR-15 qualified."},
            ]),
            success_message="",
            failure_message="You need a loaded AR-15 and you need to be at the firing range.",
            context_room_ids=json.dumps(["firing_range"]),
            puzzle_id="ar15_qualification",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The rifle target already has a dent in it. You've qualified with the AR-15.",
        )

        # ---- UNLOCK BUNKER AND SPAWN QUALIFICATION CARD ----

        # When both targets are hit, open the hatch (triggered by last shoot)
        # This command auto-fires when the player tries to go down after both flags
        db.insert_command(
            id="unlock_bunker_hatch",
            verb="open",
            pattern="open {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "firing_range"},
                {"type": "has_flag", "flag": "p226_target_hit"},
                {"type": "has_flag", "flag": "ar15_target_hit"},
            ]),
            effects=json.dumps([
                {"type": "unlock", "lock": "bunker_hatch_lock"},
                {"type": "spawn_item", "item": "qualification_card", "location": "_inventory"},
                {"type": "print", "message": "The bunker hatch display turns green: QUALIFICATION COMPLETE. The electronic bolts retract and the hatch swings open. A qualification card slides out of a slot in the wall -- you catch it."},
            ]),
            success_message="",
            failure_message="The hatch display reads: QUALIFICATION INCOMPLETE. Shoot both targets.",
            context_room_ids=json.dumps(["firing_range"]),
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The bunker hatch is already open.",
        )

        # ---- CONSUMABLE COMMANDS ----

        # Use bandages
        db.insert_command(
            id="use_bandages",
            verb="use",
            pattern="use {item}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "bandages"},
            ]),
            effects=json.dumps([
                {"type": "change_health", "amount": 20},
                {"type": "remove_item", "item": "bandages"},
                {"type": "set_flag", "flag": "used_bandages"},
                {"type": "print", "message": "You wrap the gauze bandages around your injuries. The pressure helps. You feel better."},
            ]),
            success_message="",
            failure_message="You don't have bandages.",
            context_room_ids=None,
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # Use painkillers
        db.insert_command(
            id="use_painkillers",
            verb="use",
            pattern="use {item}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "painkillers"},
            ]),
            effects=json.dumps([
                {"type": "change_health", "amount": 15},
                {"type": "remove_item", "item": "painkillers"},
                {"type": "set_flag", "flag": "used_painkillers"},
                {"type": "print", "message": "You pop two ibuprofen tablets and swallow them dry. The pain starts to ebb after a few minutes."},
            ]),
            success_message="",
            failure_message="You don't have painkillers.",
            context_room_ids=None,
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # ---- WIN CONDITION: Use qualification card in bunker ----

        # Use qualification card (use {item})
        db.insert_command(
            id="use_qual_card_bunker",
            verb="use",
            pattern="use {item}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "qualification_card"},
                {"type": "in_room", "room": "bunker"},
                {"type": "has_flag", "flag": "p226_target_hit"},
                {"type": "has_flag", "flag": "ar15_target_hit"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "range_qualification_complete"},
                {"type": "add_score", "points": 25},
                {"type": "print", "message": "You feed the qualification card into the scanner. The machine whirs, clicks, and the display reads: ALL QUALIFICATIONS VERIFIED. CLEARANCE GRANTED. The heavy hatch above swings open. Daylight streams in."},
            ]),
            success_message="",
            failure_message="You need to complete all qualifications first.",
            context_room_ids=json.dumps(["bunker"]),
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="You've already been cleared. The exit is open.",
        )

        # Use qualification card on scanner (alias)
        db.insert_command(
            id="use_qual_card_on_scanner",
            verb="use",
            pattern="use {item} on {target}",
            preconditions=json.dumps([
                {"type": "has_item", "item": "qualification_card"},
                {"type": "in_room", "room": "bunker"},
                {"type": "has_flag", "flag": "p226_target_hit"},
                {"type": "has_flag", "flag": "ar15_target_hit"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "range_qualification_complete"},
                {"type": "add_score", "points": 25},
                {"type": "print", "message": "You feed the qualification card into the scanner. The machine whirs, clicks, and the display reads: ALL QUALIFICATIONS VERIFIED. CLEARANCE GRANTED. The heavy hatch above swings open. Daylight streams in."},
            ]),
            success_message="",
            failure_message="You need to complete all qualifications first.",
            context_room_ids=json.dumps(["bunker"]),
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="You've already been cleared. The exit is open.",
        )

        # ---- PRECONDITION / EFFECT COVERAGE COMMANDS ----

        # health_above precondition test
        db.insert_command(
            id="check_health",
            verb="check",
            pattern="check {target}",
            preconditions=json.dumps([
                {"type": "health_above", "threshold": 50},
            ]),
            effects=json.dumps([
                {"type": "print", "message": "You feel healthy enough to continue."},
            ]),
            success_message="",
            failure_message="You feel weak. Find medical supplies.",
            context_room_ids=None,
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # npc_in_room precondition test
        db.insert_command(
            id="salute_quartermaster",
            verb="salute",
            pattern="salute {target}",
            preconditions=json.dumps([
                {"type": "npc_in_room", "npc": "quartermaster", "room": "_current"},
            ]),
            effects=json.dumps([
                {"type": "print", "message": "You give Hayes a nod. He nods back. 'Stay safe out there, shooter.'"},
            ]),
            success_message="",
            failure_message="There's no one here to salute.",
            context_room_ids=None,
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # container_open precondition test
        db.insert_command(
            id="rummage_crate",
            verb="rummage",
            pattern="rummage {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "storage_room"},
                {"type": "container_open", "container": "supply_crate"},
            ]),
            effects=json.dumps([
                {"type": "print", "message": "You rummage through the crate more thoroughly. Nothing else of interest -- just packing material and old receipts."},
            ]),
            success_message="",
            failure_message="You need to open it first.",
            context_room_ids=json.dumps(["storage_room"]),
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="You've already rummaged through this. Nothing left.",
        )

        # lock_unlocked precondition test
        db.insert_command(
            id="inspect_hatch",
            verb="inspect",
            pattern="inspect {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "firing_range"},
                {"type": "lock_unlocked", "lock": "bunker_hatch_lock"},
            ]),
            effects=json.dumps([
                {"type": "print", "message": "The bunker hatch display shows green. All qualifications verified. The hatch is open."},
            ]),
            success_message="",
            failure_message="The hatch display shows red. Qualifications incomplete.",
            context_room_ids=json.dumps(["firing_range"]),
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # puzzle_solved precondition test
        db.insert_command(
            id="review_scores",
            verb="review",
            pattern="review {target}",
            preconditions=json.dumps([
                {"type": "puzzle_solved", "puzzle": "p226_qualification"},
            ]),
            effects=json.dumps([
                {"type": "print", "message": "P226 Qualification: PASS. Center mass hit confirmed."},
            ]),
            success_message="",
            failure_message="No qualification results to review yet.",
            context_room_ids=None,
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # discover_quest effect test (discover field medic quest)
        db.insert_command(
            id="search_storage",
            verb="search",
            pattern="search {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "storage_room"},
                {"type": "not_flag", "flag": "found_medical_supplies"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "found_medical_supplies"},
                {"type": "set_flag", "flag": "found_bandages"},
                {"type": "discover_quest", "quest": "field_medic"},
                {"type": "print", "message": "You search the storage room thoroughly. There's a med kit on the wall with bandages and painkillers inside. Could come in handy."},
            ]),
            success_message="",
            failure_message="",
            context_room_ids=json.dumps(["storage_room"]),
            puzzle_id=None,
            priority=0,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="You've already searched this room.",
        )

        # ==============================================================
        # 11. Flags
        # ==============================================================

        flags = [
            # Dialogue flags
            ("asked_qualification", "false",
             "Set when player asks quartermaster about qualification."),
            ("asked_gun_location", "false",
             "Set when player asks quartermaster about gun locations."),
            ("got_gun_advice", "false",
             "Set when quartermaster gives gun advice (inventory-reactive)."),
            # P226 progression
            ("p226_mag_loaded", "false",
             "Set when the P226 magazine is loaded with 9mm ammo."),
            ("p226_loaded", "false",
             "Set when the P226 has a loaded magazine inserted."),
            ("p226_target_hit", "false",
             "Set when the pistol target is hit with the P226."),
            # AR-15 progression
            ("ar15_mag_loaded", "false",
             "Set when the AR-15 magazine is loaded with 5.56mm ammo."),
            ("ar15_loaded", "false",
             "Set when the AR-15 has a loaded magazine inserted."),
            ("ar15_target_hit", "false",
             "Set when the rifle target is hit with the AR-15."),
            # Medical / side quest
            ("found_medical_supplies", "false",
             "Set when storage room is searched. Discovers field medic quest."),
            ("found_bandages", "false",
             "Set when bandages are found."),
            ("used_bandages", "false",
             "Set when bandages are consumed."),
            ("used_painkillers", "false",
             "Set when painkillers are consumed."),
            ("field_medic_complete", "false",
             "Set when Field Medic side quest is completed."),
            # Win/lose flags
            ("range_qualification_complete", "false",
             "WIN CONDITION: set when qualification card is used in bunker."),
            ("player_dead", "false",
             "LOSE CONDITION: set if HP drops to 0."),
        ]
        for fid, fval, fdesc in flags:
            db.insert_flag(id=fid, value=fval, description=fdesc)

        # ==============================================================
        # 12. Initialize player state
        # ==============================================================
        db.init_player(start_room_id="armory", hp=100, max_hp=100)

    return output


if __name__ == "__main__":
    path = build_game()
    print(f"Test game created at {path}")
