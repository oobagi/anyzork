"""Combat system mixin for GameEngine.

Handles attack resolution and deterministic combat rounds.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress

logger = logging.getLogger(__name__)


class CombatMixin:
    """Combat handling methods extracted from GameEngine."""

    def _handle_attack(self, target_name: str, current_room_id: str) -> None:
        """Handle ``attack <target>`` with deterministic combat.

        If the NPC has combat stats (hp, damage), the engine runs a full
        combat round: player deals weapon damage (minus NPC defense, min 1),
        weakness doubles damage, NPC retaliates if still alive.

        Falls back to the interaction matrix and trigger system for NPCs
        without combat stats.
        """
        from anyzork.engine.game import STYLE_SYSTEM

        db = self.db

        # Find the target NPC.
        npc = db.find_npc_by_name(target_name, current_room_id)
        if npc is None:
            self.console.print("There's nothing to attack here.", style=STYLE_SYSTEM)
            return

        # Check if the player is wielding a weapon (first weapon in inventory).
        inventory = db.get_inventory()
        weapon = None
        for item in inventory:
            raw_tags = item.get("item_tags")
            if raw_tags:
                with suppress(json.JSONDecodeError, TypeError):
                    tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
                    if any(t in ("weapon", "firearm", "melee", "blade", "blunt") for t in tags):
                        weapon = item
                        break

        if weapon is None:
            self.console.print(
                "You have no weapon to attack with.", style=STYLE_SYSTEM
            )
            # Still emit the event for bare-handed triggers.
            self._emit_event(
                "on_attacked",
                npc_id=npc["id"],
                item_id="",
                room_id=current_room_id,
            )
            return

        # --- Stat-based combat ---
        # If the NPC has hp and the weapon has damage, use deterministic combat.
        npc_hp = npc.get("hp")
        weapon_damage = weapon.get("damage")
        if npc_hp is not None and npc_hp > 0 and weapon_damage is not None:
            self._combat_round(npc, weapon, current_room_id)
            return

        # --- Fallback: interaction matrix / trigger system ---
        handled = self._handle_interaction(
            weapon["name"], target_name, current_room_id
        )
        if not handled:
            self.console.print(
                f"You attack {npc['name']} with the {weapon['name']}.",
            )
            # Emit on_attacked event for trigger-based reactions.
            self._emit_event(
                "on_attacked",
                npc_id=npc["id"],
                item_id=weapon["id"],
                room_id=current_room_id,
            )

    def _combat_round(
        self, npc: dict, weapon: dict, current_room_id: str
    ) -> None:
        """Execute one deterministic combat round.

        1. Player deals damage = weapon.damage - npc.defense (min 1).
        2. If weapon tags match NPC weakness, double the damage.
        3. If NPC HP <= 0, NPC dies and drops its loot.
        4. Otherwise NPC retaliates: npc.damage - 0 (no player defense yet).
        5. If player HP <= 0, game over is handled by check_end_conditions.
        """
        from anyzork.engine.game import STYLE_SUCCESS, STYLE_SYSTEM

        db = self.db
        player = db.get_player()
        if player is None:
            return

        # -- Player attack phase --
        base_damage = int(weapon.get("damage") or 0)
        npc_defense = int(npc.get("defense") or 0)
        raw_damage = max(1, base_damage - npc_defense)

        # Weakness check: if weapon tags contain the NPC's weakness, double.
        weakness = npc.get("weakness")
        is_weak = False
        if weakness:
            raw_tags = weapon.get("item_tags")
            if raw_tags:
                with suppress(json.JSONDecodeError, TypeError):
                    tags = (
                        json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
                    )
                    if weakness in tags:
                        is_weak = True
                        raw_damage *= 2

        # Apply damage to NPC.
        updated_npc = db.damage_npc(npc["id"], raw_damage)

        if is_weak:
            self.console.print(
                f"You strike {npc['name']} with the {weapon['name']}. "
                f"It's super effective! ({raw_damage} damage)"
            )
        else:
            self.console.print(
                f"You strike {npc['name']} with the {weapon['name']}. "
                f"({raw_damage} damage)"
            )

        # Emit on_attacked event.
        self._emit_event(
            "on_attacked",
            npc_id=npc["id"],
            item_id=weapon["id"],
            room_id=current_room_id,
        )

        # Check if NPC is dead.
        if updated_npc is None or not updated_npc.get("is_alive", True):
            self.console.print(
                f"{npc['name']} is defeated!",
                style=STYLE_SUCCESS,
            )
            # Drop loot into the body container.
            drop_item_id = npc.get("drop_item")
            if drop_item_id:
                body_id = f"{npc['id']}_body"
                drop_item = db.get_item(drop_item_id)
                if drop_item:
                    db.move_item_to_container(drop_item_id, body_id)
                    self.console.print(
                        f"{npc['name']} dropped {drop_item['name']}.",
                    )
            return

        # -- NPC retaliation phase --
        npc_damage = int(updated_npc.get("damage") or 0)
        if npc_damage > 0:
            actual_damage = max(1, npc_damage)
            new_hp = max(0, player["hp"] - actual_damage)
            db.update_player(hp=new_hp)
            self.console.print(
                f"{npc['name']} attacks you! ({actual_damage} damage, "
                f"HP: {new_hp}/{player['max_hp']})"
            )
            remaining_npc_hp = updated_npc.get("hp", 0) or 0
            self.console.print(
                f"{npc['name']}: {remaining_npc_hp} HP remaining.",
                style=STYLE_SYSTEM,
            )
