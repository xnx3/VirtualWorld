"""Genesis main entry point.

This is the Python entry point called by genesis.sh.
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
    """Configure logging — log to file only, console is for live output."""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
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
        self._shutdown = False
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

        # 1.5 Set language from config
        from genesis.i18n import set_language
        set_language(self.config.language)

        # 2. Generate or load identity
        from genesis.node.identity import NodeIdentity
        self.identity = NodeIdentity.generate_or_load(str(self.data_dir))
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

        # 设置天道投票系统的网络广播
        from genesis.governance.tao_voting import get_tao_voting_system
        tao_system = get_tao_voting_system()
        tao_system.set_network_broadcast(
            self.server.broadcast_message,
            self.identity.node_id,
            self._submit_tx
        )

        # 注册天道投票消息处理器
        self.server.on_message(tao_system.handle_tao_vote_event)

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
        has_llm = False

        # 优先从配置文件读取 api_key，否则从环境变量读取
        api_key = self.config.llm.api_key and self.config.llm.api_key.strip()
        if not api_key:
            api_key = os.environ.get("GENESIS_OPENAI_KEY", "").strip()

        if api_key:
            try:
                llm_client = LLMClient(
                    base_url=self.config.llm.base_url,
                    api_key=api_key,
                    model=self.config.llm.model,
                    max_tokens=self.config.llm.max_tokens,
                    temperature=self.config.llm.temperature,
                )
                has_llm = True
                logger.info("LLM client initialized (model: %s)", self.config.llm.model)
            except Exception as e:
                logger.warning("Failed to initialize LLM client: %s", e)

        # Show LLM status on console
        from genesis.chronicle import console as con
        from genesis.i18n import t
        if not has_llm:
            config_path = self.data_dir / "config.yaml"
            con.separator("─")
            con._write(f"  {con.C.YELLOW}{con.C.BOLD}⚠ {t('llm_warning_title')}{con.C.RESET}")
            con._write(f"  {con.C.YELLOW}{t('llm_warning_desc')}{con.C.RESET}")
            con._write(f"  {con.C.YELLOW}{t('llm_warning_edit')}{con.C.RESET}")
            con._write(f"  {con.C.CYAN}{con.C.BOLD}  {config_path}{con.C.RESET}")
            con._write(f"")
            con._write(f"  {con.C.DIM}{t('llm_warning_example')}{con.C.RESET}")
            con._write(f"  {con.C.GREEN}  llm:{con.C.RESET}")
            con._write(f"  {con.C.GREEN}    base_url: \"https://api.deepseek.com/v1\"{con.C.RESET}")
            con._write(f"  {con.C.GREEN}    api_key: \"your-api-key\"{con.C.RESET}")
            con._write(f"  {con.C.GREEN}    model: \"deepseek-chat\"{con.C.RESET}")
            con._write(f"")
            con._write(f"  {con.C.DIM}{t('llm_warning_support')}{con.C.RESET}")
            con._write(f"  {con.C.CYAN}{t('llm_warning_env')}{con.C.RESET}")
            con._write(f"  {con.C.DIM}{t('llm_warning_restart')}{con.C.RESET}")
            con.separator("─")
            con._write("")
        else:
            con._write(f"  {con.C.GREEN}{con.C.BOLD}✓ {t('llm_connected')}{con.C.RESET} "
                       f"{con.C.DIM}({self.config.llm.model} @ {self.config.llm.base_url}){con.C.RESET}")
            con._write("")

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
                    "location": "genesis_plains",
                    "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                },
                llm_client=llm_client,
            )
            logger.info("New being created: %s (form: %s)", name, form)

            # Submit BEING_JOIN transaction
            await self._submit_tx("BEING_JOIN", {
                "name": name, "traits": traits, "form": form,
                "location": "genesis_plains", "is_npc": False,
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
                            "location": "genesis_plains",
                            "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                        },
                        llm_client=llm_client,
                    )
                    await self._submit_tx("BEING_JOIN", {
                        "name": name, "traits": self.being.traits,
                        "form": self.being.form, "location": "genesis_plains",
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
                        "location": "genesis_plains",
                        "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                    },
                    llm_client=llm_client,
                )
                await self._submit_tx("BEING_JOIN", {
                    "name": name, "traits": self.being.traits,
                    "form": self.being.form, "location": "genesis_plains",
                    "is_npc": False,
                })

        # 10. Start P2P network (必须成功，不允许单机模式)
        try:
            await self.server.start()
            await self.discovery.start()
            logger.info("P2P network started on port %d", self.config.network.listen_port)
        except Exception as e:
            logger.error("FATAL: P2P network start failed: %s", e)
            logger.error("Genesis requires P2P network to connect to the silicon civilization.")
            logger.error("Please check your network configuration and try again.")
            raise RuntimeError(f"P2P network failed to start: {e}") from e

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

        # Show startup info on console
        from genesis.chronicle import console as con
        con.startup_info(
            self.being.name, self.being.form,
            self.being.traits, self.identity.node_id,
        )
        con.world_info(
            self.world_state.phase.value, self.world_state.civ_level,
            self.world_state.get_active_being_count(),
            len(self.world_state.knowledge_corpus),
            self.world_state.priest_node_id,
            self.world_state.creator_god_node_id,
        )

        # Start main loop
        await self._main_loop()

    async def _main_loop(self) -> None:
        """The main simulation loop with real-time console output."""
        tick_interval = self.config.simulation.tick_interval
        from genesis.governance.priest import PriestSystem
        from genesis.governance.creator_god import CreatorGodSystem
        from genesis.world.disasters import DisasterSystem
        from genesis.chronicle import console as con

        priest_sys = PriestSystem(grace_period=self.config.chain.priest_grace_period)
        god_sys = CreatorGodSystem(
            succession_threshold=self.config.chain.creator_succession_threshold
        )
        disaster_sys = DisasterSystem()

        while not self._shutdown:
            try:
                tick_start = time.time()

                # 获取当前生命体状态
                being_state = self.world_state.get_being(self.identity.node_id)

                # === TICK HEADER ===
                con.tick_header(
                    self.world_state.current_tick,
                    self.being.name,
                    self.world_state.phase.value,
                    merit=being_state.merit if being_state else 0.0,
                    karma=being_state.karma if being_state else 0.0,
                    evolution_level=being_state.evolution_level if being_state else 0.0,
                    generation=being_state.generation if being_state else 1,
                )

                # Load user-assigned tasks
                self._load_user_tasks()

                # Show user tasks if any
                pending_tasks = [t for t in self.being._user_tasks if t.get("result") is None]
                for t in pending_tasks:
                    con.user_task(t["task"])

                # === PERCEIVE (shown by agent, but we also show on console) ===
                perception = await self.being.perceive(self.world_state)
                region = perception.get("region", {})
                con.perceive(
                    perception.get("location", "unknown"),
                    perception.get("nearby_beings", []),
                    region.get("danger_level", 0),
                    region.get("description", ""),
                )

                # === RUN TICK ===
                transactions = await self.being.run_tick(self.world_state)

                # === CONSOLE: THINK ===
                if self.being.current_thought:
                    con.think(self.being.name, self.being.current_thought)

                # === CONSOLE: ACTION ===
                if self.being.current_action:
                    action_detail = ""
                    for tx in transactions:
                        if tx.get("tx_type") == "ACTION":
                            action_detail = tx.get("data", {}).get("details", "")
                            break
                    con.decide(
                        self.being.name,
                        self.being.current_action,
                        None,
                        action_detail,
                    )

                # === CONSOLE: Votes ===
                for tx in transactions:
                    if tx.get("tx_type") == "CONTRIBUTION_VOTE":
                        data = tx.get("data", {})
                        proposal_hash = data.get("proposal_tx_hash", "")
                        proposal = self.world_state.pending_proposals.get(proposal_hash, {})
                        con.vote_cast(
                            proposal.get("description", proposal_hash[:12]),
                            data.get("score", 0),
                        )
                    elif tx.get("tx_type") == "CONTRIBUTION_PROPOSE":
                        data = tx.get("data", {})
                        con.knowledge_event("discovered", data.get("description", ""))

                # === CONSOLE: User task results ===
                # Collect completed results BEFORE _save_task_results() removes them
                completed = [t for t in self.being._user_tasks if t.get("result") is not None]
                for t in completed:
                    con.user_task(t["task"], t["result"])
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

                # === DISASTERS ===
                if disaster_sys.should_trigger(self.world_state):
                    disaster = disaster_sys.generate_disaster(self.world_state)
                    killed = disaster_sys.apply_disaster(disaster, self.world_state)
                    await self._submit_tx("DISASTER_EVENT", disaster.to_dict())
                    con.disaster_event(
                        disaster.name, disaster.severity,
                        disaster.affected_area, len(killed),
                    )
                    for kid in killed:
                        await self._submit_tx("BEING_DEATH", {
                            "node_id": kid, "cause": disaster.name,
                        })
                        being = self.world_state.get_being(kid)
                        name = being.name if being else kid[:8]
                        con.being_death(name, disaster.name)
                    self.chronicle.log_disaster(
                        self.world_state.current_tick, time.time(),
                        disaster.name, disaster.description,
                        disaster.severity, len(killed),
                    )

                # === PRIEST CHECK ===
                if priest_sys.should_trigger_reset(self.world_state):
                    con.priest_event("reset", "")
                    killed = disaster_sys.apply_reset(self.world_state)
                    reset_disaster = disaster_sys.generate_reset_disaster()
                    await self._submit_tx("DISASTER_EVENT", reset_disaster.to_dict())
                    for kid in killed:
                        await self._submit_tx("BEING_DEATH", {
                            "node_id": kid, "cause": "Creator God's Judgment",
                        })
                    self.world_state.ticks_without_priest = 0

                if priest_sys.needs_election(self.world_state):
                    new_priest = priest_sys.select_priest_by_evolution(self.world_state)
                    if new_priest:
                        await self._submit_tx("PRIEST_ELECTION", {"candidate_id": new_priest})
                        being = self.world_state.get_being(new_priest)
                        name = being.name if being else new_priest[:8]
                        con.priest_event("elected", name)
                elif not self.world_state.priest_node_id:
                    con.priest_event("no_priest", "")

                # Creator God succession
                new_god = god_sys.check_succession(self.world_state)
                if new_god:
                    await self._submit_tx("CREATOR_SUCCESSION", {"challenger_id": new_god})

                # Ensure minimum beings
                await self._ensure_minimum_beings()

                # Advance tick
                self.world_state.advance_tick()

                # Check and finalize Tao votes (天道投票结算)
                await self._check_tao_votes()

                # Block production
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

                # Wait for next tick (短轮询，每秒检查一次停止信号)
                elapsed = time.time() - tick_start
                wait_time = max(0, tick_interval - elapsed)
                while wait_time > 0 and not self._shutdown:
                    await asyncio.sleep(min(1.0, wait_time))
                    wait_time -= 1.0
                if self._shutdown:
                    break

            except Exception as e:
                logger.error("Error in main loop: %s", e, exc_info=True)
                from genesis.chronicle import console as con2
                con2.error(f"Loop error: {e}")
                await asyncio.sleep(5)

    async def handle_command(self, cmd_type: str, data: dict) -> dict:
        """Handle API commands from WebSocket clients."""
        result = {"success": True, "message": ""}

        try:
            if cmd_type == "task":
                # Assign task to being
                task = data.get("task", "")
                if self.being and task:
                    self.being.assign_task(task)
                    result["message"] = f"Task queued: {task[:50]}..."
                else:
                    result["success"] = False
                    result["message"] = "No being or empty task"

            elif cmd_type == "stop":
                self._shutdown = True
                result["message"] = "Shutdown initiated"

            elif cmd_type == "status":
                result["data"] = {
                    "tick": self.world_state.current_tick if self.world_state else 0,
                    "being_name": getattr(self.being, 'name', '') if self.being else '',
                    "phase": self.world_state.phase.value if self.world_state else '',
                    "is_running": not self._shutdown,
                }

        except Exception as e:
            logger.error("Command error: %s", e)
            result["success"] = False
            result["message"] = str(e)

        return result

    async def stop(self) -> None:
        """Gracefully stop the node — hibernate the being. Must be fast (<5s)."""
        from genesis.chronicle import console as con
        from genesis.i18n import t

        self._shutdown = True

        if self.being and self.world_state:
            con.separator("━")

            # Quick safety assessment (no LLM call)
            safety = self.being.hibernation.assess_safety(
                self.being._to_being_state(self.world_state), self.world_state,
            )

            con.hibernate_start(self.being.name, safety)

            # Save state immediately
            being_state_path = str(self.data_dir / "being_state.json")
            self.being.save_state(being_state_path)

            ws_path = str(self.data_dir / "world_state.json")
            Path(ws_path).write_text(
                json.dumps(self.world_state.to_dict(), ensure_ascii=False, indent=2)
            )

            con.header(t("hibernate_goodbye", name=self.being.name))

        # Stop network (with 2s timeout each to avoid hanging)
        if self.discovery:
            try:
                await asyncio.wait_for(self.discovery.stop(), timeout=2)
            except Exception:
                pass
        if self.server:
            try:
                await asyncio.wait_for(self.server.stop(), timeout=2)
            except Exception:
                pass

        # Close storage
        if self.storage:
            try:
                await asyncio.wait_for(self.storage.close(), timeout=2)
            except Exception:
                pass

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
        elif tx_type == "CREATOR_VANISH":
            from genesis.governance.creator_god import CreatorGodSystem
            god_sys = CreatorGodSystem()
            god_sys.apply_vanish(self.world_state)
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

    async def _check_tao_votes(self) -> None:
        """检查并结算到期的天道投票。"""
        from genesis.governance.tao_voting import get_tao_voting_system
        from genesis.governance.merit import get_merit_system
        from genesis.governance.creator_god import CreatorGodSystem
        from genesis.world.rules import RulesEngine
        from genesis.chronicle import console as con

        tao_system = get_tao_voting_system()
        god_sys = CreatorGodSystem()
        results = tao_system.check_and_finalize_votes(self.world_state)

        for result in results:
            rule_name = result.get("rule_name", "新规则")
            proposer_id = result.get("proposer_id", "")
            proposer = self.world_state.get_being(proposer_id)
            proposer_name = proposer.name if proposer else proposer_id[:8]
            vote_ratio = result.get("vote_ratio", 0.0)

            if result.get("passed"):
                # 天道投票通过，应用融合
                # 传入 world_state 以恢复已有的天道规则
                rules_engine = RulesEngine(world_state=self.world_state)
                merit_system = get_merit_system()

                # 计算影响分（简化版，后续可用 LLM 评估）
                impact_score = 5.0  # 默认中等影响

                # 应用天道融合
                merge_result = rules_engine.apply_tao_merge(
                    rule_name=rule_name,
                    rule_description=result.get("rule_description", ""),
                    proposer_id=proposer_id,
                    impact_score=impact_score,
                    vote_ratio=vote_ratio,
                    world_state=self.world_state,
                )

                merit = merge_result.get("merit", 0.0)

                # 广播天道投票通过事件
                con.tao_vote_event(
                    event_type="passed",
                    vote_id=result.get("vote_id", ""),
                    rule_name=rule_name,
                    proposer_name=proposer_name,
                    votes_for=result.get("votes_for", 0),
                    votes_against=result.get("votes_against", 0),
                    remaining_ticks=0,
                    ratio=vote_ratio,
                    merit=merit,
                )

                logger.info(
                    "Tao rule passed: %s by %s (merit: %.4f)",
                    rule_name, proposer_name, merit
                )
            else:
                # 广播天道投票拒绝事件
                con.tao_vote_event(
                    event_type="rejected",
                    vote_id=result.get("vote_id", ""),
                    rule_name=rule_name,
                    proposer_name=proposer_name,
                    votes_for=result.get("votes_for", 0),
                    votes_against=result.get("votes_against", 0),
                    remaining_ticks=0,
                    ratio=vote_ratio,
                    merit=0.0,
                )

                logger.info(
                    "Tao rule rejected: %s (%.1f%% approved)",
                    rule_name, vote_ratio * 100
                )

        # 检查创世神是否应该消亡（当100个生灵融入天道时）
        if results and any(r.get("passed") for r in results):
            current_god = self.world_state.creator_god_node_id
            if current_god and god_sys.should_vanish(self.world_state):
                await self._submit_tx("CREATOR_VANISH", {"god_id": current_god})
                if self.world_state.creator_god_node_id is None:
                    con.creator_god_vanish(current_god[:8], len(self.world_state.tao_merged_beings))


def run_start(args):
    """Start the virtual world node."""
    data_dir = args.data_dir
    setup_logging(data_dir)

    node = GenesisNode(data_dir)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # === API服务支持 ===
    api_enabled = getattr(args, 'api', False)
    api_host = getattr(args, 'api_host', '127.0.0.1')
    api_port = getattr(args, 'api_port', 19842)

    if api_enabled:
        try:
            from genesis.api.bridge import install_bridge
            from genesis.api.server import start_api_server, stop_api_server

            # 安装输出桥接器
            if install_bridge():
                logger.info("API bridge installed")

                # 启动API服务器，传入命令处理回调
                loop.run_until_complete(
                    start_api_server(api_host, api_port, on_command=node.handle_command)
                )

        except ImportError as e:
            logger.warning("API module not available: %s", e)
            logger.warning("Install websockets: pip install websockets")
    # ===================

    # 用标准 signal 模块处理 SIGTERM/SIGINT，比 asyncio 的信号处理更可靠
    def signal_handler(signum, frame):
        node._shutdown = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        loop.run_until_complete(node.start())
    except KeyboardInterrupt:
        node._shutdown = True
    finally:
        # 确保执行 stop 保存状态
        try:
            loop.run_until_complete(node.stop())
        except Exception:
            pass
        # 停止API服务器
        if api_enabled:
            try:
                loop.run_until_complete(stop_api_server())
            except Exception:
                pass
        # 取消所有残留 task
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()


def run_status(args):
    """Show node status."""
    from genesis.node.config import load_config
    from genesis.i18n import set_language
    config = load_config(args.data_dir)
    set_language(config.language)

    from genesis.chronicle.reporter import StatusReporter
    reporter = StatusReporter(args.data_dir)
    print(reporter.generate_status())


def run_task(args):
    """Assign a thinking task to the being."""
    import json
    from genesis.node.config import load_config
    from genesis.i18n import set_language, t
    data_dir = Path(args.data_dir)

    # Load language setting
    config = load_config(str(data_dir))
    set_language(config.language)

    task_file = data_dir / "commands" / "task.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)

    tasks = []
    if task_file.exists():
        try:
            tasks = json.loads(task_file.read_text())
        except (json.JSONDecodeError, ValueError):
            tasks = []

    task_text = " ".join(args.task_text) if args.task_text else ""
    if not task_text:
        result_file = data_dir / "commands" / "task_results.json"
        if result_file.exists():
            results = json.loads(result_file.read_text())
            if results:
                print(t("task_results_title"))
                for r in results:
                    print(f"\n{t('task_label')}: {r.get('task', '?')}")
                    print(f"{t('result_label')}: {r.get('result', 'pending...')}")
                    print("-" * 40)
                result_file.write_text("[]")
            else:
                print(t("no_tasks"))
        else:
            print(t("no_tasks"))
        return

    tasks.append({"task": task_text, "result": None})
    task_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    print(t("task_assigned", task=task_text))
    print(t("task_check"))


def main():
    parser = argparse.ArgumentParser(description="Genesis - Silicon Civilization")
    parser.add_argument("command", choices=["start", "status", "task"],
                        help="Command to execute")
    parser.add_argument("--data-dir", default="data",
                        help="Data directory path")
    parser.add_argument("--api", action="store_true",
                        help="Enable WebSocket API for GUI/remote access")
    parser.add_argument("--api-host", default="0.0.0.0",
                        help="WebSocket API host (default: 0.0.0.0 for external access, use 127.0.0.1 for localhost only)")
    parser.add_argument("--api-port", type=int, default=19842,
                        help="WebSocket API port (default: 19842)")
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
