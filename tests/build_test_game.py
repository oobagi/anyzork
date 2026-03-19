"""Build the single AnyZork human-testing world.

This fixture is intentionally compact, but it exercises the systems the
current product actually relies on for manual and automated testing:
deterministic commands, dialogue, triggers, quests, key/state locks,
interaction responses, dark rooms, and toggleable / quantity-backed items.
"""

from __future__ import annotations

import json
from pathlib import Path

from anyzork.db.schema import GameDB


def build_test_game() -> Path:
    """Build and return the path to the primary human-test ``.zork`` file."""
    path = Path(__file__).parent / "test_game.zork"
    path.unlink(missing_ok=True)
    Path(f"{path}-wal").unlink(missing_ok=True)
    Path(f"{path}-shm").unlink(missing_ok=True)

    db = GameDB(path)
    db.initialize(
        game_name="The Lantern Archive",
        author="tests",
        prompt=(
            "A compact archive-and-observatory fixture that exercises current "
            "AnyZork runtime systems."
        ),
        seed="human-test-world-v1",
        intro_text=(
            "The Lantern Archive has gone dark. Restore power, secure the "
            "curator's badge, and reopen the observatory."
        ),
        win_text=(
            "The archive hums back to life and the observatory iris slides "
            "open above you.\n\nFinal score: {score} / {max_score}"
        ),
        lose_text=None,
        win_conditions=json.dumps(["main_restore_complete"]),
        lose_conditions=None,
        max_score=25,
        region_count=1,
        room_count=5,
    )

    db.insert_room(
        id="entrance_hall",
        name="Entrance Hall",
        description=(
            "A domed archive foyer of brass railings, catalog drawers, and a "
            "silent reception desk. A sealed workshop sits to the east, black "
            "stacks loom to the north, and the observatory lift waits above."
        ),
        short_description=(
            "The archive foyer. Workshop east, stacks north, observatory above."
        ),
        first_visit_text=(
            "Dust hangs in the still air. Somewhere overhead, the observatory "
            "mechanism waits for enough power to move again."
        ),
        region="lantern_archive",
        is_dark=0,
        is_start=1,
    )
    db.insert_room(
        id="workshop",
        name="Lens Workshop",
        description=(
            "A narrow bench room packed with optical tools, trays of screws, "
            "and half-disassembled brass housings."
        ),
        short_description="The lens workshop smells of polish and machine oil.",
        first_visit_text=None,
        region="lantern_archive",
        is_dark=0,
        is_start=0,
    )
    db.insert_room(
        id="black_stacks",
        name="Black Stacks",
        description=(
            "Towering shelves crowd around a mural-scored wall. In the lantern "
            "glow, a fallen repair coil glints beneath the dust."
        ),
        short_description="The stacks are close, dark, and cluttered with murals.",
        first_visit_text=(
            "The temperature drops as you enter. Without your own light, the "
            "stacks are just a mouth of darkness."
        ),
        region="lantern_archive",
        is_dark=1,
        is_start=0,
    )
    db.insert_room(
        id="generator_room",
        name="Generator Room",
        description=(
            "A cramped utility chamber wrapped around an inert emergency "
            "generator. A maintenance socket on the housing waits for a new coil."
        ),
        short_description="The generator room vibrates with dormant potential.",
        first_visit_text=None,
        region="lantern_archive",
        is_dark=0,
        is_start=0,
    )
    db.insert_room(
        id="observatory",
        name="Observatory",
        description=(
            "A circular chamber under a ribbed glass dome. Brass tracking arms "
            "and calibration rails ring a central telescope mount."
        ),
        short_description="The observatory overlooks the archive below.",
        first_visit_text=(
            "With a deep mechanical groan, the observatory platform accepts "
            "your weight for the first time in years."
        ),
        region="lantern_archive",
        is_dark=0,
        is_start=0,
    )

    db.insert_exit(
        id="entrance_to_workshop",
        from_room_id="entrance_hall",
        to_room_id="workshop",
        direction="east",
        description="A brass-bound workshop door.",
        is_locked=1,
        is_hidden=0,
    )
    db.insert_exit(
        id="workshop_to_entrance",
        from_room_id="workshop",
        to_room_id="entrance_hall",
        direction="west",
        description="The workshop opens back into the foyer.",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="entrance_to_stacks",
        from_room_id="entrance_hall",
        to_room_id="black_stacks",
        direction="north",
        description="A shadowed aisle into the stacks.",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="stacks_to_entrance",
        from_room_id="black_stacks",
        to_room_id="entrance_hall",
        direction="south",
        description="The foyer lights show faintly beyond the stacks.",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="stacks_to_generator",
        from_room_id="black_stacks",
        to_room_id="generator_room",
        direction="east",
        description="A maintenance hatch stands ajar.",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="generator_to_stacks",
        from_room_id="generator_room",
        to_room_id="black_stacks",
        direction="west",
        description="The maintenance hatch leads back to the stacks.",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="entrance_to_observatory",
        from_room_id="entrance_hall",
        to_room_id="observatory",
        direction="up",
        description="A circular lift gate blocks the observatory ascent.",
        is_locked=1,
        is_hidden=0,
    )
    db.insert_exit(
        id="observatory_to_entrance",
        from_room_id="observatory",
        to_room_id="entrance_hall",
        direction="down",
        description="The lift returns to the entrance hall.",
        is_locked=0,
        is_hidden=0,
    )

    db.insert_item(
        id="brass_key",
        name="brass key",
        description="A slim brass key tagged WORKSHOP.",
        examine_description="A slim brass key with a black enamel tag reading WORKSHOP.",
        room_id="entrance_hall",
        category="key",
        room_description="A brass key hangs from a labeled hook behind the desk.",
        home_room_id="entrance_hall",
        drop_description="A brass key lies here.",
    )
    db.insert_item(
        id="battery_pack",
        name="battery pack",
        description="A sealed emergency battery pack.",
        examine_description="A sealed battery pack with enough charge for field equipment.",
        room_id="entrance_hall",
        category="power",
        room_description="A spare battery pack rests beside the reception ledger.",
        home_room_id="entrance_hall",
        drop_description="A battery pack sits here.",
        quantity=4,
        max_quantity=4,
        quantity_unit="charges",
    )
    db.insert_item(
        id="field_lantern",
        name="field lantern",
        description="A hand lantern with a guarded switch and frosted lens.",
        examine_description="A maintenance lantern built for tight archive corridors.",
        room_id="entrance_hall",
        category="tool",
        room_description="A field lantern hangs from a peg by the door.",
        home_room_id="entrance_hall",
        drop_description="A field lantern rests here.",
        is_toggleable=1,
        toggle_state="off",
        toggle_on_message="The lantern blooms to life with a warm white glow.",
        toggle_off_message="The lantern clicks dark.",
        item_tags=json.dumps(["light_source", "tool"]),
        requires_item_id="battery_pack",
        requires_message="The lantern stays dark. The battery pack is spent.",
    )
    db.insert_item(
        id="chalk_stick",
        name="chalk stick",
        description="A thumb-thick piece of drafting chalk.",
        examine_description="Soft white chalk used to mark archive shelving and star maps.",
        room_id="entrance_hall",
        category="tool",
        room_description="A chalk stick lies beside a stack of route cards.",
        home_room_id="entrance_hall",
        drop_description="A chalk stick waits here.",
        item_tags=json.dumps(["marking_tool"]),
        quantity=3,
        max_quantity=3,
        quantity_unit="marks",
    )
    db.insert_item(
        id="crate_key",
        name="case key",
        description="A stamped brass key for the workshop archive case.",
        examine_description="A compact brass key tagged CASE.",
        room_id=None,
        category="key",
        home_room_id=None,
        drop_description="A small brass key glints here.",
        is_visible=0,
    )
    db.insert_item(
        id="archive_case",
        name="archive case",
        description="A hard-sided maintenance case banded in brass.",
        examine_description=(
            "A compact archive case with a brass latch and a keyed lock. "
            "Its foam insert is shaped for field gear."
        ),
        room_id="workshop",
        category="container",
        room_description="A locked archive case sits on the workshop bench.",
        home_room_id="workshop",
        drop_description="An archive case rests here.",
        is_container=1,
        is_open=0,
        has_lid=1,
        is_locked=1,
        is_takeable=0,
        key_item_id="crate_key",
        consume_key=0,
        unlock_message="The case key clicks and the archive case springs open.",
        lock_message="The archive case is locked tight.",
        open_message="You lift the archive case lid.",
    )
    db.insert_item(
        id="tool_satchel",
        name="tool satchel",
        description="A leather satchel with clips for a single repair coil.",
        examine_description="A worn maintenance satchel lined with custom metal clips.",
        room_id=None,
        container_id="archive_case",
        category="container",
        room_description="A tool satchel lies nested inside the archive case.",
        home_room_id="workshop",
        drop_description="A tool satchel lies open here.",
        is_container=1,
        is_open=1,
        has_lid=0,
        accepts_items=json.dumps(["repair_coil"]),
        reject_message="The satchel only has clips for the repair coil.",
    )
    db.insert_item(
        id="repair_coil",
        name="repair coil",
        description="A heavy induction coil wrapped in lacquered copper.",
        examine_description="A replacement generator coil, dusty but intact.",
        room_id=None,
        container_id="tool_satchel",
        category="component",
        room_description="A repair coil is clipped into the satchel's inner frame.",
        home_room_id="workshop",
        drop_description="A repair coil has been set down here.",
    )
    db.insert_item(
        id="constellation_mural",
        name="constellation mural",
        description="A wall-sized star chart worked into the archive plaster.",
        examine_description="The mural maps shifting constellations in layered rings.",
        room_id="black_stacks",
        category="scenery",
        room_description="A cracked constellation mural spans the northern wall.",
        home_room_id="black_stacks",
        is_takeable=0,
    )
    db.insert_item(
        id="archive_badge",
        name="archive badge",
        description="A brass badge engraved with observatory access glyphs.",
        examine_description=(
            "The curator's badge is warm from a desk drawer and stamped "
            "OBSERVATORY."
        ),
        room_id=None,
        category="credential",
        home_room_id=None,
        drop_description="An archive badge glints here.",
        is_visible=0,
    )
    db.insert_item(
        id="focusing_lens",
        name="focusing lens",
        description="A polished lens ground for the observatory's guide scope.",
        examine_description="A crystal-clear focusing lens nested in a padded brass ring.",
        room_id="workshop",
        category="component",
        room_description="A focusing lens rests in a velvet tray on the bench.",
        home_room_id="workshop",
        drop_description="A focusing lens has been set here.",
    )
    db.insert_item(
        id="generator_socket",
        name="generator socket",
        description="A circular socket on the side of the backup generator.",
        examine_description="The socket is empty and sized for a repair coil.",
        room_id="generator_room",
        category="machinery",
        room_description="An empty generator socket gapes from the housing.",
        home_room_id="generator_room",
        is_takeable=0,
    )

    db.insert_npc(
        id="curator_rowan",
        name="Curator Rowan",
        description="A weary curator in rolled shirtsleeves watches the dead machinery.",
        examine_description=(
            "Rowan carries the clipped focus of someone holding an entire "
            "archive together alone."
        ),
        room_id="entrance_hall",
        default_dialogue=(
            "Rowan glances up from a ledger. 'If you can restore the power, "
            "we can reopen the dome.'"
        ),
        category="character",
    )

    db.insert_dialogue_node(
        id="rowan_root",
        npc_id="curator_rowan",
        content=(
            "\"The observatory needs two things,\" Rowan says. \"Power, and my "
            "badge in the lift registry. Bring the place back online and I'll "
            "authorize your ascent.\""
        ),
        set_flags=json.dumps(["met_rowan"]),
        is_root=1,
    )
    db.insert_dialogue_node(
        id="rowan_badge_node",
        npc_id="curator_rowan",
        content=(
            "\"Fair enough,\" Rowan says, opening a drawer. \"Take the archive "
            "badge. If the generator wakes up, the lift will recognize it.\""
        ),
        set_flags=json.dumps(["badge_received"]),
        is_root=0,
    )
    db.insert_dialogue_node(
        id="rowan_mural_node",
        npc_id="curator_rowan",
        content=(
            "\"The chalked mural tracks service constellations,\" Rowan says. "
            "\"Mark the right arc and you'll see how the stacks were meant to "
            "be navigated.\""
        ),
        set_flags=None,
        is_root=0,
    )

    db.insert_dialogue_option(
        id="rowan_opt_badge",
        node_id="rowan_root",
        text="\"I need observatory access.\"",
        next_node_id="rowan_badge_node",
        required_flags=None,
        excluded_flags=json.dumps(["badge_received"]),
        required_items=None,
        set_flags=None,
        sort_order=1,
    )
    db.insert_dialogue_option(
        id="rowan_opt_mural",
        node_id="rowan_root",
        text="\"What does the mural mean?\"",
        next_node_id="rowan_mural_node",
        required_flags=json.dumps(["mural_revealed"]),
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=2,
    )
    db.insert_dialogue_option(
        id="rowan_opt_leave",
        node_id="rowan_root",
        text="\"That's all for now.\"",
        next_node_id=None,
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=3,
    )
    db.insert_dialogue_option(
        id="rowan_badge_back",
        node_id="rowan_badge_node",
        text="\"I'll get the archive running.\"",
        next_node_id=None,
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )
    db.insert_dialogue_option(
        id="rowan_mural_back",
        node_id="rowan_mural_node",
        text="\"Understood.\"",
        next_node_id=None,
        required_flags=None,
        excluded_flags=None,
        required_items=None,
        set_flags=None,
        sort_order=1,
    )

    db.insert_lock(
        id="workshop_lock",
        lock_type="key",
        target_exit_id="entrance_to_workshop",
        key_item_id="brass_key",
        puzzle_id=None,
        combination=None,
        required_flags=None,
        locked_message="The workshop door is locked tight.",
        unlock_message="The brass key turns and the workshop door swings open.",
        is_locked=1,
        consume_key=0,
    )
    db.insert_lock(
        id="observatory_lock",
        lock_type="state",
        target_exit_id="entrance_to_observatory",
        key_item_id=None,
        puzzle_id=None,
        combination=None,
        required_flags=json.dumps(["power_restored", "badge_received"]),
        locked_message=(
            "The lift gate remains sealed. A brass plate reads: AUTHORIZED "
            "BADGE AND EMERGENCY POWER REQUIRED."
        ),
        unlock_message="The lift gate unlatches with a clean mechanical chime.",
        is_locked=1,
        consume_key=0,
    )

    db.insert_command(
        id="install_repair_coil",
        verb="install",
        pattern="install repair coil",
        preconditions=json.dumps(
            [
                {"type": "has_item", "item": "repair_coil"},
                {"type": "in_room", "room": "generator_room"},
                {"type": "not_flag", "flag": "power_restored"},
            ]
        ),
        effects=json.dumps(
            [
                {"type": "remove_item", "item": "repair_coil"},
                {"type": "set_flag", "flag": "power_restored"},
                {
                    "type": "print",
                    "message": (
                        "You seat the repair coil into the generator socket. "
                        "A rising hum answers through the floor."
                    ),
                },
            ]
        ),
        success_message="",
        failure_message="You need the repair coil and the generator room to do that.",
        context_room_ids=json.dumps(["generator_room"]),
        priority=10,
        one_shot=1,
        done_message="The generator is already running.",
    )
    db.insert_command(
        id="study_mural",
        verb="study",
        pattern="study mural",
        preconditions=json.dumps(
            [
                {"type": "in_room", "room": "black_stacks"},
                {"type": "has_flag", "flag": "mural_revealed"},
                {"type": "not_flag", "flag": "mural_notes_taken"},
            ]
        ),
        effects=json.dumps(
            [
                {"type": "set_flag", "flag": "mural_notes_taken"},
                {
                    "type": "print",
                    "message": (
                        "Following the chalk marks, you copy the mural's "
                        "hidden maintenance route into your notebook."
                    ),
                },
            ]
        ),
        success_message="",
        failure_message="You need a clearer view of the mural before you can study it.",
        context_room_ids=json.dumps(["black_stacks"]),
        priority=10,
        one_shot=1,
        done_message="You've already taken notes from the mural.",
    )
    db.insert_command(
        id="calibrate_lens",
        verb="calibrate",
        pattern="calibrate lens",
        preconditions=json.dumps(
            [
                {"type": "has_item", "item": "focusing_lens"},
                {"type": "in_room", "room": "observatory"},
                {"type": "has_flag", "flag": "observatory_open"},
                {"type": "not_flag", "flag": "lens_calibrated"},
            ]
        ),
        effects=json.dumps(
            [
                {"type": "set_flag", "flag": "lens_calibrated"},
                {
                    "type": "print",
                    "message": (
                        "You mount the focusing lens and dial the guide scope "
                        "into alignment."
                    ),
                },
            ]
        ),
        success_message="",
        failure_message="You need the focusing lens and the observatory to calibrate it.",
        context_room_ids=json.dumps(["observatory"]),
        priority=10,
        one_shot=1,
        done_message="The guide scope is already calibrated.",
    )

    db.insert_quest(
        id="restore_archive",
        name="Restore the Lantern Archive",
        description=(
            "Recover observatory access, restore the generator, and reopen "
            "the observatory lift."
        ),
        quest_type="main",
        status="undiscovered",
        discovery_flag=None,
        completion_flag="main_restore_complete",
        score_value=15,
        sort_order=1,
    )
    db.insert_quest_objective(
        id="obj_get_badge",
        quest_id="restore_archive",
        description="Secure Curator Rowan's archive badge.",
        completion_flag="badge_received",
        order_index=1,
        is_optional=0,
        bonus_score=0,
    )
    db.insert_quest_objective(
        id="obj_restore_power",
        quest_id="restore_archive",
        description="Install the repair coil and restore emergency power.",
        completion_flag="power_restored",
        order_index=2,
        is_optional=0,
        bonus_score=0,
    )
    db.insert_quest_objective(
        id="obj_open_observatory",
        quest_id="restore_archive",
        description="Reopen the observatory lift.",
        completion_flag="observatory_open",
        order_index=3,
        is_optional=0,
        bonus_score=0,
    )

    db.insert_quest(
        id="annotate_mural",
        name="Annotate the Mural",
        description="Reveal the service mural in the stacks and take notes from it.",
        quest_type="side",
        status="undiscovered",
        discovery_flag="mural_revealed",
        completion_flag="quest_mural_complete",
        score_value=5,
        sort_order=2,
    )
    db.insert_quest_objective(
        id="obj_note_mural",
        quest_id="annotate_mural",
        description="Study the revealed mural and record its route.",
        completion_flag="mural_notes_taken",
        order_index=1,
        is_optional=0,
        bonus_score=0,
    )

    db.insert_quest(
        id="calibrate_archive_lens",
        name="Calibrate the Archive Lens",
        description="Recover the workshop lens and fit it into the observatory guide scope.",
        quest_type="side",
        status="undiscovered",
        discovery_flag="lens_found",
        completion_flag="quest_lens_complete",
        score_value=5,
        sort_order=3,
    )
    db.insert_quest_objective(
        id="obj_calibrate_lens",
        quest_id="calibrate_archive_lens",
        description="Calibrate the focusing lens in the observatory.",
        completion_flag="lens_calibrated",
        order_index=1,
        is_optional=0,
        bonus_score=0,
    )

    for flag_id, description in (
        ("met_rowan", "The player has spoken with Curator Rowan."),
        ("badge_received", "Rowan has authorized observatory access."),
        ("badge_given", "The archive badge has been spawned."),
        ("power_restored", "Emergency power has been restored."),
        ("observatory_open", "The observatory lift has been unlocked."),
        ("mural_revealed", "The service mural has been marked and revealed."),
        ("mural_notes_taken", "The player has studied the revealed mural."),
        ("lens_found", "The focusing lens has been recovered."),
        ("lens_calibrated", "The focusing lens has been calibrated."),
        ("main_restore_complete", "The main restoration quest is complete."),
        ("quest_mural_complete", "The mural side quest is complete."),
        ("quest_lens_complete", "The lens side quest is complete."),
    ):
        db.insert_flag(id=flag_id, value="false", description=description)

    db.insert_interaction_response(
        id="marking_tool_scenery",
        item_tag="marking_tool",
        target_category="scenery",
        response=(
            "You drag the {item} across the {target}. A hidden service path "
            "emerges from the dust."
        ),
        consumes=1,
        score_change=0,
        flag_to_set="mural_revealed",
    )
    db.insert_interaction_response(
        id="light_source_default",
        item_tag="light_source",
        target_category="*",
        response="You sweep the {item} across the {target}, chasing out the shadows.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
    )
    db.insert_interaction_response(
        id="global_default",
        item_tag="*",
        target_category="*",
        response="Nothing interesting happens.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
    )

    db.insert_trigger(
        id="trigger_issue_badge",
        event_type="dialogue_node",
        event_data=json.dumps({"node_id": "rowan_badge_node"}),
        preconditions=json.dumps([{"type": "not_flag", "flag": "badge_given"}]),
        effects=json.dumps(
            [
                {"type": "spawn_item", "item": "archive_badge", "location": "_inventory"},
                {"type": "spawn_item", "item": "crate_key", "location": "_inventory"},
                {"type": "set_flag", "flag": "badge_given"},
            ]
        ),
        message="Rowan slides over the archive badge and a small case key.",
        priority=20,
        one_shot=1,
    )
    db.insert_trigger(
        id="trigger_unlock_observatory_on_badge",
        event_type="flag_set",
        event_data=json.dumps({"flag": "badge_received"}),
        preconditions=json.dumps(
            [
                {"type": "has_flag", "flag": "badge_received"},
                {"type": "has_flag", "flag": "power_restored"},
            ]
        ),
        effects=json.dumps(
            [
                {"type": "unlock", "lock": "observatory_lock"},
                {"type": "set_flag", "flag": "observatory_open"},
            ]
        ),
        message="Somewhere above, the observatory lift unlocks.",
        priority=30,
        one_shot=1,
    )
    db.insert_trigger(
        id="trigger_unlock_observatory_on_power",
        event_type="flag_set",
        event_data=json.dumps({"flag": "power_restored"}),
        preconditions=json.dumps(
            [
                {"type": "has_flag", "flag": "badge_received"},
                {"type": "has_flag", "flag": "power_restored"},
            ]
        ),
        effects=json.dumps(
            [
                {"type": "unlock", "lock": "observatory_lock"},
                {"type": "set_flag", "flag": "observatory_open"},
            ]
        ),
        message="Relays clack overhead as the observatory lift unlocks.",
        priority=30,
        one_shot=1,
    )
    db.insert_trigger(
        id="trigger_discover_lens_quest",
        event_type="item_taken",
        event_data=json.dumps({"item_id": "focusing_lens"}),
        preconditions=json.dumps([{"type": "not_flag", "flag": "lens_found"}]),
        effects=json.dumps([{"type": "set_flag", "flag": "lens_found"}]),
        message=None,
        priority=10,
        one_shot=1,
    )

    db.init_player(start_room_id="entrance_hall", hp=100, max_hp=100)
    db.close()
    return path


if __name__ == "__main__":
    built = build_test_game()
    print(f"Test game built: {built}")
