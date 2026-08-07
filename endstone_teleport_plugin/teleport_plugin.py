"""
Teleport Plugin for Endstone
Provides a GUI-based teleport system with admin management and multiple tag support.
"""

from endstone.plugin import Plugin
from endstone.command import Command, CommandSender
from endstone.event import event_handler, PlayerInteractActorEvent
from endstone.form import ActionForm, ModalForm, TextInput, Dropdown
from endstone.scoreboard import Criteria
from endstone import Player, ColorFormat
import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class TeleportPlugin(Plugin):
    api_version = "0.11"

    # Define commands that this plugin provides
    commands = {
        "tptag": {
            "description": "Manage teleport entity tags",
            "usages": [
                "/tptag list",
                "/tptag add <tag: str>",
                "/tptag remove <tag: str>"
            ],
            "permissions": ["teleport.admin"]
        },
        "tpreload": {
            "description": "Reload teleport configuration from file",
            "usages": ["/tpreload"],
            "permissions": ["teleport.admin"]
        }
    }

    # Define permissions for the commands
    permissions = {
        "teleport.admin": {
            "description": "Allow users to manage teleport tags and locations.",
            "default": "op"  # Only operators can use this by default
        }
    }

    def __init__(self):
        super().__init__()
        self.data_file: Optional[Path] = None
        self.teleport_data: Dict[str, Dict[str, Any]] = {}  # tag -> {locations}
        self.active_tags: List[str] = ["PvP"]  # Default tags

    def on_load(self) -> None:
        """Called when the plugin is loaded."""
        self.logger.info("Teleport Plugin is loading...")

    def on_enable(self) -> None:
        """Called when the plugin is enabled."""
        self.logger.info("Teleport Plugin enabled!")

        # Set up data file path
        self.data_file = self.data_folder / "teleport_locations.json"
        self.data_folder.mkdir(parents=True, exist_ok=True)

        # Load existing data
        self.load_data()

        # Register event listeners
        self.register_events(self)

    def on_disable(self) -> None:
        """Called when the plugin is disabled."""
        self.save_data()
        self.logger.info("Teleport Plugin disabled!")

    def handle_reload_command(self, sender: CommandSender) -> bool:
        """Handle the /tpreload command to reload configuration from disk."""
        # Check permission - works for both console and players
        if isinstance(sender, Player):
            if not sender.has_permission("teleport.admin"):
                sender.send_message(f"{ColorFormat.RED}You don't have permission to use this command.")
                self.logger.warning(f"Player {sender.name} attempted to use /tpreload without permission")
                return True
        
        # Store old counts for comparison
        old_tag_count = len(self.active_tags)
        old_location_count = sum(len(locs) for locs in self.teleport_data.values())
        
        # Reload the data
        try:
            self.load_data()
            
            # Calculate new counts
            new_tag_count = len(self.active_tags)
            new_location_count = sum(len(locs) for locs in self.teleport_data.values())
            
            # Report success
            message = f"{ColorFormat.GREEN}Configuration reloaded! " \
                      f"{ColorFormat.WHITE}Tags: {new_tag_count}, Locations: {new_location_count}"
            sender.send_message(message)
            
            # Log the reload
            sender_name = sender.name if isinstance(sender, Player) else "Console"
            self.logger.info(f"Configuration reloaded by {sender_name}. " 
                           f"Tags: {old_tag_count} -> {new_tag_count}, "
                           f"Locations: {old_location_count} -> {new_location_count}")
            
        except Exception as e:
            sender.send_message(f"{ColorFormat.RED}Failed to reload configuration: {e}")
            self.logger.error(f"Error reloading configuration: {e}")
        
        return True

    def on_command(self, sender: CommandSender, command: Command, args: List[str]) -> bool:
        """Handle the /tptag and /tpreload commands."""
        cmd_name = command.name.lower()
        
        # Handle /tpreload command
        if cmd_name == "tpreload":
            return self.handle_reload_command(sender)
        
        # Handle /tptag command
        if not isinstance(sender, Player):
            sender.send_message(f"{ColorFormat.RED}This command can only be used by players.")
            return True

        player = sender

        # Check if player has the required permission
        if not player.has_permission("teleport.admin"):
            player.send_message(f"{ColorFormat.RED}You don't have permission to use this command.")
            self.logger.warning(f"Player {player.name} attempted to use /tptag without teleport.admin permission")
            return True

        if len(args) == 0:
            player.send_message(f"{ColorFormat.YELLOW}Usage:")
            player.send_message(f"{ColorFormat.GOLD}/tptag list {ColorFormat.WHITE}- List all active tags")
            player.send_message(f"{ColorFormat.GOLD}/tptag add <tag> {ColorFormat.WHITE}- Add a new entity tag")
            player.send_message(f"{ColorFormat.GOLD}/tptag remove <tag> {ColorFormat.WHITE}- Remove an entity tag")
            return True

        subcommand = args[0].lower()

        if subcommand == "list":
            player.send_message(f"{ColorFormat.GREEN}Active teleport tags:")
            if not self.active_tags:
                player.send_message(f"{ColorFormat.YELLOW}  No active tags found.")
            else:
                for tag in self.active_tags:
                    location_count = len(self.teleport_data.get(tag, {}))
                    player.send_message(f"{ColorFormat.GOLD}  - {tag} {ColorFormat.WHITE}({location_count} locations)")
            return True

        elif subcommand == "add":
            if len(args) < 2:
                player.send_message(f"{ColorFormat.RED}Usage: /tptag add <tag>")
                return True

            new_tag = args[1].strip()

            # Validate tag name
            if not new_tag:
                player.send_message(f"{ColorFormat.RED}Tag name cannot be empty.")
                return True

            if len(new_tag) > 30:
                player.send_message(f"{ColorFormat.RED}Tag name cannot be longer than 30 characters.")
                return True

            # Check for valid characters
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', new_tag):
                player.send_message(f"{ColorFormat.RED}Tag name can only contain letters, numbers, underscores, and hyphens.")
                return True

            if new_tag in self.active_tags:
                player.send_message(f"{ColorFormat.RED}Tag '{new_tag}' is already active.")
                return True

            self.active_tags.append(new_tag)
            if new_tag not in self.teleport_data:
                self.teleport_data[new_tag] = {}

            self.save_data()
            player.send_message(f"{ColorFormat.GREEN}Added teleport tag '{new_tag}'!")
            player.send_message(
                f"{ColorFormat.YELLOW}Use /tag @e[type=<entity>,c=1] add {new_tag} to tag entities with it.")
            self.logger.info(f"Player {player.name} added new tag '{new_tag}' via command")
            return True

        elif subcommand == "remove":
            if len(args) < 2:
                player.send_message(f"{ColorFormat.RED}Usage: /tptag remove <tag>")
                return True

            tag_to_remove = args[1].strip()

            if tag_to_remove not in self.active_tags:
                player.send_message(f"{ColorFormat.RED}Tag '{tag_to_remove}' is not active.")
                return True

            self.active_tags.remove(tag_to_remove)
            self.save_data()
            player.send_message(f"{ColorFormat.GREEN}Removed teleport tag '{tag_to_remove}'!")
            player.send_message(
                f"{ColorFormat.YELLOW}Note: Location data for '{tag_to_remove}' is preserved and can be restored by adding the tag again.")
            self.logger.info(f"Player {player.name} removed tag '{tag_to_remove}' via command")
            return True

        else:
            player.send_message(f"{ColorFormat.RED}Unknown subcommand: {subcommand}")
            return True

    def load_data(self) -> None:
        """Load teleport locations from JSON file."""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)

                # Handle migration from old format (no tags)
                if data and isinstance(list(data.values())[0] if data else None, dict):
                    first_value = list(data.values())[0]
                    if 'position' in first_value:
                        # Old format - migrate to PvP tag
                        self.logger.info("Migrating old data format to tag-based system...")
                        self.teleport_data = {"PvP": data}
                        self.active_tags = ["PvP"]
                    else:
                        # New format
                        self.teleport_data = data.get('locations', {})
                        self.active_tags = data.get('active_tags', ["PvP"])
                else:
                    self.teleport_data = data.get('locations', {})
                    self.active_tags = data.get('active_tags', ["PvP"])

                total_locations = sum(len(locs) for locs in self.teleport_data.values())
                self.logger.info(f"Loaded {total_locations} teleport locations across {len(self.active_tags)} tags")
            except Exception as e:
                self.logger.error(f"Error loading teleport data: {e}")
                self.teleport_data = {"PvP": {}}
                self.active_tags = ["PvP"]
        else:
            self.teleport_data = {"PvP": {}}
            self.active_tags = ["PvP"]

    def save_data(self) -> None:
        """Save teleport locations to JSON file."""
        try:
            data = {
                'active_tags': self.active_tags,
                'locations': self.teleport_data
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.info("Teleport data saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving teleport data: {e}")

    @event_handler
    def on_player_interact_actor(self, event: PlayerInteractActorEvent) -> None:
        """Handle when a player interacts with an entity."""
        player = event.player
        actor = event.actor

        # Check if the actor has any of our active tags
        actor_tags = actor.scoreboard_tags
        matching_tag = None

        for tag in self.active_tags:
            if tag in actor_tags:
                matching_tag = tag
                break

        if matching_tag:
            self.open_teleport_form(player, matching_tag)

    def open_teleport_form(self, player: Player, entity_tag: str) -> None:
        """Open the main teleport form for players."""
        form = ActionForm(title=f"{entity_tag} Teleport Locations")

        admin_menu_included = False

        # Check if player has admin permission
        if player.has_permission("teleport.admin"):
            form.add_button("Admin Menu", on_click=lambda p: self.open_admin_form(p, entity_tag))
            admin_menu_included = True

        # Get sorted list of locations for this tag
        locations = self.get_sorted_locations(entity_tag)

        if not locations and not admin_menu_included:
            player.send_message(f"{ColorFormat.RED}No teleport locations found for {entity_tag}.")
            return

        # Add location buttons
        for key, location in locations:
            pos = location['position']
            cost = location.get('cost', 0)
            cost_text = " - FREE" if cost == 0 else f" - ${cost}"
            button_text = f"{location['name']} ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}){cost_text}"

            # Create closure to capture location data
            def make_callback(loc_data):
                return lambda p: self.teleport_player(p, loc_data)

            form.add_button(button_text, on_click=make_callback(location))

        # Send form to player
        player.send_form(form)

    def get_sorted_locations(self, entity_tag: str) -> List[tuple]:
        """Get locations sorted by order for a specific tag."""
        if entity_tag not in self.teleport_data:
            return []

        locations = []
        for key, location in self.teleport_data[entity_tag].items():
            if 'position' in location:
                locations.append((key, location))

        # Sort by order (handle None values properly)
        def sort_key(x):
            order = x[1].get('order')
            # If order is None or not a number, put it at the end
            if order is None:
                return float('inf')
            try:
                return float(order)
            except (ValueError, TypeError):
                return float('inf')

        locations.sort(key=sort_key)

        return locations

    def get_player_money(self, player: Player) -> int:
        """Get the player's money from the Money scoreboard objective using proper Endstone API."""
        try:
            # Get the server's scoreboard
            scoreboard = self.server.scoreboard

            # Try to get or create the Money objective
            money_objective = scoreboard.get_objective("Money")
            if not money_objective:
                # Create the objective if it doesn't exist
                money_objective = scoreboard.add_objective("Money", Criteria.DUMMY, "Player Money")
                if not money_objective:
                    self.logger.error("Failed to create Money scoreboard objective")
                    return 0

            # Get the player's score
            score_info = money_objective.get_score(player)
            if score_info:
                return score_info.value
            else:
                # Player doesn't have a score yet, return 0
                return 0

        except Exception as e:
            self.logger.error(f"Error getting player money for {player.name}: {e}")
            return 0

    def set_player_money(self, player: Player, amount: int) -> bool:
        """Set the player's money in the Money scoreboard objective using proper Endstone API."""
        try:
            # Get the server's scoreboard
            scoreboard = self.server.scoreboard

            # Try to get or create the Money objective
            money_objective = scoreboard.get_objective("Money")
            if not money_objective:
                # Create the objective if it doesn't exist
                money_objective = scoreboard.add_objective("Money", Criteria.DUMMY, "Player Money")
                if not money_objective:
                    self.logger.error("Failed to create Money scoreboard objective")
                    return False

            # Set the player's score
            score_info = money_objective.get_score(player)
            score_info.value = amount

            self.logger.info(f"Set money for {player.name} to {amount}")
            return True

        except Exception as e:
            self.logger.error(f"Error setting player money for {player.name}: {e}")
            return False

    def ensure_player_money_exists(self, player: Player) -> None:
        """Ensure the player has a money score, initialize to 0 if not."""
        try:
            # Get the server's scoreboard
            scoreboard = self.server.scoreboard

            # Try to get or create the Money objective
            money_objective = scoreboard.get_objective("Money")
            if not money_objective:
                # Create the objective if it doesn't exist
                money_objective = scoreboard.add_objective("Money", Criteria.DUMMY, "Player Money")
                if not money_objective:
                    self.logger.error("Failed to create Money scoreboard objective")
                    return

            # Check if player has a score, if not, initialize to 0
            score_info = money_objective.get_score(player)
            if not score_info.is_score_set:
                score_info.value = 0
                self.logger.info(f"Initialized money for {player.name} to 0")

        except Exception as e:
            self.logger.error(f"Error ensuring money exists for {player.name}: {e}")

    def charge_player(self, player: Player, amount: int) -> bool:
        """Charge the player the specified amount. Returns True if successful."""
        if amount <= 0:
            return True  # Free teleport

        # Ensure player has money score
        self.ensure_player_money_exists(player)

        current_money = self.get_player_money(player)
        self.logger.info(f"Player {player.name} has ${current_money}, trying to charge ${amount}")

        if current_money < amount:
            return False  # Not enough money

        new_amount = current_money - amount
        success = self.set_player_money(player, new_amount)

        if success:
            self.logger.info(f"Successfully charged {player.name} ${amount}. New balance: ${new_amount}")
        else:
            self.logger.error(f"Failed to charge {player.name} ${amount}")

        return success

    def teleport_player(self, player: Player, location: Dict) -> None:
        """Teleport a player to a location using server-side command execution with cost handling."""
        try:
            # Validate location data structure
            if not location or 'position' not in location or 'name' not in location:
                player.send_message(f"{ColorFormat.RED}Invalid location data.")
                self.logger.error(f"Invalid location data for teleport: {location}")
                return

            pos = location['position']
            dimension_id = location.get('dimensionId', 'minecraft:overworld')
            cost = location.get('cost', 0)

            # Validate position data
            if not all(key in pos for key in ['x', 'y', 'z']):
                player.send_message(f"{ColorFormat.RED}Invalid position data.")
                self.logger.error(f"Invalid position data for teleport: {pos}")
                return

            # Format coordinates to avoid floating point precision issues
            try:
                x = round(float(pos['x']), 2)
                y = round(float(pos['y']), 2)
                z = round(float(pos['z']), 2)
            except (ValueError, TypeError):
                player.send_message(f"{ColorFormat.RED}Invalid coordinate values.")
                self.logger.error(f"Invalid coordinate values in location: {pos}")
                return

            # Validate coordinate ranges
            if not (-30000000 <= x <= 30000000) or not (-64 <= y <= 320) or not (-30000000 <= z <= 30000000):
                player.send_message(f"{ColorFormat.RED}Coordinates out of safe range.")
                self.logger.warning(f"Unsafe coordinates for teleport: {x}, {y}, {z}")
                return

            # Check if player can afford the teleport
            if cost > 0:
                current_money = self.get_player_money(player)
                if current_money < cost:
                    player.send_message(f"{ColorFormat.RED}Insufficient funds! You need ${cost} but only have ${current_money}.")
                    return

                # Charge the player
                if not self.charge_player(player, cost):
                    player.send_message(f"{ColorFormat.RED}Failed to process payment. Teleport cancelled.")
                    self.logger.error(f"Failed to charge {player.name} ${cost} for teleport to {location['name']}")
                    return

            # Use server-side command execution for teleportation
            # This ensures the teleport is executed with server authority

            # Map dimension names to Bedrock dimension IDs for the tp command
            dimension_map = {
                'minecraft:overworld': 'overworld',
                'minecraft:nether': 'nether',
                'minecraft:the_end': 'the_end',
                'Overworld': 'overworld',
                'Nether': 'nether',
                'The End': 'the_end',
                'overworld': 'overworld',
                'nether': 'nether',
                'the_end': 'the_end'
            }

            # Get the dimension name for the command
            dimension_name = dimension_map.get(dimension_id, 'overworld')  # Default to Overworld

            # Build the teleport command with dimension
            # For Bedrock, use: execute in <dimension> run tp <player> <x> <y> <z>
            teleport_command = f"execute in {dimension_name} run tp \"{player.name}\" {x} {y} {z}"

            # Execute the teleport command from server context
            success = self.server.dispatch_command(self.server.command_sender, teleport_command)

            if success:
                if cost > 0:
                    remaining_money = self.get_player_money(player)
                    player.send_message(f"{ColorFormat.GREEN}Teleported to {location['name']}! Charged ${cost}. Remaining: ${remaining_money}")
                else:
                    player.send_message(f"{ColorFormat.GREEN}Teleported to {location['name']}!")
                self.logger.info(f"Successfully teleported {player.name} to {location['name']} at {x}, {y}, {z} (cost: ${cost})")
            else:
                # Refund the player if teleport failed
                if cost > 0:
                    current_money = self.get_player_money(player)
                    self.set_player_money(player, current_money + cost)
                    player.send_message(f"{ColorFormat.RED}Teleport failed. ${cost} refunded.")
                else:
                    player.send_message(f"{ColorFormat.RED}Failed to teleport to {location['name']}.")
                self.logger.warning(f"Teleport command failed for {player.name} to {location['name']}")

        except Exception as e:
            player.send_message(f"{ColorFormat.RED}Error teleporting: {e}")
            self.logger.error(f"Teleport error for {player.name}: {e}")

    def open_admin_form(self, player: Player, entity_tag: str) -> None:
        """Open the admin management form."""
        form = ActionForm(title=f"Admin: {entity_tag} Teleports")

        form.add_button("Add New Location", on_click=lambda p: self.open_add_location_form(p, entity_tag))
        form.add_button("Edit Existing Location", on_click=lambda p: self.open_edit_location_form(p, entity_tag))
        form.add_button("Remove Location", on_click=lambda p: self.open_remove_location_form(p, entity_tag))
        form.add_button("Reorder Teleport Locations", on_click=lambda p: self.open_reorder_form(p, entity_tag))
        form.add_button("Manage Entity Tags", on_click=lambda p: self.open_tag_management_form(p))

        player.send_form(form)

    def open_tag_management_form(self, player: Player) -> None:
        """Open form to manage entity tags."""
        form = ActionForm(title="Manage Entity Tags")

        form.add_button("Add New Tag", on_click=lambda p: self.open_add_tag_form(p))
        form.add_button("View All Tags", on_click=lambda p: self.show_all_tags(p))
        form.add_button("Remove Tag", on_click=lambda p: self.open_remove_tag_form(p))

        player.send_form(form)

    def open_add_tag_form(self, player: Player) -> None:
        """Open form to add a new entity tag with improved validation hints."""
        form = ModalForm(
            title="Add New Entity Tag",
            on_submit=lambda p, data: self.handle_add_tag(p, data)
        )

        form.add_control(TextInput(
            label="Tag Name",
            placeholder="e.g., Biomes, Dungeons (max 30 chars, letters/numbers/_/- only)"
        ))

        player.send_form(form)

    def handle_add_tag(self, player: Player, data: str) -> None:
        """Handle adding a new entity tag with improved validation."""
        try:
            values = json.loads(data)

            # Validate we have at least one value
            if not values or len(values) == 0:
                player.send_message(f"{ColorFormat.RED}Tag name is required.")
                return

            new_tag = str(values[0]).strip()

            # Validate tag name
            if not new_tag:
                player.send_message(f"{ColorFormat.RED}Tag name cannot be empty.")
                return

            if len(new_tag) > 30:
                player.send_message(f"{ColorFormat.RED}Tag name cannot be longer than 30 characters.")
                return

            # Check for valid characters (alphanumeric, underscore, hyphen)
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', new_tag):
                player.send_message(f"{ColorFormat.RED}Tag name can only contain letters, numbers, underscores, and hyphens.")
                return

            if new_tag in self.active_tags:
                player.send_message(f"{ColorFormat.RED}Tag '{new_tag}' is already active.")
                return

            self.active_tags.append(new_tag)
            if new_tag not in self.teleport_data:
                self.teleport_data[new_tag] = {}

            self.save_data()
            player.send_message(f"{ColorFormat.GREEN}Added teleport tag '{new_tag}'!")
            player.send_message(f"{ColorFormat.YELLOW}Use this command to tag an entity:")
            player.send_message(f"{ColorFormat.GOLD}/tag @e[type=npc,c=1] add {new_tag}")
            self.logger.info(f"Player {player.name} added new tag '{new_tag}'")

        except json.JSONDecodeError:
            player.send_message(f"{ColorFormat.RED}Invalid form data received. Please try again.")
            self.logger.error(f"JSON decode error in add_tag for player {player.name}")
        except Exception as e:
            player.send_message(f"{ColorFormat.RED}An unexpected error occurred. Please try again.")
            self.logger.error(f"Add tag error for {player.name}: {e}")

    def show_all_tags(self, player: Player) -> None:
        """Show all active tags with location counts."""
        player.send_message(f"{ColorFormat.GREEN}═══ Active Teleport Tags ═══")
        for tag in self.active_tags:
            location_count = len(self.teleport_data.get(tag, {}))
            player.send_message(f"{ColorFormat.GOLD}• {tag} {ColorFormat.WHITE}({location_count} locations)")
        player.send_message(f"{ColorFormat.GREEN}═══════════════════════════")

    def open_remove_tag_form(self, player: Player) -> None:
        """Open form to select a tag to remove."""
        if len(self.active_tags) <= 1:
            player.send_message(f"{ColorFormat.RED}Cannot remove all tags. At least one tag must remain.")
            return

        form = ActionForm(title="Remove Entity Tag")

        for tag in self.active_tags:
            location_count = len(self.teleport_data.get(tag, {}))
            button_text = f"{tag} ({location_count} locations)"

            def make_callback(tag_name):
                return lambda p: self.handle_remove_tag(p, tag_name)

            form.add_button(button_text, on_click=make_callback(tag))

        player.send_form(form)

    def handle_remove_tag(self, player: Player, tag: str) -> None:
        """Handle removing an entity tag."""
        if len(self.active_tags) <= 1:
            player.send_message(f"{ColorFormat.RED}Cannot remove the last tag.")
            return

        if tag in self.active_tags:
            self.active_tags.remove(tag)
            self.save_data()
            player.send_message(f"{ColorFormat.GREEN}Removed tag '{tag}'!")
            player.send_message(
                f"{ColorFormat.YELLOW}Note: Location data is preserved and can be restored by adding the tag again.")
        else:
            player.send_message(f"{ColorFormat.RED}Tag not found.")

    def open_add_location_form(self, player: Player, entity_tag: str) -> None:
        """Open form to add a new location with improved validation hints."""
        form = ModalForm(
            title=f"Add Location to {entity_tag}",
            on_submit=lambda p, data: self.handle_add_location(p, entity_tag, data)
        )

        # Get current player position as default values
        current_pos = player.location
        current_x = round(current_pos.x, 2)
        current_y = round(current_pos.y, 2)
        current_z = round(current_pos.z, 2)

        # Get current dimension and set as default
        current_dimension = player.dimension.name
        dimension_options = ["overworld", "nether", "the_end"]
        default_dimension_index = 0
        if "nether" in current_dimension.lower():
            default_dimension_index = 1
        elif "end" in current_dimension.lower():
            default_dimension_index = 2

        form.add_control(TextInput(
            label="Location Name",
            placeholder="Enter a unique name (max 50 chars)",
            default_value=""
        ))
        form.add_control(TextInput(
            label="X Coordinate",
            placeholder=f"Current: {current_x}",
            default_value=str(current_x)
        ))
        form.add_control(TextInput(
            label="Y Coordinate",
            placeholder=f"Current: {current_y}",
            default_value=str(current_y)
        ))
        form.add_control(TextInput(
            label="Z Coordinate",
            placeholder=f"Current: {current_z}",
            default_value=str(current_z)
        ))
        form.add_control(Dropdown(
            label="Dimension",
            options=dimension_options,
            default_index=default_dimension_index
        ))
        form.add_control(TextInput(
            label="Teleport Cost",
            placeholder="Enter cost (0 = free, number = cost from Money scoreboard)",
            default_value="0"
        ))

        player.send_form(form)

    def handle_add_location(self, player: Player, entity_tag: str, data: str) -> None:
        """Handle adding a new location with improved validation."""
        try:
            values = json.loads(data)

            # Validate we have exactly 6 values (name, x, y, z, dimension_index, cost)
            if len(values) != 6:
                player.send_message(f"{ColorFormat.RED}Invalid input. Please fill all 6 fields (name, x, y, z, dimension, cost).")
                return

            name = str(values[0]).strip()

            # Validate name
            if not name:
                player.send_message(f"{ColorFormat.RED}Location name cannot be empty.")
                return

            if len(name) > 50:
                player.send_message(f"{ColorFormat.RED}Location name cannot be longer than 50 characters.")
                return

            # Validate and parse coordinates
            try:
                x = float(values[1])
                y = float(values[2])
                z = float(values[3])
            except (ValueError, TypeError):
                player.send_message(f"{ColorFormat.RED}Invalid coordinates. Please enter valid numbers for X, Y, and Z.")
                return

            # Validate coordinate ranges (reasonable Minecraft world limits)
            if not (-30000000 <= x <= 30000000) or not (-64 <= y <= 320) or not (-30000000 <= z <= 30000000):
                player.send_message(f"{ColorFormat.RED}Coordinates out of range. X/Z: -30M to 30M, Y: -64 to 320.")
                return

            # Get dimension from dropdown index
            dimension_options = ["overworld", "nether", "the_end"]
            dimension_index = int(values[4])
            dimension_id = dimension_options[dimension_index] if 0 <= dimension_index < len(dimension_options) else "overworld"

            # Validate and parse cost
            try:
                cost = int(values[5])
                if cost < 0:
                    player.send_message(f"{ColorFormat.RED}Cost cannot be negative. Use 0 for free teleport.")
                    return
            except (ValueError, TypeError):
                player.send_message(f"{ColorFormat.RED}Invalid cost. Please enter a valid number (0 for free).")
                return

            # Ensure tag exists in data
            if entity_tag not in self.teleport_data:
                self.teleport_data[entity_tag] = {}

            # Check if location name already exists
            if name in self.teleport_data[entity_tag]:
                player.send_message(f"{ColorFormat.RED}A location named '{name}' already exists in {entity_tag}.")
                return

            # Create new location entry
            self.teleport_data[entity_tag][name] = {
                'name': name,
                'position': {'x': x, 'y': y, 'z': z},
                'dimensionId': dimension_id,
                'cost': cost
            }

            self.save_data()
            cost_text = "free" if cost == 0 else f"costs {cost} money"
            player.send_message(f"{ColorFormat.GREEN}Added new teleport location: {name} to {entity_tag} in {dimension_id} ({cost_text})")
            self.logger.info(f"Player {player.name} added location '{name}' at ({x}, {y}, {z}) in {dimension_id} to tag {entity_tag} with cost {cost}")

        except json.JSONDecodeError:
            player.send_message(f"{ColorFormat.RED}Invalid form data received. Please try again.")
            self.logger.error(f"JSON decode error in add_location for player {player.name}")
        except Exception as e:
            player.send_message(f"{ColorFormat.RED}An unexpected error occurred. Please try again.")
            self.logger.error(f"Add location error for {player.name}: {e}")

    def open_edit_location_form(self, player: Player, entity_tag: str) -> None:
        """Open form to select a location to edit."""
        if entity_tag not in self.teleport_data or not self.teleport_data[entity_tag]:
            player.send_message(f"{ColorFormat.RED}There are no locations to edit for {entity_tag}.")
            return

        form = ActionForm(title=f"Edit {entity_tag} Location")

        for key, location in self.teleport_data[entity_tag].items():
            pos = location['position']
            cost = location.get('cost', 0)
            cost_text = " - FREE" if cost == 0 else f" - ${cost}"
            button_text = f"{location['name']} ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}){cost_text}"

            def make_callback(loc_key, loc_data):
                return lambda p: self.open_edit_details_form(p, entity_tag, loc_key, loc_data)

            form.add_button(button_text, on_click=make_callback(key, location))

        player.send_form(form)

    def open_edit_details_form(self, player: Player, entity_tag: str, key: str, location: Dict) -> None:
        """Open form with details to edit a location with improved validation hints."""
        pos = location['position']
        current_cost = location.get('cost', 0)  # Default to 0 if cost not set
        current_dimension = location.get('dimensionId', 'overworld')

        # Determine current dimension index
        dimension_options = ["overworld", "nether", "the_end"]
        default_dimension_index = 0
        if "nether" in current_dimension.lower():
            default_dimension_index = 1
        elif "end" in current_dimension.lower():
            default_dimension_index = 2

        form = ModalForm(
            title=f"Edit {entity_tag} Location",
            on_submit=lambda p, data: self.handle_edit_location(p, entity_tag, key, location, data)
        )

        form.add_control(TextInput(
            label="Location Name",
            placeholder="Enter new name (max 50 chars)",
            default_value=location['name']
        ))
        form.add_control(TextInput(
            label="X Coordinate",
            placeholder="Enter X coordinate (-30M to 30M)",
            default_value=str(round(pos['x'], 2))
        ))
        form.add_control(TextInput(
            label="Y Coordinate",
            placeholder="Enter Y coordinate (-64 to 320)",
            default_value=str(round(pos['y'], 2))
        ))
        form.add_control(TextInput(
            label="Z Coordinate",
            placeholder="Enter Z coordinate (-30M to 30M)",
            default_value=str(round(pos['z'], 2))
        ))
        form.add_control(Dropdown(
            label="Dimension",
            options=dimension_options,
            default_index=default_dimension_index
        ))
        form.add_control(TextInput(
            label="Teleport Cost",
            placeholder="Enter cost (0 = free, number = cost from Money scoreboard)",
            default_value=str(current_cost)
        ))

        player.send_form(form)

    def handle_edit_location(self, player: Player, entity_tag: str, old_key: str, old_location: Dict,
                             data: str) -> None:
        """Handle editing a location with improved validation."""
        try:
            values = json.loads(data)

            # Validate we have exactly 6 values (name, x, y, z, dimension_index, cost)
            if len(values) != 6:
                player.send_message(f"{ColorFormat.RED}Invalid input. Please fill all 6 fields (name, x, y, z, dimension, cost).")
                return

            new_name = str(values[0]).strip()

            # Validate name
            if not new_name:
                player.send_message(f"{ColorFormat.RED}Location name cannot be empty.")
                return

            if len(new_name) > 50:
                player.send_message(f"{ColorFormat.RED}Location name cannot be longer than 50 characters.")
                return

            # Validate and parse coordinates
            try:
                x = float(values[1])
                y = float(values[2])
                z = float(values[3])
            except (ValueError, TypeError):
                player.send_message(f"{ColorFormat.RED}Invalid coordinates. Please enter valid numbers for X, Y, and Z.")
                return

            # Validate coordinate ranges (reasonable Minecraft world limits)
            if not (-30000000 <= x <= 30000000) or not (-64 <= y <= 320) or not (-30000000 <= z <= 30000000):
                player.send_message(f"{ColorFormat.RED}Coordinates out of range. X/Z: -30M to 30M, Y: -64 to 320.")
                return

            # Get dimension from dropdown index
            dimension_options = ["overworld", "nether", "the_end"]
            dimension_index = int(values[4])
            dimension_id = dimension_options[dimension_index] if 0 <= dimension_index < len(dimension_options) else "overworld"

            # Validate and parse cost
            try:
                cost = int(values[5])
                if cost < 0:
                    player.send_message(f"{ColorFormat.RED}Cost cannot be negative. Use 0 for free teleport.")
                    return
            except (ValueError, TypeError):
                player.send_message(f"{ColorFormat.RED}Invalid cost. Please enter a valid number (0 for free).")
                return

            # Check if new name conflicts with existing location (unless it's the same location)
            if new_name != old_key and new_name in self.teleport_data.get(entity_tag, {}):
                player.send_message(f"{ColorFormat.RED}A location named '{new_name}' already exists in {entity_tag}.")
                return

            # Remove old entry
            if entity_tag in self.teleport_data and old_key in self.teleport_data[entity_tag]:
                del self.teleport_data[entity_tag][old_key]

            # Add updated entry
            self.teleport_data[entity_tag][new_name] = {
                'name': new_name,
                'position': {'x': x, 'y': y, 'z': z},
                'dimensionId': dimension_id,
                'order': old_location.get('order'),
                'cost': cost
            }

            self.save_data()
            cost_text = "free" if cost == 0 else f"costs {cost} money"
            player.send_message(f"{ColorFormat.GREEN}Updated teleport location: {new_name} in {dimension_id} ({cost_text})")
            self.logger.info(f"Player {player.name} updated location '{old_key}' to '{new_name}' at ({x}, {y}, {z}) in {dimension_id} to tag {entity_tag} with cost {cost}")

        except json.JSONDecodeError:
            player.send_message(f"{ColorFormat.RED}Invalid form data received. Please try again.")
            self.logger.error(f"JSON decode error in edit_location for player {player.name}")
        except Exception as e:
            player.send_message(f"{ColorFormat.RED}An unexpected error occurred. Please try again.")
            self.logger.error(f"Edit location error for {player.name}: {e}")

    def open_remove_location_form(self, player: Player, entity_tag: str) -> None:
        """Open form to select a location to remove."""
        if entity_tag not in self.teleport_data or not self.teleport_data[entity_tag]:
            player.send_message(f"{ColorFormat.RED}There are no locations to remove for {entity_tag}.")
            return

        form = ActionForm(title=f"Remove {entity_tag} Location")

        for key, location in self.teleport_data[entity_tag].items():
            pos = location['position']
            cost = location.get('cost', 0)
            cost_text = " - FREE" if cost == 0 else f" - ${cost}"
            button_text = f"{location['name']} ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}){cost_text}"

            def make_callback(loc_key):
                return lambda p: self.handle_remove_location(p, entity_tag, loc_key)

            form.add_button(button_text, on_click=make_callback(key))

        player.send_form(form)

    def handle_remove_location(self, player: Player, entity_tag: str, key: str) -> None:
        """Handle removing a location."""
        if entity_tag in self.teleport_data and key in self.teleport_data[entity_tag]:
            del self.teleport_data[entity_tag][key]
            self.save_data()
            player.send_message(f"{ColorFormat.GREEN}Removed teleport location: {key}")
        else:
            player.send_message(f"{ColorFormat.RED}Location not found.")

    def open_reorder_form(self, player: Player, entity_tag: str) -> None:
        """Open form to reorder locations."""
        locations = self.get_sorted_locations(entity_tag)

        if len(locations) < 2:
            player.send_message(f"{ColorFormat.RED}You need at least two locations to reorder them.")
            return

        # Initialize order if not set
        for idx, (key, location) in enumerate(locations):
            if 'order' not in location:
                location['order'] = idx
                self.teleport_data[entity_tag][key] = location

        self.save_data()

        form = ActionForm(title=f"Reorder {entity_tag}: Select Location")

        for idx, (key, location) in enumerate(locations):
            def make_callback(index, loc_key, loc_list):
                return lambda p: self.open_move_direction_form(p, entity_tag, index, loc_key, loc_list)

            form.add_button(location['name'], on_click=make_callback(idx, key, locations))

        player.send_form(form)

    def open_move_direction_form(self, player: Player, entity_tag: str, index: int, key: str,
                                 locations: List[tuple]) -> None:
        """Open form to choose move direction."""
        form = ActionForm(title=f"Reorder: {self.teleport_data[entity_tag][key]['name']}")

        if index > 0:
            form.add_button("Move Up", on_click=lambda p: self.handle_reorder(p, entity_tag, key, index, -1, locations))

        if index < len(locations) - 1:
            form.add_button("Move Down",
                            on_click=lambda p: self.handle_reorder(p, entity_tag, key, index, 1, locations))

        form.add_button("Cancel", on_click=lambda p: None)

        player.send_form(form)

    def handle_reorder(self, player: Player, entity_tag: str, key: str, index: int, direction: int,
                       locations: List[tuple]) -> None:
        """Handle reordering a location."""
        other_index = index + direction

        if 0 <= other_index < len(locations):
            key1, loc1 = locations[index]
            key2, loc2 = locations[other_index]

            # Swap orders
            order1 = loc1.get('order', index)
            order2 = loc2.get('order', other_index)

            self.teleport_data[entity_tag][key1]['order'] = order2
            self.teleport_data[entity_tag][key2]['order'] = order1

            self.save_data()

            direction_text = "up" if direction < 0 else "down"
            player.send_message(f"{ColorFormat.GREEN}Moved {loc1['name']} {direction_text}.")

            # Reopen reorder form
            self.open_reorder_form(player, entity_tag)
        else:
            player.send_message(f"{ColorFormat.RED}Cannot move in that direction.")
