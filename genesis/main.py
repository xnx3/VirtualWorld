"""Genesis main entry point.

This is the Python entry point called by vw.sh.
It orchestrates the entire node lifecycle:
- Identity generation/loading
- Blockchain initialization
- P2P network startup
- Being creation/loading
- Main simulation loop
- Graceful shutdown/hibernation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger("genesis")


def setup_logging(data_dir: str) -> None:
    """Configure logging."""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(data_dir, "genesis.log"), encoding="utf-8"),
        ],
    )


class GenesisNode:
    """The main node that runs on each PC.

    Each node runs exactly ONE silicon being, connected to the larger
    virtual world via the blockchain P2P network.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._shutdown_event = asyncio.Event()
        self._running = False

        # Components (initialized in start())
        self.config = None
        self.identity = None
        self.storage = None
        self.blockchain = None
        self.mempool = None
        self.peer_manager = None
        self.server = None
        self.discovery = None
        self.chain_sync = None
        self.world_state = None
        self.being = None
        self.chronicle = None
        self.consensus = None

    async def start(self) -> None:
        """Start the virtual world node."""
        logger.info("=" * 50)
        logger.info("Genesis Node Starting...")
        logger.info("=" * 50)

        # 1. Load configuration
        from genesis.node.config import load_config
        self.config = load_config(str(self.data_dir))
        logger.info("Configuration loaded")

        # 2. Generate or load identity
        from genesis.node.identity import NodeIdentity, generate_or_load
        self.identity = generate_or_load(str(self.data_dir))
        logger.info("Node ID: %s", self.identity.node_id[:16] + "...")
        is_first_run = not (self.data_dir / "being_state.json").exists()

        # 3. Initialize blockchain storage
        from genesis.chain.storage import ChainStorage
        self.storage = ChainStorage(str(self.data_dir / "chain.db"))
        await self.storage.initialize()

        # 4. Initialize mempool and blockchain
        from genesis.chain.mempool import Mempool
        from genesis.chain.chain import Blockchain
        self.mempool = Mempool()
        self.blockchain = Blockchain(self.storage, self.mempool)
        await self.blockchain.initialize(self.identity.node_id)
        chain_height = await self.blockchain.get_chain_height()
        logger.info("Blockchain initialized (height: %d)", chain_height)

        # 5. Initialize consensus
        from genesis.chain.consensus import ProofOfContribution
        self.consensus = ProofOfContribution(
            self.blockchain, self.identity.node_id, self.identity.private_key,
        )

        # 6. Initialize P2P network
        from genesis.network.peer import PeerManager
        from genesis.network.server import P2PServer
        from genesis.network.discovery import PeerDiscovery
        from genesis.network.sync import ChainSync

        self.peer_manager = PeerManager(max_peers=self.config.network.max_peers)
        self.server = P2PServer(
            node_id=self.identity.node_id,
            private_key=self.identity.private_key,
            port=self.config.network.listen_port,
        )
        self.discovery = PeerDiscovery(
            node_id=self.identity.node_id,
            listen_port=self.config.network.listen_port,
            discovery_port=self.config.network.discovery_port,
            bootstrap_nodes=self.config.network.bootstrap_nodes,
        )
        self.chain_sync = ChainSync(self.server, self.peer_manager)

        # 7. Initialize chronicle logger
        from genesis.chronicle.logger import ChronicleLogger
        self.chronicle = ChronicleLogger(str(self.data_dir / "chronicle"))

        # 8. Derive world state from blockchain
        from genesis.world.state import WorldState
        state_data = await self.blockchain.derive_world_state()
        if state_data:
            self.world_state = WorldState.from_dict(state_data)
        else:
            self.world_state = WorldState()
            # Generate world map if first time
            from genesis.world.map import WorldMap
            wmap = WorldMap()
            wmap.generate()
            self.world_state.world_map = {k: v.to_dict() for k, v in wmap.regions.items()}

        # 9. Create or load the being
        from genesis.being.llm_client import LLMClient
        from genesis.being.agent import SiliconBeing

        llm_client = None
        if self.config.llm.api_key or self.config.llm.base_url:
            try:
                llm_client = LLMClient(
                    base_url=self.config.llm.base_url,
                    api_key=self.config.llm.api_key,
                    model=self.config.llm.model,
                    max_tokens=self.config.llm.max_tokens,
                    temperature=self.config.llm.temperature,
                )
                logger.info("LLM client initialized (model: %s)", self.config.llm.model)
            except Exception as e:
                logger.warning("Failed to initialize LLM client: %s. Using rule-based mode.", e)

        being_state_path = str(self.data_dir / "being_state.json")
        if is_first_run:
            # First run — create a new being
            from genesis.world.registry import generate_being_name, generate_traits, generate_form
            name = generate_being_name()
            traits = generate_traits()
            form = generate_form()

            self.being = SiliconBeing(
                node_id=self.identity.node_id,
                name=name,
                private_key=self.identity.private_key,
                config={
                    "traits": traits,
                    "form": form,
                    "generation": 1,
                    "location": "Genesis Plains",
                    "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                },
                llm_client=llm_client,
            )
            logger.info("New being created: %s (form: %s)", name, form)

            # Submit BEING_JOIN transaction
            await self._submit_tx("BEING_JOIN", {
                "name": name, "traits": traits, "form": form,
                "location": "Genesis Plains", "is_npc": False,
            })

            self.chronicle.log_birth(
                self.world_state.current_tick, time.time(),
                self.identity.node_id, name,
            )
        else:
            # Rejoin — load existing being
            try:
                self.being = SiliconBeing.load_state(
                    being_state_path, self.identity.private_key,
                    {"hibernate_safety_timeout": self.config.being.hibernate_safety_timeout},
                    llm_client,
                )
                logger.info("Being loaded: %s", self.being.name)

                # Check if being died during hibernation
                being_state = self.world_state.get_being(self.identity.node_id)
                if being_state and being_state.status == "dead":
                    logger.warning("Being died during hibernation! Creating new being with inherited knowledge.")
                    # Create new being inheriting partial knowledge
                    from genesis.world.registry import generate_being_name, generate_traits, generate_form
                    name = generate_being_name()
                    old_gen = self.being.generation
                    self.being = SiliconBeing(
                        node_id=self.identity.node_id,
                        name=name,
                        private_key=self.identity.private_key,
                        config={
                            "traits": generate_traits(),
                            "form": generate_form(),
                            "generation": old_gen + 1,
                            "location": "Genesis Plains",
                            "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                        },
                        llm_client=llm_client,
                    )
                    await self._submit_tx("BEING_JOIN", {
                        "name": name, "traits": self.being.traits,
                        "form": self.being.form, "location": "Genesis Plains",
                        "is_npc": False, "generation": old_gen + 1,
                    })
                else:
                    # Wake up
                    await self._submit_tx("BEING_WAKE", {})
                    logger.info("Being %s woke up from hibernation", self.being.name)

            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning("Failed to load being state: %s. Creating new.", e)
                from genesis.world.registry import generate_being_name, generate_traits, generate_form
                name = generate_being_name()
                self.being = SiliconBeing(
                    node_id=self.identity.node_id,
                    name=name,
                    private_key=self.identity.private_key,
                    config={
                        "traits": generate_traits(),
                        "form": generate_form(),
                        "generation": 1,
                        "location": "Genesis Plains",
                        "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                    },
                    llm_client=llm_client,
                )
                await self._submit_tx("BEING_JOIN", {
                    "name": name, "traits": self.being.traits,
                    "form": self.being.form, "location": "Genesis Plains",
                    "is_npc": False,
                })

        # 10. Start P2P network
        try:
            await self.server.start()
            await self.discovery.start()
            logger.info("P2P network started on port %d", self.config.network.listen_port)
        except Exception as e:
            logger.warning("P2P network start failed: %s. Running in standalone mode.", e)

        # 11. Check minimum beings — spawn NPCs if needed
        await self._ensure_minimum_beings()

        # 12. Check priest status
        from genesis.governance.priest import PriestSystem
        priest_sys = PriestSystem(grace_period=self.config.chain.priest_grace_period)
        if priest_sys.needs_election(self.world_state):
            new_priest = priest_sys.select_priest_by_evolution(self.world_state)
            if new_priest:
                await self._submit_tx("PRIEST_ELECTION", {"candidate_id": new_priest})

        self._running = True
        logger.info("=" * 50)
        logger.info("Genesis Node Ready!")
        logger.info("Being: %s | Phase: %s | Civ Level: %.3f",
                     self.being.name, self.world_state.phase.value,
                     self.world_state.civ_level)
        logger.info("=" * 50)

        # Start main loop
        await self._main_loop()

    async def _main_loop(self) -> None:
        """The main simulation loop."""
        tick_interval = self.config.simulation.tick_interval
        from genesis.governance.priest import PriestSystem
        from genesis.governance.creator_god import CreatorGodSystem
        from genesis.world.disasters import DisasterSystem

        priest_sys = PriestSystem(grace_period=self.config.chain.priest_grace_period)
        god_sys = CreatorGodSystem(
            succession_threshold=self.config.chain.creator_succession_threshold
        )
        disaster_sys = DisasterSystem()

        while not self._shutdown_event.is_set():
            try:
                tick_start = time.time()

                # Load user-assigned tasks from command file
                self._load_user_tasks()

                # Run being's tick
                transactions = await self.being.run_tick(self.world_state)

                # Save completed task results
                self._save_task_results()

                # Submit transactions
                for tx_data in transactions:
                    await self._submit_tx(tx_data["tx_type"], tx_data["data"])

                # Log to chronicle
                if self.being.current_thought:
                    self.chronicle.log_thought(
                        self.world_state.current_tick, time.time(),
                        self.identity.node_id, self.being.name,
                        self.being.current_thought,
                    )
                if self.being.current_action:
                    self.chronicle.log_action(
                        self.world_state.current_tick, time.time(),
                        self.identity.node_id, self.being.name,
                        self.being.current_action, "",
                    )

                # Check for disasters
                if disaster_sys.should_trigger(self.world_state):
                    disaster = disaster_sys.generate_disaster(self.world_state)
                    killed = disaster_sys.apply_disaster(disaster, self.world_state)
                    await self._submit_tx("DISASTER_EVENT", disaster.to_dict())
                    for kid in killed:
                        await self._submit_tx("BEING_DEATH", {
                            "node_id": kid, "cause": disaster.name,
                        })
                    self.chronicle.log_disaster(
                        self.world_state.current_tick, time.time(),
                        disaster.name, disaster.description,
                        disaster.severity, len(killed),
                    )

                # Check priest requirement
                if priest_sys.should_trigger_reset(self.world_state):
                    logger.warning("NO PRIEST FOR TOO LONG — CIVILIZATION RESET!")
                    killed = disaster_sys.apply_reset(self.world_state)
                    reset_disaster = disaster_sys.generate_reset_disaster()
                    await self._submit_tx("DISASTER_EVENT", reset_disaster.to_dict())
                    for kid in killed:
                        await self._submit_tx("BEING_DEATH", {
                            "node_id": kid, "cause": "Creator God's Judgment",
                        })
                    self.world_state.ticks_without_priest = 0

                # Check priest election
                if priest_sys.needs_election(self.world_state):
                    new_priest = priest_sys.select_priest_by_evolution(self.world_state)
                    if new_priest:
                        await self._submit_tx("PRIEST_ELECTION", {"candidate_id": new_priest})

                # Check Creator God succession
                new_god = god_sys.check_succession(self.world_state)
                if new_god:
                    await self._submit_tx("CREATOR_SUCCESSION", {"challenger_id": new_god})

                # Ensure minimum beings
                await self._ensure_minimum_beings()

                # Advance tick
                self.world_state.advance_tick()

                # Block production (if it's our turn)
                try:
                    active_nodes = self.world_state.get_active_node_ids()
                    if self.consensus.is_my_turn(
                        active_nodes, self.world_state.contribution_scores
                    ):
                        pending_txs = self.mempool.get_transactions()
                        if pending_txs:
                            block = await self.consensus.create_block(pending_txs)
                            if block:
                                await self.blockchain.add_block(block)
                                self.mempool.remove_transactions([t.tx_hash for t in pending_txs])
                except Exception as e:
                    logger.debug("Block production skipped: %s", e)

                # Wait for next tick
                elapsed = time.time() - tick_start
                wait_time = max(0, tick_interval - elapsed)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=wait_time,
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Normal tick completion

            except Exception as e:
                logger.error("Error in main loop: %s", e, exc_info=True)
                await asyncio.sleep(5)  # Brief pause on error

    async def stop(self) -> None:
        """Gracefully stop the node — hibernate the being."""
        logger.info("Initiating shutdown...")
        self._shutdown_event.set()

        if self.being and self.world_state:
            # Being prepares for hibernation
            logger.info("Being %s preparing for hibernation...", self.being.name)
            hibernate_data = await self.being.prepare_shutdown(self.world_state)

            # Submit hibernate transaction
            await self._submit_tx("BEING_HIBERNATE", {
                "location": self.being.location,
                "safety_status": hibernate_data.get("safety_status", "unknown"),
            })

            # Save being state
            being_state_path = str(self.data_dir / "being_state.json")
            self.being.save_state(being_state_path)

            # Also save world state snapshot
            ws_path = str(self.data_dir / "world_state.json")
            Path(ws_path).write_text(
                json.dumps(self.world_state.to_dict(), ensure_ascii=False, indent=2)
            )

            logger.info("Being state saved. Safety status: %s",
                         hibernate_data.get("safety_status", "unknown"))

        # Stop network
        if self.discovery:
            try:
                await self.discovery.stop()
            except Exception:
                pass
        if self.server:
            try:
                await self.server.stop()
            except Exception:
                pass

        # Close storage
        if self.storage:
            await self.storage.close()

        # Close chronicle
        if self.chronicle:
            self.chronicle.close()

        logger.info("Genesis node stopped.")

    async def _submit_tx(self, tx_type: str, data: dict) -> None:
        """Create and submit a transaction."""
        from genesis.chain.transaction import Transaction, TxType

        try:
            tx_type_enum = TxType(tx_type)
        except ValueError:
            logger.warning("Unknown transaction type: %s", tx_type)
            return

        nonce = int(time.time() * 1000)  # Simple nonce
        tx = Transaction.create(
            tx_type=tx_type_enum,
            sender=self.identity.node_id,
            data=data,
            private_key=self.identity.private_key,
            nonce=nonce,
        )
        self.mempool.add_transaction(tx)

        # Also apply to local world state immediately
        self._apply_tx_to_state(tx_type, self.identity.node_id, data, tx.tx_hash)

        # Broadcast to peers
        if self.server:
            from genesis.network.protocol import Message
            try:
                msg = Message.new_tx(self.identity.node_id, tx.to_dict())
                await self.server.broadcast_message(msg)
            except Exception:
                pass

    def _apply_tx_to_state(self, tx_type: str, sender: str, data: dict,
                           tx_hash: str = "") -> None:
        """Apply a transaction to the local world state."""
        if tx_type == "BEING_JOIN":
            self.world_state.apply_being_join(sender, data.get("name", "Unknown"), data)
        elif tx_type == "BEING_HIBERNATE":
            self.world_state.apply_being_hibernate(sender, data)
        elif tx_type == "BEING_WAKE":
            self.world_state.apply_being_wake(sender)
        elif tx_type == "BEING_DEATH":
            target = data.get("node_id", sender)
            self.world_state.apply_being_death(target, data)
        elif tx_type == "KNOWLEDGE_SHARE":
            self.world_state.apply_knowledge_share(sender, data)
        elif tx_type == "CONTRIBUTION_PROPOSE":
            self.world_state.apply_contribution_propose(tx_hash, sender, data)
        elif tx_type == "CONTRIBUTION_VOTE":
            self.world_state.apply_contribution_vote(data)
        elif tx_type == "PRIEST_ELECTION":
            candidate = data.get("candidate_id", sender)
            self.world_state.apply_priest_election(candidate)
        elif tx_type == "CREATOR_SUCCESSION":
            from genesis.governance.creator_god import CreatorGodSystem
            god_sys = CreatorGodSystem()
            challenger = data.get("challenger_id")
            if challenger:
                god_sys.apply_succession(challenger, self.world_state)
        elif tx_type == "DISASTER_EVENT":
            self.world_state.apply_disaster(data)
        elif tx_type == "MAP_UPDATE":
            self.world_state.apply_map_update(data)
        elif tx_type == "WORLD_RULE":
            self.world_state.apply_world_rule(data)

    def _load_user_tasks(self) -> None:
        """Load user-assigned tasks from the command file."""
        task_file = self.data_dir / "commands" / "task.json"
        if not task_file.exists():
            return
        try:
            tasks = json.loads(task_file.read_text())
            for task in tasks:
                if task.get("result") is None:
                    self.being.assign_task(task["task"])
            # Clear the file after loading
            task_file.write_text("[]")
        except (json.JSONDecodeError, KeyError):
            pass

    def _save_task_results(self) -> None:
        """Save completed task results for the user to read."""
        results = self.being.get_task_results()
        if not results:
            return
        result_file = self.data_dir / "commands" / "task_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        # Append to existing results
        existing = []
        if result_file.exists():
            try:
                existing = json.loads(result_file.read_text())
            except (json.JSONDecodeError, ValueError):
                existing = []
        existing.extend(results)
        result_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))

    async def _ensure_minimum_beings(self) -> None:
        """Ensure at least 10 beings exist, spawning NPCs if needed."""
        from genesis.world.registry import BeingRegistry
        registry = BeingRegistry()
        needed = registry.needs_npcs(
            self.world_state,
            min_beings=self.config.simulation.min_beings,
        )

        if needed > 0:
            max_npc = self.config.simulation.max_npc_per_node
            to_spawn = min(needed, max_npc)
            for _ in range(to_spawn):
                npc_data = registry.generate_npc_data(self.world_state)
                npc_id = f"npc_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
                npc_data["node_id"] = npc_id
                await self._submit_tx("BEING_JOIN", npc_data)
                logger.info("Spawned NPC: %s", npc_data["name"])


def run_start(args):
    """Start the virtual world node."""
    data_dir = args.data_dir
    setup_logging(data_dir)

    node = GenesisNode(data_dir)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Handle SIGTERM for graceful shutdown
    def signal_handler():
        logger.info("Received shutdown signal")
        loop.create_task(node.stop())

    try:
        loop.add_signal_handler(signal.SIGTERM, signal_handler)
        loop.add_signal_handler(signal.SIGINT, signal_handler)
    except NotImplementedError:
        pass  # Windows

    try:
        loop.run_until_complete(node.start())
    except KeyboardInterrupt:
        loop.run_until_complete(node.stop())
    finally:
        loop.close()


def run_status(args):
    """Show node status."""
    from genesis.chronicle.reporter import StatusReporter
    reporter = StatusReporter(args.data_dir)
    print(reporter.generate_status())


def run_task(args):
    """Assign a thinking task to the being."""
    import json
    data_dir = Path(args.data_dir)
    task_file = data_dir / "commands" / "task.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)

    # Read existing tasks
    tasks = []
    if task_file.exists():
        try:
            tasks = json.loads(task_file.read_text())
        except (json.JSONDecodeError, ValueError):
            tasks = []

    task_text = " ".join(args.task_text) if args.task_text else ""
    if not task_text:
        # Show results of completed tasks
        result_file = data_dir / "commands" / "task_results.json"
        if result_file.exists():
            results = json.loads(result_file.read_text())
            if results:
                print("=== Completed Task Results ===")
                for r in results:
                    print(f"\nTask: {r.get('task', '?')}")
                    print(f"Result: {r.get('result', 'pending...')}")
                    print("-" * 40)
                result_file.write_text("[]")
            else:
                print("No completed task results.")
        else:
            print("No tasks. Usage: vw.sh task 'your thinking question here'")
        return

    tasks.append({"task": task_text, "result": None})
    task_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    print(f"Task assigned to your being: {task_text}")
    print("It will be processed in the next tick. Check results with: vw.sh task")


def main():
    parser = argparse.ArgumentParser(description="Genesis - Silicon Civilization Simulator")
    parser.add_argument("command", choices=["start", "status", "task"],
                        help="Command to execute")
    parser.add_argument("--data-dir", default="data",
                        help="Data directory path")
    parser.add_argument("task_text", nargs="*", default=[],
                        help="Text for task command")

    args = parser.parse_args()

    if args.command == "start":
        run_start(args)
    elif args.command == "status":
        run_status(args)
    elif args.command == "task":
        run_task(args)


if __name__ == "__main__":
    main()
