"""Build a hand-crafted zombie apocalypse test game to validate the AnyZork engine.

Game: "Dead City: Escape"

You wake up in your apartment to the sound of screaming. The city has fallen
to a zombie outbreak overnight. You need to escape. Scavenge supplies, deal
with locked doors, solve puzzles, talk to survivors, search containers, and
survive long enough to reach the gas station at the edge of town where an
escape truck is waiting.

Layout:

    Apartment Building Region:
        [bedroom] --(east)--> [living_room] --(east)--> [kitchen]
                                    |                       |
                                  (down, locked)          (down, hidden)
                                    |                       |
                              [building_lobby]         [fire_escape]
                                    |
                                  (east)
                                    |
    Street Region:                  |
                              [main_street] --(east)--> [abandoned_car]
                                    |
                                  (south)
                                    |
    Gas Station Region:             |
                            [gas_station_lot] --(north, locked)--> [gas_station_interior]

Win condition: Start the escape truck (requires finding keys + fuel)

Container showcase:
    - Abandoned car: glovebox (locked), backseat (open/no lid),
      trunk (locked via lever), under seat (open/no lid)
    - Kitchen: kitchen drawer (closed), kitchen cabinet (open/no lid)
    - Apartment: medicine cabinet (closed), nightstand (closed)

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
            game_name="Dead City: Escape",
            author="Level Designer Agent (test harness)",
            prompt="A zombie apocalypse survival escape. Wake up, scavenge, survive, escape.",
            seed="zombie-42",
            intro_text=(
                "You wake to the sound of breaking glass and distant screaming. Your "
                "apartment is dark -- the power went out sometime in the night. Through "
                "the bedroom window you can see fires burning across the skyline. Something "
                "is very, very wrong. Your phone is dead. The emergency broadcast was the "
                "last thing you heard before you fell asleep: 'Seek shelter. Do not engage. "
                "Evacuation point: Mercer Street Gas Station.' Time to move."
            ),
            win_text=(
                "The truck's engine catches with a deep, rumbling roar. You throw it "
                "into gear and the tires bite asphalt. In the mirror, you see shapes "
                "stumbling out of the darkness behind you, but they are already shrinking. "
                "The gas station sign flickers once and dies. Ahead, the highway stretches "
                "empty under a pale dawn sky. You made it out. You survived Dead City."
            ),
            lose_text=(
                "The world goes dark. The last thing you feel is cold hands and the "
                "smell of decay. The city claims another one."
            ),
            win_conditions=json.dumps(["escaped_city"]),
            lose_conditions=json.dumps(["player_dead"]),
            max_score=100,
            region_count=3,
            room_count=9,
        )

        # ==============================================================
        # 2. Rooms
        # ==============================================================

        # --- Apartment Building Region ---

        db.insert_room(
            id="bedroom",
            name="Your Bedroom",
            description=(
                "Your small bedroom. The sheets are tangled where you threw them off. "
                "Through the window, orange firelight flickers against the glass. The "
                "only exit leads east into the living room."
            ),
            short_description=(
                "Your bedroom. East leads to the living room."
            ),
            first_visit_text=(
                "You swing your feet onto the cold floor. The screaming outside has "
                "stopped. Somehow that is worse."
            ),
            region="Apartment Building",
            is_dark=0,
            is_start=1,
            visited=0,
        )

        db.insert_room(
            id="living_room",
            name="Living Room",
            description=(
                "The apartment living room. A couch faces a dead television. The front "
                "door is to the south -- wait, no, it leads down to the building lobby, "
                "but someone has wedged it shut with a chair. The kitchen is east. Your "
                "bedroom is west."
            ),
            short_description=(
                "The living room. Kitchen east, bedroom west. The lobby door is jammed "
                "with a chair -- you need the apartment key to go down."
            ),
            first_visit_text=(
                "The TV screen is cracked. Someone -- you, probably, in the panic last "
                "night -- knocked it over. The emergency broadcast is just a memory now."
            ),
            region="Apartment Building",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="kitchen",
            name="Kitchen",
            description=(
                "A cramped galley kitchen. Dishes are piled in the sink. The living room "
                "is back to the west."
            ),
            short_description=(
                "The kitchen. West to the living room."
            ),
            first_visit_text=(
                "The faucet drips. One drop at a time, loud in the silence."
            ),
            region="Apartment Building",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="fire_escape",
            name="Fire Escape",
            description=(
                "A rusted metal fire escape clinging to the side of the building. The "
                "alley below is dark and you can hear shuffling down there. The kitchen "
                "window is back to the north. The ladder descends to the street, but "
                "the bottom section is jammed with rust."
            ),
            short_description=(
                "The fire escape. Kitchen window north. The ladder is rusted shut."
            ),
            first_visit_text=(
                "The metal groans under your weight. Two stories down, something moves "
                "in the alley. You freeze. It passes."
            ),
            region="Apartment Building",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="building_lobby",
            name="Building Lobby",
            description=(
                "The ground-floor lobby of your apartment building. Mailboxes line one "
                "wall, most of them hanging open. The front door has been smashed in -- "
                "glass crunches underfoot. Bloody handprints streak the wall near the "
                "stairwell. The stairs lead back up to your apartment. The front door "
                "opens east onto the main street."
            ),
            short_description=(
                "The building lobby. Broken glass, bloody handprints. Stairs up to "
                "your apartment. East to the street."
            ),
            first_visit_text=(
                "The lobby smells like copper and something worse. Mrs. Chen's cat "
                "sits on the mail counter, watching you with flat yellow eyes. It is "
                "the only living thing in sight."
            ),
            region="Apartment Building",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        # --- Street Region ---

        db.insert_room(
            id="main_street",
            name="Main Street",
            description=(
                "The street is a warzone. Overturned cars, shattered storefronts, "
                "scattered belongings. A low fog creeps along the gutters. To the west, "
                "the door to your apartment building. To the east, an abandoned car sits "
                "at the curb with its driver-side door hanging open. To the south, a "
                "faded sign reads 'MERCER ST GAS' -- the evacuation point. A figure "
                "shambles in the distance."
            ),
            short_description=(
                "Main Street. Building west, abandoned car east, gas station south."
            ),
            first_visit_text=(
                "You step outside. The air tastes like smoke and rot. Somewhere, a car "
                "alarm wails and dies. You are not alone out here."
            ),
            region="Street",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="abandoned_car",
            name="Inside the Abandoned Car",
            description=(
                "You are sitting in the driver's seat of a wrecked sedan. The "
                "windshield is spider-cracked. The vinyl seats are torn and stained "
                "with something dark. The key is gone from the ignition."
            ),
            short_description=(
                "Inside the wrecked sedan. West to exit."
            ),
            first_visit_text=(
                "You slide into the seat. The car smells like old blood and spilled "
                "coffee."
            ),
            region="Street",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        # --- Gas Station Region ---

        db.insert_room(
            id="gas_station_lot",
            name="Gas Station Parking Lot",
            description=(
                "The parking lot of the Mercer Street Gas Station. Two rusted fuel "
                "pumps stand sentinel under a flickering canopy. The station building "
                "is to the north, but a heavy chain and padlock seal the front door. "
                "A faded EVACUATION POINT sign hangs from the canopy. A beat-up pickup "
                "truck sits near the pumps, its hood raised. The street is back to "
                "the north."
            ),
            short_description=(
                "Gas station lot. Chained door north. Pickup truck by the pumps. "
                "Street north."
            ),
            first_visit_text=(
                "The gas station canopy light buzzes and flickers. The evacuation "
                "point sign sways in a gust of hot wind. Nobody is here. Nobody "
                "came to evacuate."
            ),
            region="Gas Station",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        db.insert_room(
            id="gas_station_interior",
            name="Gas Station Interior",
            description=(
                "The inside of the gas station. Shelves have been picked clean, "
                "overturned and smashed. Behind the counter, a CB radio crackles with "
                "static. A back door leads to the alley behind the building -- and "
                "freedom. Through the grimy window, you can see the pickup truck "
                "in the lot."
            ),
            short_description=(
                "Inside the gas station. Ransacked shelves, a CB radio. The back "
                "door leads out. South to the lot."
            ),
            first_visit_text=(
                "You step inside. The floor is sticky with spilled soda and something "
                "you do not want to identify. The CB radio hisses: '...any survivors... "
                "highway north... do not stop...' Then static."
            ),
            region="Gas Station",
            is_dark=0,
            is_start=0,
            visited=0,
        )

        # ==============================================================
        # 3. Exits (bidirectional pairs)
        # ==============================================================

        # Bedroom <-> Living Room
        db.insert_exit(
            id="bedroom_to_living",
            from_room_id="bedroom",
            to_room_id="living_room",
            direction="east",
            description="The living room is through the doorway to the east.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="living_to_bedroom",
            from_room_id="living_room",
            to_room_id="bedroom",
            direction="west",
            description="Your bedroom is to the west.",
            is_locked=0,
            is_hidden=0,
        )

        # Living Room <-> Kitchen
        db.insert_exit(
            id="living_to_kitchen",
            from_room_id="living_room",
            to_room_id="kitchen",
            direction="east",
            description="The kitchen is to the east.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="kitchen_to_living",
            from_room_id="kitchen",
            to_room_id="living_room",
            direction="west",
            description="The living room is back to the west.",
            is_locked=0,
            is_hidden=0,
        )

        # Kitchen <-> Fire Escape (HIDDEN -- revealed by examining window)
        db.insert_exit(
            id="kitchen_to_fire_escape",
            from_room_id="kitchen",
            to_room_id="fire_escape",
            direction="south",
            description="The kitchen window leads out to the fire escape.",
            is_locked=0,
            is_hidden=1,
        )
        db.insert_exit(
            id="fire_escape_to_kitchen",
            from_room_id="fire_escape",
            to_room_id="kitchen",
            direction="north",
            description="The kitchen window is back to the north.",
            is_locked=0,
            is_hidden=0,
        )

        # Living Room <-> Building Lobby (LOCKED -- requires apartment key)
        db.insert_exit(
            id="living_to_lobby",
            from_room_id="living_room",
            to_room_id="building_lobby",
            direction="down",
            description="The door to the building lobby is down the stairs.",
            is_locked=1,
            is_hidden=0,
        )
        db.insert_exit(
            id="lobby_to_living",
            from_room_id="building_lobby",
            to_room_id="living_room",
            direction="up",
            description="Stairs lead back up to your apartment.",
            is_locked=0,
            is_hidden=0,
        )

        # Building Lobby <-> Main Street
        db.insert_exit(
            id="lobby_to_street",
            from_room_id="building_lobby",
            to_room_id="main_street",
            direction="east",
            description="The smashed front door opens east onto the main street.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="street_to_lobby",
            from_room_id="main_street",
            to_room_id="building_lobby",
            direction="west",
            description="The apartment building entrance is to the west.",
            is_locked=0,
            is_hidden=0,
        )

        # Main Street <-> Abandoned Car
        db.insert_exit(
            id="street_to_car",
            from_room_id="main_street",
            to_room_id="abandoned_car",
            direction="east",
            description="An abandoned car sits at the curb to the east.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="car_to_street",
            from_room_id="abandoned_car",
            to_room_id="main_street",
            direction="west",
            description="Step out of the car back to the street.",
            is_locked=0,
            is_hidden=0,
        )

        # Main Street <-> Gas Station Lot
        db.insert_exit(
            id="street_to_gas_lot",
            from_room_id="main_street",
            to_room_id="gas_station_lot",
            direction="south",
            description="A sign points south to the Mercer Street Gas Station.",
            is_locked=0,
            is_hidden=0,
        )
        db.insert_exit(
            id="gas_lot_to_street",
            from_room_id="gas_station_lot",
            to_room_id="main_street",
            direction="north",
            description="The street is back to the north.",
            is_locked=0,
            is_hidden=0,
        )

        # Gas Station Lot <-> Gas Station Interior (LOCKED -- padlock, bolt cutters)
        db.insert_exit(
            id="gas_lot_to_interior",
            from_room_id="gas_station_lot",
            to_room_id="gas_station_interior",
            direction="east",
            description="The gas station building entrance is to the east, sealed with a chain.",
            is_locked=1,
            is_hidden=0,
        )
        db.insert_exit(
            id="interior_to_gas_lot",
            from_room_id="gas_station_interior",
            to_room_id="gas_station_lot",
            direction="west",
            description="The front door leads back west to the parking lot.",
            is_locked=0,
            is_hidden=0,
        )

        # ==============================================================
        # 4. Items -- containers first, then contained items, then loose
        # ==============================================================

        # ---- CONTAINERS ----

        # Bedroom: Nightstand (closed, unlocked)
        db.insert_item(
            id="nightstand",
            name="nightstand",
            description="A small nightstand beside your bed, drawer closed.",
            examine_description=(
                "A cheap IKEA nightstand. The single drawer is closed. "
                "You keep your essentials in here."
            ),
            room_id="bedroom",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=0,
            open_message="You pull open the nightstand drawer.",
            search_message="You rummage through the nightstand drawer...",
            category="scenery",
            room_description=(
                "A nightstand sits beside the bed, its single drawer closed."
            ),
        )

        # Kitchen: Kitchen Drawer (closed, unlocked)
        db.insert_item(
            id="kitchen_drawer",
            name="kitchen drawer",
            description="A cluttered kitchen drawer beneath the counter.",
            examine_description=(
                "The junk drawer. Every apartment has one. It's half-open -- "
                "you can see the glint of metal inside."
            ),
            room_id="kitchen",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=0,
            open_message="You pull the kitchen drawer open. It sticks, then slides free.",
            search_message="You dig through the junk drawer...",
            category="scenery",
            room_description=(
                "A kitchen drawer sits half-open beneath the counter."
            ),
        )

        # Kitchen: Overhead Cabinet (open, no lid -- always accessible)
        db.insert_item(
            id="kitchen_cabinet",
            name="kitchen cabinet",
            description="An overhead cabinet above the stove, door hanging open.",
            examine_description=(
                "The cabinet door hangs open on one hinge. You can see a few "
                "items still on the shelves."
            ),
            room_id="kitchen",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=1,
            has_lid=0,
            is_locked=0,
            search_message="You reach into the overhead cabinet...",
            category="scenery",
            room_description=(
                "An overhead cabinet hangs above the stove, its door ajar."
            ),
        )

        # Living Room: Medicine Cabinet (in bathroom, but treating as living
        # room fixture for simplicity -- "the bathroom is part of the apartment")
        # Actually, let's put a medicine cabinet in the bedroom
        # as a wall-mounted cabinet near the bed.
        db.insert_item(
            id="medicine_cabinet",
            name="medicine cabinet",
            description="A small medicine cabinet mounted on the wall.",
            examine_description=(
                "A mirrored medicine cabinet. The mirror is cracked down "
                "the middle. The cabinet is closed."
            ),
            room_id="bedroom",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=0,
            open_message="You swing open the medicine cabinet. The cracked mirror reflects your exhausted face.",
            search_message="You look through the medicine cabinet shelves...",
            category="scenery",
            room_description=(
                "A small medicine cabinet is mounted on the wall, its mirror cracked down the middle."
            ),
        )

        # Car: Glovebox (locked -- needs crowbar as key; key_item_id set later
        # after the crowbar item is inserted, to avoid FK constraint issues)
        db.insert_item(
            id="car_glovebox",
            name="glovebox",
            description="The car's glovebox, latched shut.",
            examine_description=(
                "A standard glovebox in the dashboard. The latch is jammed -- "
                "it's locked. You'd need something to pry it open."
            ),
            room_id="abandoned_car",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=1,
            lock_message="The glovebox is jammed shut. You need something to pry it open.",
            open_message="The glovebox drops open, revealing its contents.",
            category="scenery",
            room_description=(
                "The glovebox is latched shut in the dashboard."
            ),
            consume_key=0,
            unlock_message=(
                "You jam the crowbar into the glovebox latch and twist. The cheap "
                "plastic cracks and the glovebox drops open, spilling papers and a "
                "small flashlight."
            ),
        )

        # Car: Backseat (open, no lid -- always searchable)
        db.insert_item(
            id="car_backseat",
            name="backseat",
            description="The car's backseat, littered with garbage.",
            examine_description=(
                "The backseat is covered in fast-food wrappers, old newspapers, "
                "and empty cans. There might be something buried in the mess."
            ),
            room_id="abandoned_car",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=1,
            has_lid=0,
            is_locked=0,
            search_message="You dig through the garbage on the backseat...",
            category="scenery",
            room_description=(
                "The backseat is littered with fast-food wrappers and old newspapers."
            ),
        )

        # Car: Under the Seat (open, no lid)
        db.insert_item(
            id="car_under_seat",
            name="under the seat",
            description="The dark space beneath the driver's seat.",
            examine_description=(
                "You lean down and peer under the seat. It's dark and gritty "
                "under there. Something metallic glints."
            ),
            room_id="abandoned_car",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=1,
            has_lid=0,
            is_locked=0,
            search_message="You reach under the seat and feel around...",
            category="scenery",
            room_description=(
                "Something rattles in the dark space under the seat."
            ),
        )

        # Car: Trunk (locked, opened by lever)
        db.insert_item(
            id="car_trunk",
            name="trunk",
            description="The car's trunk. A release lever is near your left knee.",
            examine_description=(
                "You can't see inside the trunk from the driver's seat, but "
                "there's a release lever by your left knee. You could pull it "
                "to pop the trunk open."
            ),
            room_id="abandoned_car",
            is_takeable=0,
            is_visible=1,
            is_container=1,
            is_open=0,
            has_lid=1,
            is_locked=1,
            lock_message="The trunk is closed. There's a release lever by your left knee.",
            open_message="You hear a thunk from behind as the trunk pops open.",
            category="scenery",
            room_description=(
                "The car's trunk is closed tight."
            ),
        )

        # ---- ITEMS INSIDE CONTAINERS ----

        # In nightstand
        db.insert_item(
            id="apartment_key",
            name="apartment key",
            description="Your apartment key on a plain ring.",
            examine_description=(
                "A single brass key on a cheap keyring. It opens the deadbolt "
                "on your apartment door -- the one leading down to the lobby."
            ),
            room_id=None,
            container_id="nightstand",
            is_takeable=1,
            is_visible=1,
            take_message="You grab your apartment key. You'll need this to get out.",
            weight=1,
            category="key",
        )

        db.insert_item(
            id="phone_charger",
            name="phone charger",
            description="A tangled phone charger cable. Useless without power.",
            examine_description=(
                "A USB-C charger cable. Your phone is dead and there's no power. "
                "This is completely useless right now."
            ),
            room_id=None,
            container_id="nightstand",
            is_takeable=1,
            is_visible=1,
            weight=1,
            category="junk",
        )

        # In medicine cabinet
        db.insert_item(
            id="bandages",
            name="bandages",
            description="A roll of gauze bandages.",
            examine_description=(
                "Clean gauze bandages, still in their packaging. Could be useful "
                "if you get hurt. In this city, that seems likely."
            ),
            room_id=None,
            container_id="medicine_cabinet",
            is_takeable=1,
            is_visible=1,
            take_message="You pocket the bandages. Smart.",
            weight=1,
            category="supply",
        )

        db.insert_item(
            id="painkillers",
            name="painkillers",
            description="A half-empty bottle of ibuprofen.",
            examine_description=(
                "About a dozen tablets left. Not much, but enough to dull the "
                "pain if something goes wrong."
            ),
            room_id=None,
            container_id="medicine_cabinet",
            is_takeable=1,
            is_visible=1,
            take_message="You take the painkillers. Every little bit helps.",
            weight=1,
            category="supply",
        )

        # In kitchen drawer
        db.insert_item(
            id="kitchen_knife",
            name="kitchen knife",
            description="A heavy chef's knife.",
            examine_description=(
                "An 8-inch chef's knife, still sharp. Not designed as a weapon, "
                "but it'll do."
            ),
            room_id=None,
            container_id="kitchen_drawer",
            is_takeable=1,
            is_visible=1,
            take_message="You take the kitchen knife. It feels reassuring in your hand.",
            weight=2,
            category="weapon",
        )

        db.insert_item(
            id="duct_tape",
            name="duct tape",
            description="A half-used roll of duct tape.",
            examine_description=(
                "Silver duct tape. The handyman's secret weapon. About half a "
                "roll left."
            ),
            room_id=None,
            container_id="kitchen_drawer",
            is_takeable=1,
            is_visible=1,
            take_message="You grab the duct tape. Always useful.",
            weight=1,
            category="tool",
        )

        # In kitchen cabinet
        db.insert_item(
            id="canned_food",
            name="canned food",
            description="Two cans of beans.",
            examine_description=(
                "Two cans of pork and beans. No pull-tab, you'd need a can "
                "opener. But they'll keep you fed if you make it out."
            ),
            room_id=None,
            container_id="kitchen_cabinet",
            is_takeable=1,
            is_visible=1,
            take_message="You shove the cans into your pockets. Heavy but necessary.",
            weight=3,
            category="supply",
        )

        # In car glovebox
        db.insert_item(
            id="car_registration",
            name="registration papers",
            description="Vehicle registration papers, folded and stained.",
            examine_description=(
                "The registration belongs to a 'Marcus Webb' at 445 Mercer Street. "
                "The car is a 2004 Honda Civic. There's a sticky note attached: "
                "'Truck keys in the station. Under the counter. --M'"
            ),
            read_description=(
                "The registration belongs to Marcus Webb at 445 Mercer Street. "
                "A sticky note is attached: 'Truck keys in the station. Under "
                "the counter. --M' Someone left a getaway plan."
            ),
            room_id=None,
            container_id="car_glovebox",
            is_takeable=1,
            is_visible=1,
            weight=1,
            category="document",
        )

        db.insert_item(
            id="small_flashlight",
            name="small flashlight",
            description="A cheap plastic flashlight.",
            examine_description=(
                "A red plastic flashlight, about six inches long. You click it "
                "on -- weak but functional beam. Better than nothing in the dark."
            ),
            room_id=None,
            container_id="car_glovebox",
            is_takeable=1,
            is_visible=1,
            take_message="You take the flashlight. Could save your life in a dark room.",
            weight=1,
            category="tool",
        )

        # In car backseat
        db.insert_item(
            id="torn_map",
            name="torn map",
            description="A torn city map with markings in red ink.",
            examine_description=(
                "A gas station road map, torn in half. Someone has circled the "
                "Mercer Street Gas Station in red and drawn arrows pointing "
                "north along the highway. In shaky handwriting: 'GET OUT. NORTH. "
                "DON'T STOP.' The other half of the map is missing."
            ),
            read_description=(
                "A gas station road map, torn in half. Someone circled the Mercer "
                "Street Gas Station in red and drew arrows north along the highway. "
                "In shaky handwriting: 'GET OUT. NORTH. DON'T STOP.'"
            ),
            room_id=None,
            container_id="car_backseat",
            is_takeable=1,
            is_visible=1,
            weight=1,
            category="document",
        )

        # Under the car seat
        db.insert_item(
            id="crowbar",
            name="crowbar",
            description="A short, heavy crowbar.",
            examine_description=(
                "A 12-inch crowbar, cold and heavy in your hand. Perfect for "
                "prying things open. Or for self-defense."
            ),
            room_id=None,
            container_id="car_under_seat",
            is_takeable=1,
            is_visible=1,
            take_message="You grab the crowbar. This changes things.",
            weight=3,
            category="tool",
        )

        # In car trunk
        db.insert_item(
            id="bolt_cutters",
            name="bolt cutters",
            description="A pair of heavy-duty bolt cutters.",
            examine_description=(
                "Industrial bolt cutters, 24 inches long. These could cut through "
                "a padlock chain like butter."
            ),
            room_id=None,
            container_id="car_trunk",
            is_takeable=1,
            is_visible=1,
            take_message="You grab the bolt cutters. Now you can get through that chain.",
            weight=4,
            category="tool",
        )

        # ---- LOOSE ITEMS (in rooms) ----

        # Baseball bat in living room
        db.insert_item(
            id="baseball_bat",
            name="baseball bat",
            description="An aluminum baseball bat leaning against the wall.",
            examine_description=(
                "An aluminum Louisville Slugger. Dented near the sweet spot. "
                "Someone's already used this for something other than baseball."
            ),
            room_id="living_room",
            is_takeable=1,
            is_visible=1,
            take_message="You pick up the bat. It feels right.",
            drop_message="You set the bat down.",
            weight=3,
            category="weapon",
            room_description=(
                "An aluminum baseball bat leans against the wall by the door."
            ),
        )

        # Kitchen window (scenery -- examining reveals fire escape exit)
        db.insert_item(
            id="kitchen_window",
            name="kitchen window",
            description="A narrow window over the sink, smeared with grime.",
            examine_description=(
                "Through the grime, you can see a metal fire escape platform "
                "just outside. The window latch is rusty but functional. You "
                "could climb through."
            ),
            room_id="kitchen",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A narrow window over the sink is dark with grime."
            ),
        )

        # Bloody note in lobby
        db.insert_item(
            id="bloody_note",
            name="bloody note",
            description="A note pinned to the wall in brownish-red.",
            examine_description=(
                "Written in what looks like dried blood on a piece of cardboard: "
                "'THEY COME AT NIGHT. BOARD THE WINDOWS. IF YOU HEAR THEM DON'T "
                "OPEN THE DOOR. --APT 4B' The handwriting gets shakier toward "
                "the end."
            ),
            read_description=(
                "Written in what looks like dried blood on cardboard: 'THEY COME "
                "AT NIGHT. BOARD THE WINDOWS. IF YOU HEAR THEM DON'T OPEN THE "
                "DOOR. --APT 4B' The handwriting gets shakier toward the end."
            ),
            room_id="building_lobby",
            is_takeable=1,
            is_visible=1,
            weight=1,
            category="document",
            room_description=(
                "A note pinned to the wall near the mailboxes, written in what "
                "looks like dried blood."
            ),
        )

        # Trunk release lever in car (scenery)
        db.insert_item(
            id="trunk_release_lever",
            name="trunk release lever",
            description="A small lever near your left knee.",
            examine_description=(
                "A plastic lever with a trunk icon on it. Pull it to pop the trunk."
            ),
            room_id="abandoned_car",
            is_takeable=0,
            is_visible=1,
            is_container=0,
            category="scenery",
            room_description=(
                "A small trunk release lever sits near your left knee."
            ),
        )

        # Pickup truck in gas station lot (scenery -- the escape vehicle)
        db.insert_item(
            id="pickup_truck",
            name="pickup truck",
            description="A beat-up Ford F-150 near the fuel pumps, hood raised.",
            examine_description=(
                "An old Ford pickup. The hood is up -- someone was working on it. "
                "The engine looks intact but the gas tank is bone dry. There's a "
                "fuel can slot on the truck bed. If you had fuel and the keys, "
                "this thing might run."
            ),
            room_id="gas_station_lot",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A beat-up pickup truck sits near the fuel pumps, its hood raised."
            ),
        )

        # Gas station chain/padlock (scenery)
        db.insert_item(
            id="station_chain",
            name="chain",
            description="A heavy chain and padlock sealing the gas station door.",
            examine_description=(
                "A thick steel chain wrapped through the door handles, secured "
                "with a heavy padlock. You'd need bolt cutters to get through this."
            ),
            room_id="gas_station_lot",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A heavy chain and padlock seal the gas station's front door."
            ),
        )

        # Truck keys (hidden, inside gas station -- under counter)
        db.insert_item(
            id="truck_keys",
            name="truck keys",
            description="A set of Ford truck keys on a greasy keyring.",
            examine_description=(
                "Ford keys on a ring with a bottle opener and a faded Texaco "
                "loyalty tag. These must be for the pickup outside."
            ),
            room_id=None,
            is_takeable=1,
            is_visible=0,
            take_message="You grab the truck keys. This is your way out.",
            weight=1,
            category="key",
        )

        # Gas can (in gas station, needs to be found)
        db.insert_item(
            id="gas_can",
            name="gas can",
            description="A red plastic gas can, about two gallons.",
            examine_description=(
                "A standard red plastic gas can. You shake it -- maybe a half "
                "gallon of gas sloshes inside. Might be enough to get the truck "
                "out of the city."
            ),
            room_id="gas_station_interior",
            is_takeable=1,
            is_visible=1,
            take_message="You grab the gas can. It's light but not empty.",
            weight=4,
            category="supply",
            room_description=(
                "A red gas can sits behind the counter."
            ),
        )

        # CB Radio (scenery in gas station)
        db.insert_item(
            id="cb_radio",
            name="CB radio",
            description="A CB radio on the counter, crackling with static.",
            examine_description=(
                "The radio cycles through channels of static and fragments: "
                "'...military checkpoint at mile marker 40...' '...do not approach "
                "the hospitals...' '...if you can hear this, head north...' "
                "Then nothing but hiss."
            ),
            room_id="gas_station_interior",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "A CB radio on the counter hisses with fragments of distant voices."
            ),
        )

        # Counter in gas station (scenery -- searching reveals truck keys)
        db.insert_item(
            id="station_counter",
            name="counter",
            description="The gas station checkout counter.",
            examine_description=(
                "A standard checkout counter, covered in dust and debris. The "
                "register is smashed open, empty. Behind the counter... you "
                "notice a hook underneath where keys might hang."
            ),
            room_id="gas_station_interior",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "The checkout counter sits against the back wall, register smashed."
            ),
        )

        # Fire escape scenery
        db.insert_item(
            id="rusted_ladder",
            name="rusted ladder",
            description="The fire escape ladder, its bottom section rusted shut.",
            examine_description=(
                "The ladder's last section is fused with rust. You can see the "
                "alley two stories below. Even if you could free the ladder, "
                "the noise would attract attention. Better to find another way "
                "down."
            ),
            room_id="fire_escape",
            is_takeable=0,
            is_visible=1,
            category="scenery",
            room_description=(
                "The fire escape ladder hangs above the alley, its lower "
                "section rusted solid."
            ),
        )

        # ---- BACKFILL: Set key_item_id on containers (deferred to avoid FK issues) ----
        db._mutate(
            "UPDATE items SET key_item_id = ? WHERE id = ?",
            ("crowbar", "car_glovebox"),
        )

        # ==============================================================
        # 5. NPCs
        # ==============================================================

        # Survivor hiding in the lobby
        db.insert_npc(
            id="survivor_maria",
            name="Maria",
            description=(
                "A woman in her thirties crouches behind the mail counter, clutching "
                "a fire axe. Her eyes are wide but alert. She's been here a while."
            ),
            examine_description=(
                "Maria is wearing hospital scrubs -- she must be a nurse or doctor. "
                "There's dried blood on her sleeves but she doesn't appear injured. "
                "The fire axe in her hands is steady. She knows how to use it."
            ),
            room_id="building_lobby",
            is_alive=1,
            is_blocking=0,
            blocked_exit_id=None,
            unblock_flag=None,
            default_dialogue=(
                "'Keep your voice down,' Maria whispers. 'They can hear you. I've "
                "been hiding here since last night. The gas station -- that's the "
                "evacuation point. But the door is chained shut. You'll need bolt "
                "cutters.' She pauses. 'There was a car outside. Maybe check it.'"
            ),
            hp=None,
            damage=None,
        )

        # Zombie blocking the gas station approach
        # (well, it's in the gas station lot -- atmospheric NPC)
        db.insert_npc(
            id="shambling_zombie",
            name="shambling zombie",
            description=(
                "A figure in a torn business suit stumbles between the fuel pumps. "
                "Its jaw hangs at an impossible angle. It hasn't noticed you yet."
            ),
            examine_description=(
                "It used to be a man. The suit is expensive -- or was. One shoe "
                "is missing. Its skin has a grey-green pallor and its eyes are "
                "milky white. It moves in slow, jerking steps, sniffing the air. "
                "You could try to sneak past, or deal with it directly."
            ),
            room_id="gas_station_lot",
            is_alive=1,
            is_blocking=0,
            blocked_exit_id=None,
            unblock_flag=None,
            default_dialogue=(
                "The zombie groans -- a low, rattling sound that is not a word "
                "and never was. It turns toward you, arms rising."
            ),
            hp=20,
            damage=15,
        )

        # Another NPC: the voice on the radio (not physically present,
        # but we can have an NPC in the gas station for flavor)
        db.insert_npc(
            id="radio_voice",
            name="radio operator",
            description=(
                "A crackling voice on the CB radio, fading in and out of static."
            ),
            examine_description=(
                "You can't see the person speaking. The voice is calm, measured -- "
                "military, maybe. Someone who has done this before."
            ),
            room_id="gas_station_interior",
            is_alive=1,
            is_blocking=0,
            blocked_exit_id=None,
            unblock_flag=None,
            default_dialogue=(
                "'...checkpoint is at mile marker 40. Highway north. If you have "
                "a vehicle, do not stop until you reach it. They are faster at "
                "night. I repeat: they are faster at night. Over.'"
            ),
            hp=None,
            damage=None,
        )

        # ==============================================================
        # 6. Dialogue Trees
        # ==============================================================

        # ---- Maria's dialogue tree ----

        # Root node: Maria's introduction
        db.insert_dialogue_node(
            id="maria_root",
            npc_id="survivor_maria",
            content=(
                "'I'm Maria. I was working the night shift at St. Agnes when "
                "it all went to hell. People started biting -- patients, visitors, "
                "security. I grabbed this axe and ran.' She swallows hard. 'The "
                "gas station on Mercer is the evacuation point. Military was "
                "supposed to be there. I don't think they ever came.'"
            ),
            set_flags=json.dumps(["spoke_to_maria"]),
            is_root=1,
        )

        # Sub-nodes for each topic
        db.insert_dialogue_node(
            id="maria_hospital",
            npc_id="survivor_maria",
            content=(
                "'Don't call them that,' Maria says quietly. 'They're... they "
                "were people. Something happened. A virus, a chemical, I don't "
                "know. They're slow during the day but faster at night. Much "
                "faster. If you're going to move, do it now -- you've got maybe "
                "two hours of daylight left.'"
            ),
            set_flags=json.dumps(["knows_about_zombies"]),
            is_root=0,
        )

        db.insert_dialogue_node(
            id="maria_gas_station",
            npc_id="survivor_maria",
            content=(
                "'The gas station door is chained shut from outside. Someone "
                "locked it to keep them out -- or to keep something in. You'll "
                "need bolt cutters. There was a car parked on the street... "
                "check the trunk maybe.' She shakes her head. 'I'm not going "
                "out there. Not again.'"
            ),
            set_flags=json.dumps(["knows_about_station"]),
            is_root=0,
        )

        db.insert_dialogue_node(
            id="maria_building",
            npc_id="survivor_maria",
            content=(
                "'Most of the apartments are empty. People either evacuated "
                "early or...' She trails off. 'Don't go upstairs past the "
                "third floor. I heard sounds from up there. Not human sounds.'"
            ),
            set_flags=None,
            is_root=0,
        )

        db.insert_dialogue_node(
            id="maria_bolt_cutters_react",
            npc_id="survivor_maria",
            content=(
                "Maria's eyes widen. 'Bolt cutters! That's exactly what we "
                "need to get through the chain on the gas station door. Go -- "
                "cut that chain and get inside. The truck keys have to be in "
                "there somewhere.'"
            ),
            set_flags=None,
            is_root=0,
        )

        db.insert_dialogue_node(
            id="maria_registration_react",
            npc_id="survivor_maria",
            content=(
                "Maria takes the papers and scans them quickly. 'Marcus Webb... "
                "445 Mercer. That's the gas station owner.' She taps the sticky "
                "note. 'Truck keys under the counter. He left a getaway plan. "
                "Smart man. Let's hope he made it out.'"
            ),
            set_flags=None,
            is_root=0,
        )

        # Options from root node
        db.insert_dialogue_option(
            id="maria_opt_hospital",
            node_id="maria_root",
            text='"What happened at the hospital?"',
            next_node_id="maria_hospital",
            required_flags=None,
            excluded_flags=json.dumps(["asked_about_hospital"]),
            required_items=None,
            set_flags=json.dumps(["asked_about_hospital"]),
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="maria_opt_gas_station",
            node_id="maria_root",
            text='"Do you know about the gas station?"',
            next_node_id="maria_gas_station",
            required_flags=None,
            excluded_flags=json.dumps(["asked_about_station"]),
            required_items=None,
            set_flags=json.dumps(["asked_about_station"]),
            sort_order=1,
        )

        db.insert_dialogue_option(
            id="maria_opt_building",
            node_id="maria_root",
            text='"What about this building?"',
            next_node_id="maria_building",
            required_flags=None,
            excluded_flags=json.dumps(["asked_about_building"]),
            required_items=None,
            set_flags=json.dumps(["asked_about_building"]),
            sort_order=2,
        )

        db.insert_dialogue_option(
            id="maria_opt_bolt_cutters",
            node_id="maria_root",
            text='"I found bolt cutters!"',
            next_node_id="maria_bolt_cutters_react",
            required_flags=None,
            excluded_flags=json.dumps(["showed_maria_bolt_cutters"]),
            required_items=json.dumps(["bolt_cutters"]),
            set_flags=json.dumps(["showed_maria_bolt_cutters"]),
            sort_order=3,
        )

        db.insert_dialogue_option(
            id="maria_opt_registration",
            node_id="maria_root",
            text='"I found some papers in a car."',
            next_node_id="maria_registration_react",
            required_flags=None,
            excluded_flags=json.dumps(["showed_maria_registration"]),
            required_items=json.dumps(["car_registration"]),
            set_flags=json.dumps(["showed_maria_registration"]),
            sort_order=4,
        )

        # Sub-node options: loop back to root after viewing a topic
        db.insert_dialogue_option(
            id="maria_hospital_back",
            node_id="maria_hospital",
            text='"I have more questions."',
            next_node_id="maria_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="maria_hospital_leave",
            node_id="maria_hospital",
            text='"Thanks. Stay safe."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        db.insert_dialogue_option(
            id="maria_gas_station_back",
            node_id="maria_gas_station",
            text='"I have more questions."',
            next_node_id="maria_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="maria_gas_station_leave",
            node_id="maria_gas_station",
            text='"Thanks. Stay safe."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        db.insert_dialogue_option(
            id="maria_building_back",
            node_id="maria_building",
            text='"I have more questions."',
            next_node_id="maria_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="maria_building_leave",
            node_id="maria_building",
            text='"Thanks. Stay safe."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        db.insert_dialogue_option(
            id="maria_bolt_cutters_back",
            node_id="maria_bolt_cutters_react",
            text='"I have more questions."',
            next_node_id="maria_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="maria_bolt_cutters_leave",
            node_id="maria_bolt_cutters_react",
            text='"On it."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        db.insert_dialogue_option(
            id="maria_registration_back",
            node_id="maria_registration_react",
            text='"I have more questions."',
            next_node_id="maria_root",
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="maria_registration_leave",
            node_id="maria_registration_react",
            text='"Good to know."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=1,
        )

        # ---- Radio operator dialogue tree ----

        db.insert_dialogue_node(
            id="radio_root",
            npc_id="radio_voice",
            content=(
                "The radio crackles: '...this is an automated emergency broadcast. "
                "Evacuation route: Highway 1 North. Checkpoint at mile marker 40. "
                "Bring supplies. Bring fuel. Do not travel after dark. This message "
                "will repeat...'"
            ),
            set_flags=json.dumps(["heard_broadcast"]),
            is_root=1,
        )

        db.insert_dialogue_node(
            id="radio_checkpoint",
            npc_id="radio_voice",
            content=(
                "'...military checkpoint is at mile marker 40. Medical tents, "
                "food, water. Armed perimeter. If you can get there, you're safe. "
                "Key word: if. The highway is not clear. Drive fast. Don't stop "
                "for anything. Over and out.'"
            ),
            set_flags=json.dumps(["knows_about_checkpoint"]),
            is_root=0,
        )

        db.insert_dialogue_option(
            id="radio_opt_checkpoint",
            node_id="radio_root",
            text='"Ask about the checkpoint."',
            next_node_id="radio_checkpoint",
            required_flags=None,
            excluded_flags=json.dumps(["asked_about_checkpoint"]),
            required_items=None,
            set_flags=json.dumps(["asked_about_checkpoint"]),
            sort_order=0,
        )

        db.insert_dialogue_option(
            id="radio_checkpoint_leave",
            node_id="radio_checkpoint",
            text='"Copy that."',
            next_node_id=None,
            required_flags=None,
            excluded_flags=None,
            required_items=None,
            set_flags=None,
            sort_order=0,
        )

        # The zombie NPC has no dialogue tree -- it uses default_dialogue
        # only. Trying to "talk to zombie" will print:
        #   "The zombie groans -- a low, rattling sound..."

        # ==============================================================
        # 7. Puzzles (before locks, since locks FK to puzzles)
        # ==============================================================

        # Puzzle 1: Find the fire escape (examine window in kitchen)
        db.insert_puzzle(
            id="fire_escape_puzzle",
            name="The Fire Escape",
            description=(
                "Examine the kitchen window to discover the fire escape exit."
            ),
            room_id="kitchen",
            is_solved=0,
            solution_steps=json.dumps([
                "Go to the kitchen",
                "Examine the kitchen window",
            ]),
            hint_text=json.dumps([
                "Is there another way out of the apartment?",
                "That window in the kitchen looks like it leads somewhere.",
            ]),
            difficulty=1,
            score_value=5,
            is_optional=1,
        )

        # Puzzle 2: Start the escape truck (find keys + fuel + use them)
        db.insert_puzzle(
            id="escape_truck_puzzle",
            name="The Escape Truck",
            description=(
                "Find the truck keys (under gas station counter) and gas can, "
                "then use them on the pickup truck in the gas station lot to "
                "escape the city."
            ),
            room_id="gas_station_lot",
            is_solved=0,
            solution_steps=json.dumps([
                "Get bolt cutters from car trunk",
                "Cut the chain on the gas station door",
                "Find truck keys under the counter",
                "Take the gas can",
                "Use gas can on pickup truck",
                "Use truck keys on pickup truck",
            ]),
            hint_text=json.dumps([
                "You need to get inside the gas station first.",
                "The registration papers mention where the keys are.",
                "The truck needs fuel AND keys.",
            ]),
            difficulty=3,
            score_value=25,
            is_optional=0,
        )

        # Puzzle 3: Dealing with the zombie at the gas station
        db.insert_puzzle(
            id="zombie_encounter_puzzle",
            name="The Gas Station Zombie",
            description=(
                "Deal with the zombie at the gas station. Hit it with a "
                "weapon (bat, crowbar, knife) to clear the area."
            ),
            room_id="gas_station_lot",
            is_solved=0,
            solution_steps=json.dumps([
                "Find a weapon (baseball bat, crowbar, or kitchen knife)",
                "Attack the zombie at the gas station lot",
            ]),
            hint_text=json.dumps([
                "You should probably deal with that zombie before doing anything else here.",
                "Any weapon will work -- bat, crowbar, or knife.",
            ]),
            difficulty=2,
            score_value=10,
            is_optional=0,
        )

        # ==============================================================
        # 8. Locks (after puzzles, since locks FK to puzzles)
        # ==============================================================

        # Apartment door lock (key lock)
        db.insert_lock(
            id="apartment_door_lock",
            lock_type="key",
            target_exit_id="living_to_lobby",
            key_item_id="apartment_key",
            puzzle_id=None,
            combination=None,
            required_flags=None,
            locked_message=(
                "The door to the lobby is locked from inside. You need your "
                "apartment key to undo the deadbolt."
            ),
            unlock_message=(
                "The deadbolt clicks open. You pull the chair away from the "
                "door and it swings wide, revealing the dark stairwell."
            ),
            is_locked=1,
            consume_key=1,
        )

        # Gas station chain lock (requires bolt cutters -- state/flag lock)
        db.insert_lock(
            id="station_chain_lock",
            lock_type="state",
            target_exit_id="gas_lot_to_interior",
            key_item_id=None,
            puzzle_id=None,
            combination=None,
            required_flags=json.dumps(["chain_cut"]),
            locked_message=(
                "A heavy chain and padlock seal the gas station door. "
                "You'd need bolt cutters to get through this."
            ),
            unlock_message=(
                "The bolt cutters bite through the chain with a sharp snap. "
                "The chain clatters to the ground and the door swings open."
            ),
            is_locked=1,
            consume_key=0,
        )

        # ==============================================================
        # 9. Flags
        # ==============================================================

        flags = [
            # NPC interaction flags
            ("spoke_to_maria", "false",
             "Set when the player first talks to Maria."),
            ("knows_about_zombies", "false",
             "Set when Maria tells you about the zombies."),
            ("knows_about_station", "false",
             "Set when Maria tells you about the gas station."),
            ("heard_broadcast", "false",
             "Set when the player hears the radio broadcast."),
            ("knows_about_checkpoint", "false",
             "Set when the player asks the radio about the checkpoint."),
            # Dialogue tree tracking flags (excluded_flags hide used options)
            ("asked_about_hospital", "false",
             "Set when the player asks Maria about the hospital."),
            ("asked_about_station", "false",
             "Set when the player asks Maria about the gas station."),
            ("asked_about_building", "false",
             "Set when the player asks Maria about the building."),
            ("showed_maria_bolt_cutters", "false",
             "Set when the player shows Maria the bolt cutters."),
            ("showed_maria_registration", "false",
             "Set when the player shows Maria the registration papers."),
            ("asked_about_checkpoint", "false",
             "Set when the player asks the radio about the checkpoint."),
            # Exploration flags
            ("window_examined", "false",
             "Set when the player examines the kitchen window, revealing fire escape."),
            ("note_read", "false",
             "Set when the player reads the registration papers and learns about keys."),
            ("searched_counter", "false",
             "Set when the player searches behind the counter for truck keys."),
            # Progression flags
            ("apartment_unlocked", "false",
             "Set when the player unlocks the apartment door with the key."),
            ("chain_cut", "false",
             "Set when the player cuts the gas station chain with bolt cutters."),
            ("zombie_defeated", "false",
             "Set when the player defeats the gas station zombie."),
            ("truck_fueled", "false",
             "Set when the player puts gas in the pickup truck."),
            ("truck_started", "false",
             "Set when the player uses keys on the fueled truck."),
            ("escaped_city", "false",
             "WIN CONDITION: set when the player starts the truck and escapes."),
            # Container flags
            ("trunk_popped", "false",
             "Set when the player pulls the trunk release lever in the car."),
            ("glovebox_opened", "false",
             "Set when the player pries open the glovebox with the crowbar."),
            # Item usage
            ("used_bandages", "false",
             "Set when the player uses bandages to heal."),
            ("used_painkillers", "false",
             "Set when the player uses painkillers to heal."),
            # Zombie warning flags
            ("player_dead", "false",
             "LOSE CONDITION: set if HP drops to 0."),
            # Quest completion flags
            ("quest_main_complete", "false",
             "Set by engine when all main quest objectives are complete."),
            ("quest_survivor_complete", "false",
             "Set by engine when The Survivor's Story quest is complete."),
            ("quest_scavenger_complete", "false",
             "Set by engine when the Scavenger quest is complete."),
        ]
        for fid, fval, fdesc in flags:
            db.insert_flag(id=fid, value=fval, description=fdesc)

        # ==============================================================
        # 10. Commands
        # ==============================================================

        # --- APARTMENT: Unlock door with apartment key ---
        # REMOVED: use_apartment_key and unlock_apartment_door commands.
        # The engine's built-in key-on-lock handler (via _try_unlock and
        # _handle_use_on) handles "use apartment key on door", "unlock door",
        # and "open down" automatically using locks table data.

        # --- KITCHEN: Examine window to reveal fire escape ---
        db.insert_command(
            id="examine_window_reveal",
            verb="look",
            pattern="look at {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "kitchen"},
                {"type": "item_in_room", "item": "kitchen_window", "room": "_current"},
                {"type": "not_flag", "flag": "window_examined"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "window_examined"},
                {"type": "reveal_exit", "exit": "kitchen_to_fire_escape"},
                {"type": "solve_puzzle", "puzzle": "fire_escape_puzzle"},
                {"type": "add_score", "points": 5},
                {"type": "print", "message": "You wipe the grime from the window and peer through. A metal fire escape platform sits just outside, its railing coated with rust. The window latch is stiff but it turns. You could climb through to the fire escape."},
            ]),
            success_message="",
            failure_message="",
            context_room_id="kitchen",
            puzzle_id="fire_escape_puzzle",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The window is open. The fire escape platform is just outside -- you can climb through to the south.",
        )

        # REMOVED: examine_window_after — "already done" variant.
        # Now handled by done_message on examine_window_reveal.

        # --- CAR: Pull trunk release lever ---
        db.insert_command(
            id="pull_trunk_release",
            verb="pull",
            pattern="pull {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "abandoned_car"},
                {"type": "item_in_room", "item": "trunk_release_lever", "room": "_current"},
                {"type": "not_flag", "flag": "trunk_popped"},
            ]),
            effects=json.dumps([
                {"type": "open_container", "container": "car_trunk"},
                {"type": "set_flag", "flag": "trunk_popped"},
                {"type": "add_score", "points": 5},
                {"type": "print", "message": "You pull the lever. There's a muffled thunk from behind -- the trunk pops open. Something heavy shifts inside."},
            ]),
            success_message="",
            failure_message="",
            context_room_id="abandoned_car",
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
            done_message="The lever moves loosely. The trunk is already open.",
        )

        # REMOVED: pull_trunk_already — "already done" variant.
        # Now handled by done_message on pull_trunk_release.

        # --- CAR: Pry open glovebox with crowbar ---
        db.insert_command(
            id="pry_glovebox",
            verb="use",
            pattern="use {item} on {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "abandoned_car"},
                {"type": "has_item", "item": "crowbar"},
                {"type": "item_in_room", "item": "car_glovebox", "room": "_current"},
                {"type": "not_flag", "flag": "glovebox_opened"},
            ]),
            effects=json.dumps([
                {"type": "open_container", "container": "car_glovebox"},
                {"type": "set_flag", "flag": "glovebox_opened"},
                {"type": "add_score", "points": 5},
                {"type": "print", "message": "You jam the crowbar into the glovebox latch and twist. The cheap plastic cracks and the glovebox drops open, spilling papers and a small flashlight."},
            ]),
            success_message="",
            failure_message="You need something to pry this open with.",
            context_room_id="abandoned_car",
            puzzle_id=None,
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # REMOVED: pry_glovebox_alt — verb synonym of pry_glovebox.
        # The DSL pry_glovebox command handles "use crowbar on glovebox",
        # and the built-in key-on-container handles the fallback pattern.

        # REMOVED: read_registration — the engine handles "read" as examine
        # with read_description. The registration papers item now has a
        # read_description field.

        # --- GAS STATION: Cut the chain with bolt cutters ---
        db.insert_command(
            id="cut_chain",
            verb="use",
            pattern="use bolt cutters on chain",
            preconditions=json.dumps([
                {"type": "has_item", "item": "bolt_cutters"},
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "not_flag", "flag": "chain_cut"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "chain_cut"},
                {"type": "unlock", "lock": "station_chain_lock"},
                {"type": "add_score", "points": 10},
                {"type": "print", "message": "You clamp the bolt cutters around the chain and squeeze. The steel link snaps with a sharp crack that echoes down the empty street. The chain clatters to the ground. The gas station door swings open."},
            ]),
            success_message="",
            failure_message="You need bolt cutters to get through this chain.",
            context_room_id="gas_station_lot",
            puzzle_id="escape_truck_puzzle",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # REMOVED: cut_chain_alt — verb synonym of cut_chain.
        # Keep the canonical "use bolt cutters on chain" command.

        # --- GAS STATION: Search counter (spawn truck keys) ---
        db.insert_command(
            id="search_counter",
            verb="search",
            pattern="search {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "gas_station_interior"},
                {"type": "item_in_room", "item": "station_counter", "room": "_current"},
                {"type": "not_flag", "flag": "searched_counter"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "searched_counter"},
                {"type": "spawn_item", "item": "truck_keys", "location": "_current"},
                {"type": "add_score", "points": 5},
                {"type": "print", "message": "You reach under the counter and feel around. Your fingers close on a set of keys hanging from a hook. Ford truck keys on a greasy keyring. This is it -- the way out."},
            ]),
            success_message="",
            failure_message="",
            context_room_id="gas_station_interior",
            puzzle_id="escape_truck_puzzle",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # REMOVED: look_under_counter — verb synonym of search_counter.

        # --- GAS STATION: Use gas can on truck ---
        db.insert_command(
            id="fuel_truck",
            verb="use",
            pattern="use gas can on truck",
            preconditions=json.dumps([
                {"type": "has_item", "item": "gas_can"},
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "not_flag", "flag": "truck_fueled"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "gas_can"},
                {"type": "set_flag", "flag": "truck_fueled"},
                {"type": "add_score", "points": 5},
                {"type": "print", "message": "You unscrew the truck's gas cap and pour in the fuel. It's not much -- maybe half a gallon -- but you can hear it gurgling into the empty tank. Enough to get out of the city. Maybe."},
            ]),
            success_message="",
            failure_message="You need fuel to put in the truck.",
            context_room_id="gas_station_lot",
            puzzle_id="escape_truck_puzzle",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # REMOVED: fuel_truck_alt — verb synonym of fuel_truck.

        # --- GAS STATION: Use truck keys on truck (WIN!) ---
        db.insert_command(
            id="start_truck",
            verb="use",
            pattern="use truck keys on truck",
            preconditions=json.dumps([
                {"type": "has_item", "item": "truck_keys"},
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "has_flag", "flag": "truck_fueled"},
                {"type": "not_flag", "flag": "escaped_city"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "escaped_city"},
                {"type": "solve_puzzle", "puzzle": "escape_truck_puzzle"},
                {"type": "add_score", "points": 25},
                {"type": "print", "message": "You jam the key into the ignition and turn it. The engine coughs. Sputters. You pump the gas and try again. It catches -- a deep, rumbling roar that fills the empty parking lot. You throw it into gear. In the mirror, shapes are already stumbling out of the darkness. You don't look back. The highway stretches north under a pale dawn sky. You made it. You survived Dead City."},
            ]),
            success_message="",
            failure_message="The truck needs fuel before it can start.",
            context_room_id="gas_station_lot",
            puzzle_id="escape_truck_puzzle",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # Start truck without fuel
        db.insert_command(
            id="start_truck_no_fuel",
            verb="use",
            pattern="use truck keys on truck",
            preconditions=json.dumps([
                {"type": "has_item", "item": "truck_keys"},
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "not_flag", "flag": "truck_fueled"},
            ]),
            effects=json.dumps([
                {"type": "print", "message": "You turn the key. The starter cranks but the engine won't catch. The gas tank is bone dry. You need fuel."},
            ]),
            success_message="",
            failure_message="",
            context_room_id="gas_station_lot",
            puzzle_id=None,
            priority=5,
            is_enabled=1,
            one_shot=0,
            executed=0,
        )

        # REMOVED: start_truck_verb — verb synonym of start_truck.

        # --- ZOMBIE: Attack with weapon ---
        db.insert_command(
            id="attack_zombie_bat",
            verb="hit",
            pattern="hit {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "npc_in_room", "npc": "shambling_zombie", "room": "_current"},
                {"type": "has_item", "item": "baseball_bat"},
                {"type": "not_flag", "flag": "zombie_defeated"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "zombie_defeated"},
                {"type": "solve_puzzle", "puzzle": "zombie_encounter_puzzle"},
                {"type": "add_score", "points": 10},
                {"type": "print", "message": "You swing the bat hard. It connects with a sickening crack and the zombie staggers, then crumples to the asphalt. It twitches once and goes still. The parking lot is quiet again. Your hands are shaking."},
            ]),
            success_message="",
            failure_message="You need a weapon first.",
            context_room_id="gas_station_lot",
            puzzle_id="zombie_encounter_puzzle",
            priority=10,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # Attack with crowbar
        db.insert_command(
            id="attack_zombie_crowbar",
            verb="hit",
            pattern="hit {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "npc_in_room", "npc": "shambling_zombie", "room": "_current"},
                {"type": "has_item", "item": "crowbar"},
                {"type": "not_flag", "flag": "zombie_defeated"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "zombie_defeated"},
                {"type": "solve_puzzle", "puzzle": "zombie_encounter_puzzle"},
                {"type": "add_score", "points": 10},
                {"type": "print", "message": "You bring the crowbar down with everything you've got. The zombie drops like a puppet with its strings cut. It doesn't get back up. Silence settles over the parking lot."},
            ]),
            success_message="",
            failure_message="You need a weapon first.",
            context_room_id="gas_station_lot",
            puzzle_id="zombie_encounter_puzzle",
            priority=9,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # Attack with knife
        db.insert_command(
            id="attack_zombie_knife",
            verb="hit",
            pattern="hit {target}",
            preconditions=json.dumps([
                {"type": "in_room", "room": "gas_station_lot"},
                {"type": "npc_in_room", "npc": "shambling_zombie", "room": "_current"},
                {"type": "has_item", "item": "kitchen_knife"},
                {"type": "not_flag", "flag": "zombie_defeated"},
            ]),
            effects=json.dumps([
                {"type": "set_flag", "flag": "zombie_defeated"},
                {"type": "solve_puzzle", "puzzle": "zombie_encounter_puzzle"},
                {"type": "add_score", "points": 10},
                {"type": "change_health", "amount": -10},
                {"type": "print", "message": "You rush in with the knife. It grabs at you -- cold fingers scraping your arm -- but you drive the blade home. The zombie collapses. You stumble back, bleeding from a shallow gash on your forearm. It got close. Too close."},
            ]),
            success_message="",
            failure_message="You need a weapon first.",
            context_room_id="gas_station_lot",
            puzzle_id="zombie_encounter_puzzle",
            priority=8,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # REMOVED: attack_zombie_verb — verb synonym of attack_zombie_* commands.

        # --- HEALING: Use bandages ---
        db.insert_command(
            id="use_bandages",
            verb="use",
            pattern="use bandages",
            preconditions=json.dumps([
                {"type": "has_item", "item": "bandages"},
                {"type": "not_flag", "flag": "used_bandages"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "bandages"},
                {"type": "set_flag", "flag": "used_bandages"},
                {"type": "change_health", "amount": 25},
                {"type": "print", "message": "You unwrap the gauze and bandage your wounds. The clean wrapping feels good against your skin. You feel a little better."},
            ]),
            success_message="",
            failure_message="",
            context_room_id=None,
            puzzle_id=None,
            priority=5,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # --- HEALING: Use painkillers ---
        db.insert_command(
            id="use_painkillers",
            verb="use",
            pattern="use painkillers",
            preconditions=json.dumps([
                {"type": "has_item", "item": "painkillers"},
                {"type": "not_flag", "flag": "used_painkillers"},
            ]),
            effects=json.dumps([
                {"type": "remove_item", "item": "painkillers"},
                {"type": "set_flag", "flag": "used_painkillers"},
                {"type": "change_health", "amount": 15},
                {"type": "print", "message": "You dry-swallow three ibuprofen tablets. The pain dulls to a manageable ache after a few minutes."},
            ]),
            success_message="",
            failure_message="",
            context_room_id=None,
            puzzle_id=None,
            priority=5,
            is_enabled=1,
            one_shot=1,
            executed=0,
        )

        # REMOVED: read_bloody_note, read_torn_map — the engine handles
        # "read" as examine with read_description. These items now have
        # read_description fields set on the item rows.

        # REMOVED: ask_maria_zombies, ask_maria_station — the dialogue
        # system already handles "ask {npc} about {topic}" as a built-in
        # verb with flag-gated dialogue entries. These were duplicates.

        # ==============================================================
        # 11. Quests
        # ==============================================================

        # --- Main Quest: Escape Dead City ---
        db.insert_quest(
            id="escape_dead_city",
            name="Escape Dead City",
            description=(
                "The city has fallen to a zombie outbreak. Find a way to escape "
                "before nightfall. The evacuation point is the Mercer Street Gas "
                "Station -- find a vehicle and get out."
            ),
            quest_type="main",
            status="undiscovered",
            discovery_flag=None,
            completion_flag="quest_main_complete",
            score_value=0,
            sort_order=0,
        )

        db.insert_quest_objective(
            id="main_unlock_apartment",
            quest_id="escape_dead_city",
            description="Get out of the apartment",
            completion_flag="apartment_unlocked",
            order_index=0,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="main_cut_chain",
            quest_id="escape_dead_city",
            description="Break into the gas station",
            completion_flag="chain_cut",
            order_index=1,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="main_fuel_truck",
            quest_id="escape_dead_city",
            description="Fuel the escape truck",
            completion_flag="truck_fueled",
            order_index=2,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="main_escape",
            quest_id="escape_dead_city",
            description="Start the truck and escape the city",
            completion_flag="escaped_city",
            order_index=3,
            is_optional=0,
            bonus_score=0,
        )

        # --- Side Quest: The Survivor's Story ---
        db.insert_quest(
            id="survivor_story",
            name="The Survivor's Story",
            description=(
                "A woman named Maria is hiding in the building lobby. She might "
                "know something about what happened and how to get out."
            ),
            quest_type="side",
            status="undiscovered",
            discovery_flag="spoke_to_maria",
            completion_flag="quest_survivor_complete",
            score_value=10,
            sort_order=1,
        )

        db.insert_quest_objective(
            id="survivor_talk",
            quest_id="survivor_story",
            description="Talk to Maria",
            completion_flag="spoke_to_maria",
            order_index=0,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="survivor_zombies",
            quest_id="survivor_story",
            description="Learn about the infected",
            completion_flag="knows_about_zombies",
            order_index=1,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="survivor_station",
            quest_id="survivor_story",
            description="Learn about the gas station",
            completion_flag="knows_about_station",
            order_index=2,
            is_optional=0,
            bonus_score=0,
        )

        # --- Side Quest: Scavenger ---
        db.insert_quest(
            id="scavenger",
            name="Scavenger",
            description=(
                "The abandoned car on the street might have useful supplies. "
                "Search it thoroughly."
            ),
            quest_type="side",
            status="undiscovered",
            discovery_flag="trunk_popped",
            completion_flag="quest_scavenger_complete",
            score_value=10,
            sort_order=2,
        )

        db.insert_quest_objective(
            id="scavenger_glovebox",
            quest_id="scavenger",
            description="Search the car glovebox",
            completion_flag="glovebox_opened",
            order_index=0,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="scavenger_trunk",
            quest_id="scavenger",
            description="Pop the trunk",
            completion_flag="trunk_popped",
            order_index=1,
            is_optional=0,
            bonus_score=0,
        )
        db.insert_quest_objective(
            id="scavenger_registration",
            quest_id="scavenger",
            description="Read the registration papers",
            completion_flag="note_read",
            order_index=2,
            is_optional=0,
            bonus_score=0,
        )

        # ==============================================================
        # 12. Initialize player state
        # ==============================================================
        db.init_player(start_room_id="bedroom", hp=100, max_hp=100)

    return output


if __name__ == "__main__":
    path = build_game()
    print(f"Test game created at {path}")
